"""UI-agnostic dictation state machine: idle -> preparing -> listening -> processing -> idle.

All listener callbacks fire on background threads; the UI must marshal them onto its own thread.
"""
import logging
import threading
import time
from enum import Enum

from . import cleanup, history, output, platform_utils, tidy
from .asr import AsrSession
from .audio import Microphone
from .config import CLEANUP_MODELS, MODELS_DIR
from .platform_utils import exe_name
from .runtimes import AsrServer, CleanupServer, ModelDownloadError, llama_root

log = logging.getLogger(__name__)

FINISHING = "Finishing up"  # one word for transcribe + tidy: tidy-up may be off, and transcribing is brief


def _explain(exc: Exception) -> str:
    """User-facing text for a failure; technical detail goes to the log."""
    if isinstance(exc, ModelDownloadError):
        return str(exc)
    log.error("Dictation failed", exc_info=exc)
    return "Something went wrong. Please try again, or restart Speak."


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
        self._lock = threading.RLock()  # re-entered by _set_state from _abort
        self._cancelled = False
        self._target = None  # window focused when dictation started
        self._unload_timer = None
        self._cleanup_retry_at = 0.0  # monotonic time before which a failed tidy-up download isn't retried
        threading.Thread(target=tidy.probe, args=(llama_root() / exe_name("llama-server"),), daemon=True).start()

    @property
    def level(self) -> float:
        return self.mic.level if self.mic is not None and self.state == State.LISTENING else 0.0

    def toggle(self):
        with self._lock:
            if self.state == State.IDLE:
                self._start_locked()
            elif self.state == State.LISTENING:
                self._stop_locked()

    def start(self):
        with self._lock:
            if self.state == State.IDLE:
                self._start_locked()

    def stop(self):
        """Finish listening; if still preparing, give up instead (e.g. hold-to-talk released too early)."""
        with self._lock:
            if self.state == State.LISTENING:
                self._stop_locked()
            elif self.state == State.PREPARING:
                self._cancelled = True

    def _start_locked(self):
        self._cancel_unload()
        self._cancelled = False
        self._target = platform_utils.foreground_window()
        self._set_state(State.PREPARING)
        threading.Thread(target=self._prepare, daemon=True).start()

    def _stop_locked(self):
        self._set_state(State.PROCESSING)
        threading.Thread(target=self._finish, daemon=True).start()

    def warm_up(self):
        """Start already-downloaded runtimes in the background so the first dictation is fast.

        Never triggers a download; errors are ignored.
        """
        def run():
            try:
                tidy._probed.wait(15)
                if not any(p.name != "cleanup" for p in MODELS_DIR.glob("*")):
                    return  # speech model not downloaded yet
                self.asr_server.ensure(self.settings["model"], lambda *_: None)
                plan = tidy.plan(self.settings)
                if plan.model_id and (MODELS_DIR / "cleanup" / CLEANUP_MODELS[plan.model_id]["file"]).exists():
                    self._ensure_cleanup(plan, lambda *_: None)
            except Exception:
                pass
            with self._lock:
                if self.state == State.IDLE:
                    self._schedule_unload()
        threading.Thread(target=run, daemon=True).start()

    def settings_changed(self):
        with self._lock:
            if self.state == State.IDLE:
                self._schedule_unload()
        plan = tidy.plan(self.settings)
        if self.cleanup_server.key not in (None, plan.key):
            self.cleanup_server.stop()

    # ----- free RAM/VRAM when idle -----

    def _cancel_unload(self):
        if self._unload_timer is not None:
            self._unload_timer.cancel()
            self._unload_timer = None

    def _schedule_unload(self):
        """Call with the lock held, when going idle. Stops both runtimes after settings["unload_after"] minutes."""
        self._cancel_unload()
        after = self.settings.get("unload_after", "5")
        if after == "never":
            return
        timer = threading.Timer(float(after) * 60, lambda: self._unload(timer))
        timer.daemon = True
        self._unload_timer = timer
        timer.start()

    def _unload(self, timer):
        with self._lock:
            if self.state != State.IDLE or self._unload_timer is not timer:
                return
            self._unload_timer = None
        # Outside the lock: a dictation starting now just waits for the stop, then reloads.
        self.asr_server.stop()
        self.cleanup_server.stop()

    def shutdown(self):
        self._cancel_unload()
        if self.mic is not None:
            self.mic.stop()
        if self.session is not None:
            self.session.close()
        self.asr_server.stop()
        self.cleanup_server.stop()

    def _set_state(self, state: State):
        with self._lock:
            self.state = state
            if state == State.IDLE:
                self._schedule_unload()
        self.listener.on_state(state)

    def _ensure_cleanup(self, plan, progress):
        if self.cleanup_server.ensure(plan, progress):
            cleanup.warm(self.cleanup_server.port, plan.llm_mode)

    def _ensure_runtimes(self, progress):
        tidy._probed.wait(15)
        self.asr_server.ensure(self.settings["model"], progress)
        plan = tidy.plan(self.settings)
        if plan.model_id:
            self._ensure_cleanup(plan, progress)

    def _prepare(self):
        try:
            self.mic = Microphone(self._on_audio, self.settings["mic_device"])
            self._ensure_runtimes(self.listener.on_progress)
            self.session = AsrSession(
                self.asr_server.port,
                self.mic.sample_rate,
                self.settings["language"],
                punctuation=True,
                on_update=lambda final, partial: self.listener.on_live_text(f"{final} {partial}".strip()),
                on_error=self.listener.on_error,
            )
            with self._lock:
                if self._cancelled:
                    self._abort("You let go too soon. Hold the shortcut until the mic turns red.")
                    return
                self.mic.start()
                self.listener.on_live_text("")
                self._set_state(State.LISTENING)
        except Exception as exc:
            self._abort(_explain(exc))

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
            self.listener.on_error(_explain(exc))

    def _process(self):
        mic, session = self.mic, self.session
        mic.stop()
        self.session = None
        if mic.frames == 0:
            session.close()
            self._set_state(State.IDLE)
            self.listener.on_error("Speak didn't hear anything. Check that your microphone is working.")
            return
        self.listener.on_progress(FINISHING, None)
        text = session.finish()
        plan = tidy.plan(self.settings)
        port = None
        tidy_note = ""
        if text and plan.model_id:
            if time.monotonic() < self._cleanup_retry_at:
                tidy_note = "Tidy-up is unavailable right now, so your text was left as spoken."
            else:
                try:
                    self._ensure_cleanup(plan, self.listener.on_progress)
                    port = self.cleanup_server.port
                    self.listener.on_progress(FINISHING, None)
                except ModelDownloadError:
                    self._cleanup_retry_at = time.monotonic() + 300
                    tidy_note = "Tidy-up is unavailable right now, so your text was left as spoken."
                except Exception:
                    pass
        text, note = cleanup.finalize(text, plan.level, plan.llm_mode, port)
        note = note or tidy_note
        if not text:
            self._set_state(State.IDLE)
            self.listener.on_error("Speak didn't catch any words. Please try again.")
            return
        self.latest = text
        if self.settings["history_enabled"]:
            history.add(text)
        if self.settings["auto_paste"]:
            target = self._target
            enter = lambda: (self.settings["press_enter"] and target is not None  # noqa: E731
                             and platform_utils.foreground_window() == target)
            try:
                output.paste(text, enter)
            except Exception:
                note = note or "Paste unavailable; copy it from Speak"
        self._set_state(State.IDLE)
        self.listener.on_result(text, note)
