"""Qt application: wires the Dictation controller to the window, overlay, tray, and global hotkey.

Controller callbacks arrive on worker threads; `Bridge` re-emits them as Qt signals (queued onto the UI thread).
"""
import sys
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .. import config, hotkey, tidy
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
    hotkey = Signal()
    probed = Signal()

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


class SpeakApp(QObject):
    def __init__(self, app: QApplication, background: bool):
        super().__init__()
        self.app = app
        self.settings = config.load_settings()
        self.bridge = Bridge()
        self.dictation = Dictation(self.settings, self.bridge)
        level = lambda: self.dictation.level  # noqa: E731

        self.window = MainWindow(self.settings, level)
        self.overlay = Overlay(level)
        self.tray = self._make_tray()
        self.palette = theme.LIGHT

        b = self.bridge
        b.state.connect(self._on_state)
        b.progress.connect(self._on_progress)
        b.live.connect(self._on_live)
        b.result.connect(self._on_result)
        b.error.connect(self._on_error)
        b.hotkey.connect(self.dictation.toggle)
        b.probed.connect(self._refresh_tidy)

        w = self.window
        w.close_requested.connect(self._on_close)
        w.dictate.toggle_requested.connect(self.dictation.toggle)
        w.history.enable_requested.connect(lambda: self._update({"history_enabled": True}))
        w.settings.changed.connect(self._update)
        w.settings.shortcut_changed.connect(lambda combo: self._update({"hotkey": combo}))
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda *_: self._apply_theme())

        self._apply_theme()
        self._register_hotkey()
        w.dictate.set_shortcut(self.settings["hotkey"])
        w.history.refresh(self.settings["history_enabled"])
        self._refresh_tidy()
        threading.Thread(target=lambda: (tidy._probed.wait(30), b.probed.emit()), daemon=True).start()
        self.dictation.warm_up()
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
            self.window.dictate.set_shortcut(self.settings["hotkey"])
        if "history_enabled" in changes:
            self.window.history.refresh(self.settings["history_enabled"])
        if {"tidy", "cleanup_model"} & changes.keys():
            self._refresh_tidy()
        self.window.settings.sync(self.settings)

    def _refresh_tidy(self):
        summary = tidy.plan(self.settings).summary if tidy.probed() else "Checking what your computer can run…"
        self.window.settings.set_tidy_summary(summary)

    def _apply_theme(self):
        self.palette = theme.resolve(self.settings["theme"])
        self.app.setStyleSheet(theme.stylesheet(self.palette))
        self.window.dictate.mic.palette_ = self.palette
        self.window.dictate.mic.update()
        self.window.settings.set_palette(self.palette)
        self.overlay.palette_ = self.palette
        self._on_state(self.dictation.state.value, refresh_only=True)

    def _register_hotkey(self):
        try:
            hotkey.register(self.settings["hotkey"], self.bridge.hotkey.emit)
        except Exception as exc:
            self.window.set_status("Shortcut unavailable", self.palette.danger)
            self.window.dictate.set_result("", f"Couldn't use that shortcut: {exc}")

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
        if self.settings["overlay_enabled"]:
            self.overlay.show_text = self.settings["live_preview"] != "off"
            self.overlay.set_mode(state)

    def _on_progress(self, message: str, percent):
        mode = "processing" if self.dictation.state == State.PROCESSING else "preparing"
        self.window.dictate.set_mode(mode, percent)
        self.window.dictate.mic.setToolTip(message)
        self.window.set_status(f"{int(percent)}%" if percent is not None else "Starting", self.palette.muted)
        if self.overlay.isVisible():
            self.overlay.set_mode(mode, percent)

    def _on_live(self, text: str):
        self.window.dictate.set_live(text)
        if self.settings["live_preview"] != "off":
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
