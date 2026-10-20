"""Qt application: wires the Dictation controller to the window, overlay, tray, and global hotkey.

Controller callbacks arrive on worker threads; `Bridge` re-emits them as Qt signals (queued onto the UI thread).
"""
import sys
import threading
import time
from datetime import datetime

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .. import config, hotkey, tidy, updates
from ..controller import Dictation, Listener, State
from . import theme
from .overlay import Overlay
from .window import CloseDialog, MainWindow, app_icon


class Bridge(QObject, Listener):
    state = Signal(str)
    progress = Signal(str, object)
    live = Signal(str)
    result = Signal(str, str)
    error = Signal(str)
    hotkey_down = Signal()
    hotkey_up = Signal()
    probed = Signal()
    update_found = Signal(object, bool)   # Release or None, manual check
    update_progress = Signal(int)
    update_ready = Signal(object)        # Path of downloaded exe, or None on failure

    def on_state(self, state):
        self.state.emit(state.value)

    def on_progress(self, message, percent):
        self.progress.emit(message, percent)

    def on_live_text(self, text):
        self.live.emit(text)

    def on_result(self, text, note):
        self.result.emit(text, note)

    def on_error(self, message):
        self.error.emit(message)


HOLD_SECONDS = 0.4      # auto mode: a press held longer than this is push-to-talk
CAPTURE_GRACE = 0.6     # ignore the hotkey this long after recording a new shortcut


