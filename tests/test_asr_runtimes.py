import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from speak import runtimes
from speak.asr import AsrSession
from speak.cleanup import PAUSE


class FakeSocket:
    def __init__(self, events):
        self.events = iter(events)
        self.sent = []
        self.binary = []
        self.closed = False

    def recv(self):
        return json.dumps(next(self.events))

    def send(self, message):
        self.sent.append(json.loads(message))

    def send_binary(self, chunk):
        self.binary.append(chunk)

    def settimeout(self, timeout):
        pass

    def close(self):
        self.closed = True


class AsrSessionTest(unittest.TestCase):
    """The ASR websocket handshake, audio flow, transcript events, and shutdown contract."""

    def test_streaming_handshake_audio_and_pause_markers(self):
        events = [
            {"type": "session.created"},
            {"type": "session.updated"},
            {"type": "conversation.item.input_audio_transcription.delta", "delta": "hello"},
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "transcript": "hello there",
                "words": [
                    {"word": "hello", "start": 0.0, "end": 0.2},
                    {"word": "there", "start": 0.3, "end": 0.5},
                ],
            },
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "transcript": "again now",
                "words": [
                    {"word": "again", "start": 2.1, "end": 2.4},
                    {"word": "now", "start": 2.5, "end": 2.7},
                ],
            },
            {"type": "session.end"},
        ]
        ws = FakeSocket(events)
        updates, errors = [], []
        with patch("speak.asr.websocket.create_connection", return_value=ws):
            session = AsrSession(1234, 16000, "en-GB", True, lambda *v: updates.append(v), errors.append)
            session.send_audio(b"\x01\x00")
            transcript = session.finish(timeout=1)

        self.assertEqual(f"hello there {PAUSE} again now", transcript)
        self.assertEqual(b"\x01\x00", ws.binary[0])
        self.assertEqual("session.update", ws.sent[0]["type"])
        self.assertEqual("en-GB", ws.sent[0]["session"]["language"])
        self.assertEqual("input_audio_buffer.commit", ws.sent[-1]["type"])
        self.assertTrue(any(final == "hello there" and partial == "" for final, partial in updates))
        self.assertEqual([], errors)
        self.assertTrue(ws.closed)

    def test_unexpected_handshake_closes_socket_and_raises(self):
        ws = FakeSocket([{"type": "not-a-session"}])
        with patch("speak.asr.websocket.create_connection", return_value=ws):
            with self.assertRaisesRegex(RuntimeError, "Unexpected ASR session response"):
                AsrSession(1234, 16000, "en", True, Mock(), Mock())
        self.assertTrue(ws.closed)


class ManagedServerTest(unittest.TestCase):
    """A runtime is launched once when ready, reused by key, and stopped cleanly."""

    def test_start_reuses_matching_server_and_stop_terminates_it(self):
        class Process:
            def __init__(self, *_args, **_kwargs):
                self.exit_code = None
                self.terminated = False

            def poll(self):
                return self.exit_code

            def terminate(self):
                self.terminated = True
                self.exit_code = 0

            def wait(self, timeout):
                return self.exit_code

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "runtime"
            executable.touch()
            process = Process()
            server = runtimes.ManagedServer("test", root / "server.log", "/ready")
            with patch.object(runtimes, "free_port", return_value=9876), \
                    patch.object(runtimes.subprocess, "Popen", return_value=process) as popen, \
                    patch.object(runtimes.urllib.request, "urlopen", return_value=Response()), \
                    patch.object(runtimes, "tie_to_app"):
                self.assertTrue(server.start("model-a", executable, [], root, {}, timeout=1))
                self.assertTrue(server.running("model-a"))
                self.assertFalse(server.start("model-a", executable, [], root, {}))
                self.assertEqual(1, popen.call_count)
                server.stop()

        self.assertTrue(process.terminated)
        self.assertFalse(server.running("model-a"))

    def test_missing_runtime_fails_before_spawning(self):
        server = runtimes.ManagedServer("test", Path("unused.log"), "/ready")
        with patch.object(runtimes.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(RuntimeError, "runtime is missing"):
                server.start("model", Path("missing-runtime"), [], Path("."), {})
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
