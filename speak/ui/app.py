"""Qt application: wires the Dictation controller to the window, overlay, tray, and global hotkey.

Controller callbacks arrive on worker threads; `Bridge` re-emits them as Qt signals (queued onto the UI thread).
"""
import hashlib
import logging
import sys
import threading
import time
from datetime import datetime

from PySide6.QtCore import QLockFile, QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QGuiApplication, QKeySequence, QPalette
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMenuBar, QSystemTrayIcon

from .. import benchmark, config, hotkey, permissions, platform_utils, tidy, updates
from ..controller import Dictation, Listener, State
from ..runtimes import ModelDownloadError
from ..platform_utils import IS_MAC
from . import theme
from .overlay import Overlay
from .window import CloseDialog, MainWindow, app_icon, menu_bar_icon


log = logging.getLogger(__name__)


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

    def on_state(self, state):
        self.state.emit(state.value)

    def on_progress(self, message, percent):
        self.progress.emit(message, percent)

    def on_live_text(self, text):
        self.live.emit(text)

    def on_warning(self, message):
        self.warning.emit(message)

    def on_result(self, text, note):
        self.result.emit(text, note)

    def on_error(self, message):
        self.error.emit(message)

    def on_cancelled(self):
        self.cancelled.emit()


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
        self._menu_bar = self._make_menu_bar() if IS_MAC else None
        self.palette = theme.LIGHT
        self._capturing = False
        self._setup_timer = None
        self._closed_by_user = False
        self._capture_ended = 0.0
        self._pressed_at = None  # set when a hotkey press started (or will stop) dictation
        self._use_overlay = False  # decided per dictation: Speak's own window shows progress when focused
        self._release = None       # newer release found
        self._downloading = False
        self._downloaded = None    # verified exe waiting beside ours; swapped in on quit
        self._restart = False
        self._onboarding = False   # first-run setup is showing: the global hotkey stays quiet

        b = self.bridge
        b.state.connect(self._on_state)
        b.progress.connect(self._on_progress)
        b.live.connect(self._on_live)
        b.warning.connect(lambda message: self.window.notify("audio-dimming", message, "error", timeout=12))
        b.result.connect(self._on_result)
        b.error.connect(self._on_error)
        b.hotkey_down.connect(self._on_hotkey_down)
        b.hotkey_up.connect(self._on_hotkey_up)
        b.escape.connect(self.dictation.cancel)
        b.cancelled.connect(self._on_cancelled)
        b.probed.connect(self._on_probed)
        b.update_found.connect(self._on_update_found)
        b.update_progress.connect(lambda p: self._set_update(f"{p}%", "Downloading the update…", enabled=False))
        b.update_ready.connect(self._on_update_ready)
        b.test_progress.connect(lambda message, percent: self.window.onboarding.set_progress(message, percent))
        b.test_done.connect(self.window.onboarding.set_result)
        b.test_failed.connect(self.window.onboarding.set_failure)

        w = self.window
        w.close_requested.connect(self._on_close)
        w.notice_action.connect(self._on_notice_action)
        w.setup.allow_clicked.connect(permissions.request)
        w.setup.settings_clicked.connect(permissions.open_settings)
        w.setup.restart_clicked.connect(self._relaunch)
        w.settings.check_updates.connect(lambda: self._check_updates(manual=True))
        w.settings.rerun_setup.connect(self._start_onboarding)
        w.onboarding.changed.connect(self._update)
        w.onboarding.skipped.connect(self._finish_onboarding)
        w.onboarding.finished.connect(self._finish_onboarding)
        w.onboarding.test_requested.connect(self._run_test)
        w.onboarding.test_cancelled.connect(self.dictation.cancel_benchmark)
        w.onboarding.shortcut_recording.connect(self._on_shortcut_recording)
        w.dictate.toggle_requested.connect(self.dictation.toggle)
        w.history.open_settings.connect(lambda: w.show_page(2))
        w.settings.changed.connect(self._update)
        w.settings.shortcut_changed.connect(lambda combo: self._update({"hotkey": combo}))
        w.settings.shortcut_recording.connect(self._on_shortcut_recording)
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda *_: self._apply_theme())
        if IS_MAC:  # clicking the Dock icon reopens a hidden window
            app.applicationStateChanged.connect(self._on_app_state)

        self._apply_theme()
        setup_needed = bool(permissions.missing())
        onboarding_needed = not self.settings["onboarding_done"]
        if setup_needed:
            self._start_setup()
        else:
            self._register_hotkey()
            if onboarding_needed:
                self._start_onboarding()
        w.dictate.set_shortcut(self.settings["hotkey"], self.settings["shortcut_mode"])
        w.history.refresh(self.settings["history_enabled"])
        self._refresh_tidy()
        threading.Thread(target=lambda: (tidy._probed.wait(30), b.probed.emit()), daemon=True).start()
        updates.cleanup()
        if not background and self.settings["unload_after"] != "0":  # login start: load on first use instead
            self.dictation.warm_up()
        self._update_timer = QTimer(self, interval=24 * 3600 * 1000, timeout=self._check_updates)
        self._update_timer.start()
        QTimer.singleShot(5000, self._check_updates)
        if not (background and self.tray) or setup_needed or onboarding_needed:
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
        if {"tidy", "cleanup_model", "cleanup_device", "corrections"} & changes.keys():
            self._refresh_tidy()
        if {"updates", "prereleases"} & changes.keys():
            self._check_updates()
        self.window.settings.sync(self.settings)
        self.window.onboarding.sync(self.settings)

    # ----- updates -----

    def _check_updates(self, manual: bool = False):
        if self._downloading or self._downloaded:
            return
        if self.settings["updates"] == "off" and not manual:
            self._set_update("")
            return
        if manual:
            self.window.settings.set_update_status("Checking…")
        if updates.updatable():
            self.window.settings.set_last_check(datetime.now())
        threading.Thread(target=lambda: self.bridge.update_found.emit(
            updates.newer_release(self.settings["prereleases"]), manual), daemon=True).start()

    def _on_update_found(self, release, manual: bool):
        self._release = release
        if manual:
            self.window.settings.set_update_status(f"{release.version} available" if release else "Up to date")
        if not release:
            self._set_update("")
        elif self.settings["updates"] == "auto" and updates.can_install(release):
            self._download()
        else:
            self._set_update("Update" if updates.can_install(release) else "Download",
                             f"Speak {release.version} is available.")

    def _set_update(self, label: str, message: str = "", enabled: bool = True):
        if label:
            self.window.notify("update", message, "info", label, enabled)
        else:
            self.window.clear_notice("update")

    def _on_notice_action(self, key: str):
        if key == "update":
            self._on_update_clicked()
        elif key == "permissions":
            self._start_setup()
        elif key == "restart":
            self._relaunch()

    def _download(self):
        self._downloading = True
        self._set_update("0%", "Downloading the update…", enabled=False)
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
            self._set_update("Restart to update", f"Speak {self._release.version} is ready to install.")
        else:
            self._set_update("Try again", "The update didn't download.")

    def _on_update_clicked(self):
        if self._downloaded:
            if self.dictation.state != State.IDLE:
                self.dictation.cancel()
            self._restart = True
            self.quit()
        elif updates.can_install(self._release):
            self._download()
        elif self._release:
            QDesktopServices.openUrl(QUrl(self._release.page))

    def _on_probed(self):
        device = self.settings["cleanup_device"]
        if device not in config.CLEANUP_DEVICES and not any(g.device == device for g in tidy.gpus()):
            self._update({"cleanup_device": config.DEFAULTS["cleanup_device"]})
            message = f"The saved GPU preference ({device}) is unavailable. Tidy-up device reset to Automatic."
            self.window.notify(
                "cleanup-device",
                message,
                "error",
            )
            if self.tray and not self.window.isVisible():
                self.tray.showMessage("Speak", message, QSystemTrayIcon.Warning, 4000)
        self.window.settings.set_gpus(tidy.gpus(), self.settings["cleanup_device"])
        self.window.onboarding.set_gpus(tidy.gpus(), self.settings["cleanup_device"])
        self._refresh_tidy()

    def _refresh_tidy(self):
        if tidy.probed():
            plan = tidy.plan(self.settings)
            summary, large = plan.summary, plan.model_id == config.LARGE_MODEL
        else:
            summary, large = "Checking what your computer can run…", True
        self.window.settings.set_tidy_summary(summary, large)
        self.window.onboarding.set_tidy_summary(summary, large)

    def _apply_theme(self):
        self.palette = theme.resolve(self.settings["theme"])
        self.app.setStyleSheet(theme.stylesheet(self.palette))
        links = self.app.palette()
        links.setColor(QPalette.Link, QColor(self.palette.accent))
        self.app.setPalette(links)
        self.window.dictate.set_palette(self.palette)
        self.window.settings.set_palette(self.palette)
        self.window.onboarding.set_palette(self.palette)
        self.overlay.palette_ = self.palette
        self._on_state(self.dictation.state.value, refresh_only=True)

    def _register_hotkey(self):
        try:
            hotkey.register(self.settings["hotkey"], self.bridge.hotkey_down.emit, self.bridge.hotkey_up.emit,
                            self.bridge.escape.emit, lambda: self.dictation.state != State.IDLE)
            self.window.clear_notice("restart")
        except PermissionError:
            self.window.notify("restart", "Speak can't hear your shortcut yet. Restart Speak to finish setting up.",
                               "error", "Restart Speak")
        except Exception:
            self.window.notify("restart", "That shortcut can't be used. Choose a different one in Settings.", "error")

    # ----- permissions -----

    def _start_setup(self):
        self.window.show_setup(True)
        if self._setup_timer is None:
            self._setup_timer = QTimer(self, interval=1000, timeout=self._check_setup)
        self._setup_timer.start()
        self._check_setup()

    def _check_setup(self):
        status = {p.id: permissions.granted(p.id) for p in permissions.REQUIRED}
        self.window.setup.set_status(status, self.palette)
        if all(status.values()):
            self._setup_timer.stop()
            self.window.show_setup(False)
            self.window.clear_notice("permissions")
            self._register_hotkey()
            if not self.settings["onboarding_done"]:
                self._start_onboarding()
            self.show_window()

    # ----- first-run setup -----

    def _start_onboarding(self):
        self._onboarding = True
        self.window.show_onboarding(True)
        self.show_window()

    def _finish_onboarding(self):
        self._onboarding = False
        self.window.show_onboarding(False)
        if not self.settings["onboarding_done"]:
            self._update({"onboarding_done": True})

    def _run_test(self, pcm, rate: int):
        bridge, dictation = self.bridge, self.dictation

        def run():
            try:
                if pcm is None:
                    audio, sample_rate = benchmark.read_wav(platform_utils.sample_audio_file())
                else:
                    audio, sample_rate = pcm, rate
                bridge.test_done.emit(dictation.run_benchmark(audio, sample_rate, bridge.test_progress.emit))
            except benchmark.Cancelled:
                pass
            except Exception as exc:
                log.warning("Setup test failed", exc_info=exc)
                bridge.test_failed.emit(str(exc) if isinstance(exc, (ModelDownloadError, RuntimeError))
                                        else "The test didn't work. Please try again.")
        threading.Thread(target=run, daemon=True).start()

    def _check_permissions(self):
        """After setup: warn if the user has since switched a permission off."""
        if self.window.screens.currentIndex() == 1:
            return
        missing = permissions.missing()
        if missing:
            names = " and ".join(p.title for p in missing)
            self.window.notify("permissions", f"Speak no longer has access to {names}, so dictation won't work.",
                               "error", "Fix")
        else:
            self.window.clear_notice("permissions")

    def _relaunch(self):
        platform_utils.relaunch()
        self.quit()

    def _on_shortcut_recording(self, active: bool):
        self._capturing = active
        self._capture_ended = time.monotonic()
        self._pressed_at = None

    # ----- hotkey: "hold" (release stops), "toggle" (tap again stops), "auto" (held > HOLD_SECONDS = hold) -----

    def _hotkey_blocked(self) -> bool:
        return self._capturing or time.monotonic() - self._capture_ended < CAPTURE_GRACE

    def _on_hotkey_down(self):
        if self._hotkey_blocked() or self._onboarding:
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
            self.tray.setIcon(self._tray_icon(state == State.LISTENING.value))
            self.tray.setToolTip(f"Speak · {text}")
        if refresh_only or state == State.IDLE:
            return
        self.window.dictate.set_mode(state)
        if state == State.LISTENING:
            self.window.dictate.set_live("")
        if state == State.PREPARING:
            self._use_overlay = self.settings["overlay_enabled"] and not (
                self.window.dictate.isVisible() and self.window.isActiveWindow())
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
        self.window.dictate.set_result(text)
        self.window.clear_notice("error")
        if note:
            self.window.notify("note", note, "info", timeout=8)
        else:
            self.window.clear_notice("note")
        self.window.dictate.set_mode("done")
        if self.overlay.isVisible():
            self.overlay.set_mode("done")
        if self.settings["history_enabled"]:
            self.window.history.refresh(True)

    def _on_error(self, message: str):
        self.window.dictate.set_result(self.window.dictate.text.toPlainText())
        self.window.notify("error", message, "error", timeout=12)
        self.window.dictate.set_mode("error")
        self.window.set_status("Ready", self.palette.success)
        if self.overlay.isVisible():
            self.overlay.set_mode("error")
        if self.tray and not self.window.isVisible():
            self.tray.showMessage("Speak", message, QSystemTrayIcon.Warning, 4000)

    def _on_cancelled(self):
        self.window.dictate.set_live("")
        self.window.dictate.set_mode("idle")
        self.window.clear_notice("error")
        self.window.set_status("Ready", self.palette.success)
        self.overlay.hide_now()
        self._use_overlay = False

    # ----- window / tray -----

    def _tray_icon(self, listening: bool = False):
        if IS_MAC and not listening:
            return menu_bar_icon()
        return app_icon(self.palette.danger if listening else "")

    def _make_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QSystemTrayIcon(self._tray_icon(), self)
        tray.setToolTip("Speak")
        menu = QMenu()
        menu.addAction("Open Speak", self.show_window)
        menu.addAction("Start / stop dictation", self.dictation.toggle)
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        tray.setContextMenu(menu)
        if not IS_MAC:  # on macOS a click already opens the menu
            tray.activated.connect(
                lambda reason: self.show_window() if reason == QSystemTrayIcon.Trigger else None)
        tray.show()
        self._tray_menu = menu
        return tray

    def _make_menu_bar(self):
        """Standard macOS menus; Qt moves the About/Preferences/Quit roles into the app menu."""
        bar = QMenuBar()

        def action(menu, text, slot, shortcut=None, role=None):
            act = QAction(text, self)
            act.triggered.connect(slot)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            if role:
                act.setMenuRole(role)
            menu.addAction(act)

        app_menu = bar.addMenu("Speak")
        action(app_menu, "About Speak", lambda: self._show_page(3), role=QAction.AboutRole)
        action(app_menu, "Settings…", lambda: self._show_page(2), QKeySequence.Preferences, QAction.PreferencesRole)
        action(app_menu, "Quit Speak", self.quit, QKeySequence.Quit, QAction.QuitRole)
        dictation_menu = bar.addMenu("Dictation")
        action(dictation_menu, "Start / Stop Dictation", self.dictation.toggle)
        window_menu = bar.addMenu("Window")
        action(window_menu, "Minimize", self.window.showMinimized, "Ctrl+M")
        action(window_menu, "Close", self.window.close, QKeySequence.Close)
        return bar

    def _show_page(self, index: int):
        self.show_window()
        self.window.show_page(index)

    def _on_app_state(self, state):
        if state != Qt.ApplicationActive:
            return
        if self._closed_by_user:
            self.show_window()
        hotkey.prepare()  # pick up a changed keyboard layout
        self._check_permissions()

    def show_window(self):
        self._closed_by_user = False
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
            self._closed_by_user = True
            self.window.hide()
            if self.dictation.state == State.IDLE:
                self.overlay.hide_now()
        else:
            self.quit()

    def quit(self):
        self.window.allow_close = True  # Qt 6 quit() closes windows; don't re-prompt
        hotkey.unregister()
        self.overlay.hide_now()
        self.dictation.cancel_benchmark()
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


