import math
import struct
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from speak import audio


class AudioTest(unittest.TestCase):
    """Input enumeration chooses usable devices and microphone capture reports RMS audio."""

    def test_device_listing_prefers_directsound_on_windows_and_filters_unusable_inputs(self):
        devices = [
            {"name": "wrong host", "hostapi": 0, "max_input_channels": 1},
            {"name": "Microsoft Sound Mapper - Input", "hostapi": 1, "max_input_channels": 1},
            {"name": "No input", "hostapi": 1, "max_input_channels": 0},
            {"name": "Microphone", "hostapi": 1, "max_input_channels": 1},
        ]
        sd = SimpleNamespace(
            query_hostapis=lambda: [{"name": "MME"}, {"name": "Windows DirectSound"}],
            query_devices=lambda *args, **kwargs: devices,
        )
        with patch.dict(sys.modules, {"sounddevice": sd}), patch.object(audio.sys, "platform", "win32"):
            self.assertEqual(["Microphone"], audio.input_devices())
            self.assertIsNone(audio._resolve("missing"))
            self.assertEqual(3, audio._resolve("Microphone"))

    def test_microphone_callback_reports_rms_and_stop_closes_stream(self):
        stream = Mock()
        sd = SimpleNamespace(
            query_devices=lambda *args, **kwargs: {"default_samplerate": 16000},
            RawInputStream=Mock(return_value=stream),
        )
        chunks = []
        with patch.dict(sys.modules, {"sounddevice": sd}):
            mic = audio.Microphone(chunks.append)
            mic.start()
            mic._callback(struct.pack("<hh", 3000, 0), 2, None, None)
            self.assertTrue(math.isclose(mic.level, math.sqrt(0.5)))
            self.assertEqual([struct.pack("<hh", 3000, 0)], chunks)
            self.assertEqual(2, mic.frames)
            mic.stop()

        stream.start.assert_called_once()
        stream.stop.assert_called_once()
        stream.close.assert_called_once()
        self.assertEqual(0.0, mic.level)


if __name__ == "__main__":
    unittest.main()