class SpeakApp(QObject):
    def __init__(self, app: QApplication, background: bool):
        super().__init__()
        self.app = app
        self.settings = config.load_settings()
        self.bridge = Bridge()
        self.dictation = Dictation(self.settings, self.bridge)
        level = lambda: self.dictation.level  # noqa: E731

        self.window = MainWindow(self.settings, level, lambda: self.dictation.state == State.IDLE)
        self.overlay = Overlay(level)
        self.tray = self._make_tray()
        self.palette = theme.LIGHT
        self._capturing = False
        self._capture_ended = 0.0
        self._pressed_at = None  # set when a hotkey press started (or will stop) dictation
        self._use_overlay = False  # decided per dictation: Speak's own window shows progress when focused
        self._release = None       # newer release found
        self._downloading = False
        self._downloaded = None    # verified exe waiting beside ours; swapped in on quit
        self._restart = False

        b = self.bridge
        b.state.connect(self._on_state)
        b.progress.connect(self._on_progress)
        b.live.connect(self._on_live)
        b.result.connect(self._on_result)
        b.error.connect(self._on_error)
        b.hotkey_down.connect(self._on_hotkey_down)
        b.hotkey_up.connect(self._on_hotkey_up)
        b.probed.connect(self._refresh_tidy)
        b.update_found.connect(self._on_update_found)
        b.update_progress.connect(lambda p: self.window.set_update(f"Downloading {p}%", enabled=False))
        b.update_ready.connect(self._on_update_ready)

        w = self.window
        w.close_requested.connect(self._on_close)
        w.update_clicked.connect(self._on_update_clicked)
        w.settings.check_updates.connect(lambda: self._check_updates(manual=True))
        w.dictate.toggle_requested.connect(self.dictation.toggle)
        w.history.open_settings.connect(lambda: w.show_page(2))
        w.settings.changed.connect(self._update)
        w.settings.shortcut_changed.connect(lambda combo: self._update({"hotkey": combo}))
        w.settings.shortcut_recording.connect(self._on_shortcut_recording)
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda *_: self._apply_theme())

        self._apply_theme()
        self._register_hotkey()
        w.dictate.set_shortcut(self.settings["hotkey"], self.settings["shortcut_mode"])
        w.history.refresh(self.settings["history_enabled"])
        self._refresh_tidy()
        threading.Thread(target=lambda: (tidy._probed.wait(30), b.probed.emit()), daemon=True).start()
        updates.cleanup()
        self.dictation.warm_up()
        self._update_timer = QTimer(self, interval=24 * 3600 * 1000, timeout=self._check_updates)
        self._update_timer.start()
        QTimer.singleShot(5000, self._check_updates)
        if not (background and self.tray):
            w.show()

    # ----- settings -----

    def _update(self, changes: dict):
        self.settings.update(changes)
        config.save_settings(self.settings)
        self.dictation.settings_changed()
        if "theme" in changes:
            self._apply_theme()
        if "hotkey" in changes:
            self._register_hotkey()
        if {"hotkey", "shortcut_mode"} & changes.keys():
            self.window.dictate.set_shortcut(self.settings["hotkey"], self.settings["shortcut_mode"])
        if "history_enabled" in changes:
            self.window.history.refresh(self.settings["history_enabled"])
        if {"tidy", "cleanup_model", "corrections"} & changes.keys():
            self._refresh_tidy()
        if "updates" in changes:
            self._check_updates()
        self.window.settings.sync(self.settings)

    # ----- updates -----

    def _check_updates(self, manual: bool = False):
        if self._downloading or self._downloaded:
            return
        if self.settings["updates"] == "off" and not manual:
            self.window.set_update("")
            return
        if manual:
            self.window.settings.set_update_status("Checking…")
        if updates.VERSION:
            self.window.settings.set_last_check(datetime.now())
        threading.Thread(target=lambda: self.bridge.update_found.emit(updates.newer_release(), manual),
                         daemon=True).start()

    def _on_update_found(self, release, manual: bool):
        self._release = release
        if manual:
            self.window.settings.set_update_status(f"{release.version} available" if release else "Up to date")
        if not release:
            self.window.set_update("")
        elif self.settings["updates"] == "auto" and updates.can_install(release):
            self._download()
        else:
            self.window.set_update(f"Update to {release.version}", "Download and install" if
                                   updates.can_install(release) else "Open the download page")

    def _download(self):
        self._downloading = True
        self.window.set_update("Downloading…", enabled=False)
        release, bridge = self._release, self.bridge

        def run():
            try:
                bridge.update_ready.emit(updates.download(release, bridge.update_progress.emit))
            except Exception:
                bridge.update_ready.emit(None)
        threading.Thread(target=run, daemon=True).start()

    def _on_update_ready(self, path):
        self._downloading = False
        self._downloaded = path
        if path:
            self.window.set_update("Restart to update", f"Installs {self._release.version}; also happens when Speak quits")
        else:
            self.window.set_update(f"Update to {self._release.version}", "Download failed. Click to try again")

    def _on_update_clicked(self):
        if self._downloaded:
            if self.dictation.state != State.IDLE:
                return
            self._restart = True
            self.quit()
        elif updates.can_install(self._release):
            self._download()
        elif self._release:
            QDesktopServices.openUrl(QUrl(self._release.page))

    def _refresh_tidy(self):
        if tidy.probed():
            plan = tidy.plan(self.settings)
            self.window.settings.set_tidy_summary(plan.summary, plan.model_id == config.LARGE_MODEL)
        else:
            self.window.settings.set_tidy_summary("Checking what your computer can run…", True)

    def _apply_theme(self):
        self.palette = theme.resolve(self.settings["theme"])
        self.app.setStyleSheet(theme.stylesheet(self.palette))
        self.window.dictate.set_palette(self.palette)
        self.window.settings.set_palette(self.palette)
        self.overlay.palette_ = self.palette
        self._on_state(self.dictation.state.value, refresh_only=True)

    def _register_hotkey(self):
        try:
            hotkey.register(self.settings["hotkey"], self.bridge.hotkey_down.emit, self.bridge.hotkey_up.emit)
        except Exception as exc:
            self.window.set_status("Shortcut unavailable", self.palette.danger)
            self.window.dictate.set_result("", f"Couldn't use that shortcut: {exc}")

    def _on_shortcut_recording(self, active: bool):
        self._capturing = active
        self._capture_ended = time.monotonic()
        self._pressed_at = None

    # ----- hotkey: "hold" (release stops), "toggle" (tap again stops), "auto" (held > HOLD_SECONDS = hold) -----

    def _hotkey_blocked(self) -> bool:
        return self._capturing or time.monotonic() - self._capture_ended < CAPTURE_GRACE

    def _on_hotkey_down(self):
        if self._hotkey_blocked():
            return
        state = self.dictation.state
        if state == State.IDLE:
            self._pressed_at = time.monotonic()
            self.dictation.start()
        elif state == State.LISTENING:
            self._pressed_at = None
            self.dictation.stop()

    def _on_hotkey_up(self):
        pressed_at, self._pressed_at = self._pressed_at, None
        if pressed_at is None or self._hotkey_blocked():
            return
        mode = self.settings["shortcut_mode"]
        if mode == "hold" or (mode == "auto" and time.monotonic() - pressed_at >= HOLD_SECONDS):
            self.dictation.stop()

    # ----- dictation events -----

    def _on_state(self, state: str, refresh_only: bool = False):
        pal = self.palette
        labels = {State.IDLE: ("Ready", pal.success), State.PREPARING: ("Starting", pal.muted),
                  State.LISTENING: ("Listening", pal.danger), State.PROCESSING: ("Thinking", pal.accent)}
        text, color = labels[State(state)]
        self.window.set_status(text, color)
        if self.tray:
            self.tray.setIcon(app_icon(pal.danger if state == State.LISTENING else ""))
            self.tray.setToolTip(f"Speak · {text}")
        if refresh_only or state == State.IDLE:
            return
        self.window.dictate.set_mode(state)
        if state == State.LISTENING:
            self.window.dictate.set_live("")
        if state == State.PREPARING:
            self._use_overlay = self.settings["overlay_enabled"] and not (
                self.window.isVisible() and self.window.isActiveWindow())
            self.overlay.preview = self.settings["live_preview"]
            self.overlay.position = self.settings["overlay_position"]
        if self._use_overlay:
            self.overlay.set_mode(state)

    def _on_progress(self, message: str, percent):
        mode = "processing" if self.dictation.state == State.PROCESSING else "preparing"
        self.window.dictate.set_mode(mode, percent, message)
        self.window.set_status(message, self.palette.muted)
        if self.overlay.isVisible():
            self.overlay.set_mode(mode, percent, message)

    def _on_live(self, text: str):
        self.window.dictate.set_live(text)
        if self.overlay.isVisible():
            self.overlay.set_text(text)

    def _on_result(self, text: str, note: str):
        self.window.dictate.set_result(text, note)
        self.window.dictate.set_mode("done")
        if self.overlay.isVisible():
            self.overlay.set_mode("done")
        if self.settings["history_enabled"]:
            self.window.history.refresh(True)

    def _on_error(self, message: str):
        self.window.dictate.set_result(self.window.dictate.text.toPlainText(), message)
        self.window.dictate.set_mode("error")
        self.window.set_status("Ready", self.palette.success)
        if self.overlay.isVisible():
            self.overlay.set_mode("error")
        if self.tray and not self.window.isVisible():
            self.tray.showMessage("Speak", message, QSystemTrayIcon.Warning, 4000)

    # ----- window / tray -----

    def _make_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QSystemTrayIcon(app_icon(), self)
        tray.setToolTip("Speak")
        menu = QMenu()
        menu.addAction("Open Speak", self.show_window)
        menu.addAction("Start / stop dictation", self.dictation.toggle)
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        tray.setContextMenu(menu)
        tray.activated.connect(
            lambda reason: self.show_window() if reason == QSystemTrayIcon.Trigger else None)
        tray.show()
        self._tray_menu = menu
        return tray

    def show_window(self):
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def _on_close(self):
        action = self.settings["close_action"]
        if self.tray is None:
            action = "exit"
        elif action == "ask":
            dialog = CloseDialog(self.window)
            dialog.exec()
            if dialog.choice is None:
                return
            action = dialog.choice
            self._update({"close_action": action})
        if action == "tray":
            self.window.hide()
            if self.dictation.state == State.IDLE:
                self.overlay.hide_now()
        else:
            self.quit()

    def quit(self):
        self.window.allow_close = True  # Qt 6 quit() closes windows; don't re-prompt
        hotkey.unregister()
        self.overlay.hide_now()
        self.dictation.shutdown()
        if self.tray:
            self.tray.hide()
        if self._downloaded:
            try:
                updates.install(self._downloaded, updates.exe_path())
                if self._restart:
                    updates.restart(updates.exe_path())
            except OSError:
                pass
            self._downloaded = None
        self.app.quit()


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("Speak")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())
    speak = SpeakApp(app, background="--background" in sys.argv)
    app.aboutToQuit.connect(lambda: speak.dictation.shutdown())
    sys.exit(app.exec())
