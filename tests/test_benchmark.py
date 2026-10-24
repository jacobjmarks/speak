import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

from speak import benchmark, tidy


def result(**overrides):
    values = dict(audio_s=10.0, load_s=3.0, transcribe_s=0.3, tidy_s=0.2, raw="hi", text="Hi.",
                  plan=tidy.Plan("fast", None, "literal", None, "summary"))
    return benchmark.Result(**{**values, **overrides})


class VerdictTest(unittest.TestCase):
    """The wait after speaking is rated in plain language; model start-up is not part of it."""

    def test_rating_follows_the_wait_after_speaking_not_model_loading(self):
        self.assertEqual("good", result(load_s=60).verdict[0])
        self.assertEqual("ok", result(transcribe_s=1.0, tidy_s=1.0).verdict[0])
        rating, text = result(transcribe_s=1.0, tidy_s=3.0).verdict
        self.assertEqual("slow", rating)
        self.assertIn("4.0 seconds", text)


class RunTest(unittest.TestCase):
    """The sample is streamed to the speech server, then tidied with the planned model."""

    def run_with(self, plan, cancelled=lambda: False):
        asr, llm = MagicMock(port=1), MagicMock(port=2)
        session = MagicMock()
        session.finish.return_value = "raw words"
        with patch.object(benchmark, "AsrSession", return_value=session), \
                patch.object(benchmark.tidy, "plan", return_value=plan), \
                patch.object(benchmark.tidy, "_probed"), \
                patch.object(benchmark.cleanup, "warm") as warm, \
                patch.object(benchmark.cleanup, "finalize", return_value=("Clean words.", "")) as finalize, \
                patch.object(benchmark, "STREAM_SPEEDUP", 1000):
            out = benchmark.run({"model": "m", "language": "auto"}, bytes(16000 * 2), 16000, asr, llm,
                                MagicMock(), cancelled)
        return out, session, llm, warm, finalize

    def test_tidy_model_is_started_and_used(self):
        plan = tidy.Plan("auto", "qwen25-q4km", "literal", None, "s")

        out, session, llm, warm, finalize = self.run_with(plan)

        self.assertEqual("Clean words.", out.text)
        self.assertEqual(1.0, out.audio_s)
        self.assertGreater(session.send_audio.call_count, 1)
        warm.assert_called_once_with(llm.port, "literal")
        finalize.assert_called_once_with("raw words", "auto", "literal", 2)

    def test_no_model_means_rules_only(self):
        plan = tidy.Plan("fast", None, "literal", None, "s")

        _, _, llm, warm, finalize = self.run_with(plan)

        llm.ensure.assert_not_called()
        finalize.assert_called_once_with("raw words", "fast", "literal", None)

    def test_cancelling_stops_streaming(self):
        plan = tidy.Plan("fast", None, "literal", None, "s")

        with self.assertRaises(benchmark.Cancelled):
            self.run_with(plan, cancelled=lambda: True)

    def test_a_failing_speech_session_is_closed_and_the_error_surfaces(self):
        plan = tidy.Plan("fast", None, "literal", None, "s")
        session = MagicMock()
        session.send_audio.side_effect = ConnectionError("lost")
        with patch.object(benchmark, "AsrSession", return_value=session), \
                patch.object(benchmark.tidy, "plan", return_value=plan), \
                patch.object(benchmark.tidy, "_probed"), \
                patch.object(benchmark, "STREAM_SPEEDUP", 1000):
            with self.assertRaises(ConnectionError):
                benchmark.run({"model": "m", "language": "auto"}, bytes(32000), 16000,
                              MagicMock(port=1), MagicMock(port=2), MagicMock())

        session.close.assert_called_once()


class ReadWavTest(unittest.TestCase):
    """Sample audio loads only as 16-bit mono, returned with its sample rate."""

    def write(self, channels, width):
        folder = tempfile.TemporaryDirectory(prefix="speak-wav-")
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "s.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(width)
            wav.setframerate(16000)
            wav.writeframes(bytes(width * channels * 100))
        return path

    def test_mono_16_bit_returns_pcm_and_rate(self):
        pcm, rate = benchmark.read_wav(self.write(1, 2))

        self.assertEqual((200, 16000), (len(pcm), rate))

    def test_stereo_or_8_bit_is_rejected(self):
        for channels, width in ((2, 2), (1, 1)):
            with self.subTest(channels=channels, width=width):
                with self.assertRaises(ValueError):
                    benchmark.read_wav(self.write(channels, width))


if __name__ == "__main__":
    unittest.main()
