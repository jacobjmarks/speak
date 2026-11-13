"""Qt bridge: controller callbacks arrive on worker threads; `Bridge` re-emits them as Qt signals, delivered on the UI thread."""
import threading

from PySide6.QtCore import QObject, Signal

from ..controller import Listener


class Bridge(QObject, Listener):
    state = Signal(str)
    progress = Signal(str, object)
    live = Signal(str)
    warning = Signal(str)
    result = Signal(str, str)
    error = Signal(str)
    hotkey_down = Signal()
    hotkey_up = Signal()
    escape = Signal()
    cancelled = Signal()
    probed = Signal()
    update_found = Signal(object, bool)   # Release or None, manual check
    update_progress = Signal(int)
    update_ready = Signal(object)        # Path of downloaded exe, or None on failure
    test_progress = Signal(str, object)  # setup test phase, percent
    test_done = Signal(object)           # benchmark.Result
    test_failed = Signal(str)
    _live_ready = Signal()               # wakes the UI thread to take the newest live text

    def __init__(self):
        super().__init__()
        self._live_lock = threading.Lock()
        self._live_latest = None  # newest live text not yet delivered; None when no wake-up is queued
        self._live_ready.connect(self._deliver_live)

    def on_state(self, state):
        self.state.emit(state.value)

    def on_progress(self, message, percent):
        self.progress.emit(message, percent)

    def on_live_text(self, text):
        # Updates can arrive faster than the UI paints; only the newest transcript matters, so queue one wake-up.
        with self._live_lock:
            queued = self._live_latest is not None
            self._live_latest = text
        if not queued:
            self._live_ready.emit()

    def _deliver_live(self):
        with self._live_lock:
            text, self._live_latest = self._live_latest, None
        if text is not None:
            self.live.emit(text)

    def on_warning(self, message):
        self.warning.emit(message)

    def on_result(self, text, note):
        self.result.emit(text, note)

    def on_error(self, message):
        self.error.emit(message)

    def on_cancelled(self):
        self.cancelled.emit()
