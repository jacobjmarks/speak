"""Realtime transcription session over NeMo-Speech's websocket API."""
import json
import queue
import threading
from typing import Callable

import websocket

from .cleanup import PAUSE

# Gap between finalized segments that counts as a "long pause" (paragraph hint for cleanup).
PAUSE_SECONDS = 1.5

# on_update(final_text, partial_text): called from a background thread.
OnUpdate = Callable[[str, str], None]
OnError = Callable[[str], None]


class AsrSession:
    def __init__(self, port: int, sample_rate: int, language: str, punctuation: bool,
                 on_update: OnUpdate, on_error: OnError):
        self.on_update = on_update
        self.on_error = on_error
        self.final_text = ""
        self.marked_text = ""  # final_text plus PAUSE markers, for the cleanup model
        self.partial_text = ""
        self.last_word_end = None
        self.stopping = False
        self.done = threading.Event()
        self.audio = queue.Queue()
        self.ws = websocket.create_connection(
            f"ws://127.0.0.1:{port}/v1/audio/transcriptions/realtime", timeout=30, enable_multithread=True
        )
        try:
            created = json.loads(self.ws.recv())
            if created.get("type") != "session.created":
                raise RuntimeError(f"Unexpected ASR session response: {created}")
            self.ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "sample_rate": sample_rate,
                    "language": language,
                    "automatic_punctuation": punctuation,
                    "word_timestamps": True,
                },
            }))
            updated = json.loads(self.ws.recv())
            if updated.get("type") == "error":
                raise RuntimeError(updated.get("error", {}).get("message", "ASR session rejected settings"))
            if updated.get("type") != "session.updated":
                raise RuntimeError(f"Unexpected ASR settings response: {updated}")
        except Exception:
            self.ws.close()
            raise
        self.ws.settimeout(None)
        self.sender = threading.Thread(target=self._send_loop, daemon=True)
        self.receiver = threading.Thread(target=self._receive_loop, daemon=True)
        self.sender.start()
        self.receiver.start()

    @property
    def text(self) -> str:
        return f"{self.final_text} {self.partial_text}".strip()

    @property
    def marked(self) -> str:
        return f"{self.marked_text} {self.partial_text}".strip()

    def send_audio(self, chunk: bytes):
        self.audio.put(chunk)

    def finish(self, timeout: float = 15) -> str:
        """Flush remaining audio, wait for the final transcript, close, and return it with PAUSE markers."""
        self.stopping = True
        self.audio.put(None)
        self.sender.join(timeout=3)
        try:
            self.ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
            self.done.wait(timeout=timeout)
        except Exception:
            pass
        text = self.marked
        self.close()
        return text

    def close(self):
        self.stopping = True
        self.audio.put(None)
        try:
            self.ws.close()
        except Exception:
            pass

    def _send_loop(self):
        try:
            while (chunk := self.audio.get()) is not None:
                self.ws.send_binary(chunk)
        except Exception as exc:
            if not self.stopping:
                self.on_error(f"Audio stream failed: {exc}")

    def _mark_pauses(self, text: str, words: list) -> str:
        """Insert PAUSE markers where the gap between words (including across segments) is long."""
        tokens = [w.get("word", "") for w in words]
        if not words or tokens != text.split():
            return text  # timestamps don't line up with the text (e.g. after normalization); skip hints
        out = []
        for token, word in zip(tokens, words):
            start = word.get("start", 0)
            if self.last_word_end is not None and (out or self.marked_text) \
                    and start - self.last_word_end >= PAUSE_SECONDS:
                out.append(PAUSE)
            out.append(token)
            self.last_word_end = word.get("end", start)
        return " ".join(out)

    def _receive_loop(self):
        try:
            while True:
                event = json.loads(self.ws.recv())
                kind = event.get("type", "")
                if kind == "conversation.item.input_audio_transcription.delta":
                    self.partial_text += event.get("delta", "")
                    self.on_update(self.final_text, self.partial_text)
                elif kind == "conversation.item.input_audio_transcription.completed":
                    text = event.get("transcript", event.get("text", self.partial_text)).strip()
                    if text:
                        self.final_text = f"{self.final_text} {text}".strip()
                        self.marked_text = f"{self.marked_text} {self._mark_pauses(text, event.get('words') or [])}".strip()
                    self.partial_text = ""
                    self.on_update(self.final_text, self.partial_text)
                    if self.stopping:
                        self.done.set()
                elif kind == "error":
                    self.on_error("ASR error: " + event.get("error", {}).get("message", "unknown"))
                elif kind == "session.end":
                    break
        except websocket.WebSocketConnectionClosedException:
            pass
        except Exception as exc:
            if not self.stopping:
                self.on_error(f"ASR stream failed: {exc}")
        finally:
            self.done.set()