INSTANCE_NAME = "speak-" + hashlib.sha1(str(config.APP_DIR).encode()).hexdigest()[:12]  # per user


def _single_instance(wait_ms: int):
    """Return (lock, server) if this is the only Speak, else None after asking the running one to show itself.

    Two instances would both hear the shortcut and paste every dictation twice.
    """
    config.APP_DIR.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(config.APP_DIR / "speak.lock"))
    lock.setStaleLockTime(0)  # never by age; a crashed owner's lock is still detected (dead PID) and taken over
    if not lock.tryLock(wait_ms):
        if "--background" not in sys.argv:
            socket = QLocalSocket()
            socket.connectToServer(INSTANCE_NAME)
            if socket.waitForConnected(1000):
                socket.write(b"show")
                socket.waitForBytesWritten(1000)
                socket.disconnectFromServer()
        return None
    QLocalServer.removeServer(INSTANCE_NAME)
    server = QLocalServer()
    server.listen(INSTANCE_NAME)
    return lock, server


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("Speak")
    claimed = _single_instance(15000 if "--restarted" in sys.argv else 0)
    if claimed is None:
        sys.exit(0)
    lock, server = claimed
    app.setQuitOnLastWindowClosed(False)
    if not (IS_MAC and getattr(sys, "frozen", False)):  # the bundle's .icns is the sharper Dock icon
        app.setWindowIcon(app_icon(inset=0.1 if IS_MAC else 0.0))
    hotkey.prepare()
    speak = SpeakApp(app, background="--background" in sys.argv)
    server.newConnection.connect(lambda: (server.nextPendingConnection().deleteLater(), speak.show_window()))
    app.aboutToQuit.connect(lambda: speak.dictation.shutdown())
    code = app.exec()
    server.close()
    lock.unlock()
    sys.exit(code)
