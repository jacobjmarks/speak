"""UI-agnostic dictation state machine: idle -> preparing -> listening -> processing -> idle.

All listener callbacks fire on background threads; the UI must marshal them onto its own thread.
"""
import threading
from enum import Enum

from . import cleanup, history, output
from .asr import AsrSession
from .config import cleanup_model_id
from .audio import Microphone
from .runtimes import AsrServer, CleanupServer


class State(str, Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    LISTENING = "listening"
    PROCESSING = "processing"


class Listener:
    """Override what you need. Every method may be called from any thread."""

    def on_state(self, state: State) -> None: ...
    def on_progress(self, message: str, percent) -> None: ...
    def on_live_text(self, text: str) -> None: ...
    def on_result(self, text: str, note: str) -> None: ...
    def on_error(self, message: str) -> None: ...


class Dictation:
    def __init__(self, settings: dict, listener: Listener):
        self.settings = settings
        self.listener = listener
        self.state = State.IDLE
        self.asr_server = AsrServer()
        self.cleanup_server = CleanupServer()
        self.mic = None
        self.session = None
        self.latest = ""
        self._lock = threading.Lock()

    @property
    def level(self) -> float:
        return self.mic.level if self.mic is not None and self.state == State.LISTENING else 0.0

    def toggle(self):
        with self._lock:
            if self.state == State.IDLE:
                self._set_state(State.PREPARING)
                threading.Thread(target=self._prepare, daemon=True).start()
            elif self.state == State.LISTENING:
                self._set_state(State.PROCESSING)
                threading.Thread(target=self._finish, daemon=True).start()

    def warm_up(self):
        """Start runtimes in the background so the first dictation is fast. Errors are ignored."""
        def run():
            try:
                self._ensure_runtimes(lambda *_: None)
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

    def settings_changed(self):
        if self.cleanup_server.key not in (None, cleanup_model_id(self.settings)):
            self.cleanup_server.stop()

    def shutdown(self):
        if self.mic is not None:
            self.mic.stop()
        if self.session is not None:
            self.session.close()
        self.asr_server.stop()
        self.cleanup_server.stop()

    def _set_state(self, state: State):
        self.state = state
        self.listener.on_state(state)

    def _ensure_runtimes(self, progress):
        self.asr_server.ensure(self.settings["model"], progress)
        if self.settings["cleanup_enabled"]:
            self.cleanup_server.ensure(cleanup_model_id(self.settings), progress)

    def _prepare(self):
        try:
            self.mic = Microphone(self._on_audio)
            self._ensure_runtimes(self.listener.on_progress)
            self.session = AsrSession(
                self.asr_server.port,
                self.mic.sample_rate,
                self.settings["language"],
                punctuation=True,
                on_update=lambda final, partial: self.listener.on_live_text(f"{final} {partial}".strip()),
                on_error=self.listener.on_error,
            )
            self.mic.start()
            self.listener.on_live_text("")
            self._set_state(State.LISTENING)
        except Exception as exc:
            self._abort(str(exc))

    def _on_audio(self, chunk: bytes):
        session = self.session
        if session is not None:
            session.send_audio(chunk)

    def _abort(self, message: str):
        if self.mic is not None:
            self.mic.stop()
        if self.session is not None:
            self.session.close()
            self.session = None
        self._set_state(State.IDLE)
        self.listener.on_error(message)

    def _finish(self):
        try:
            self._process()
        except Exception as exc:
            self._set_state(State.IDLE)
            self.listener.on_error(str(exc))

    def _process(self):
        mic, session = self.mic, self.session
        mic.stop()
        self.session = None
        if mic.frames == 0:
            session.close()
            self._set_state(State.IDLE)
            self.listener.on_error("No audio captured")
            return
        text = session.finish()
        port = None
        if text and self.settings["cleanup_enabled"]:
            try:
                self.cleanup_server.ensure(cleanup_model_id(self.settings), self.listener.on_progress)
                port = self.cleanup_server.port
            except Exception:
                pass
        text, note = cleanup.finalize(text, self.settings["cleanup_mode"], port)
        if not text:
            self._set_state(State.IDLE)
            self.listener.on_error("No speech recognized")
            return
        self.latest = text
        if self.settings["history_enabled"]:
            history.add(text)
        if self.settings["auto_paste"]:
            try:
                output.paste(text)
            except Exception:
                note = note or "Paste unavailable; copy it from Speak"
        self._set_state(State.IDLE)
        self.listener.on_result(text, note)
