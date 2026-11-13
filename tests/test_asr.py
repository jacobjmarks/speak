import json
import unittest
from unittest.mock import Mock, patch

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


if __name__ == "__main__":
    unittest.main()
