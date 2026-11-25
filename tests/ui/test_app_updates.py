from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton

from speak import config, updates
from speak.controller import State
from speak.ui import theme
from speak.ui.bridge import Bridge
from speak.ui.app import SpeakApp
from speak.ui.banner import Banner
from speak.ui.pages.settings import SettingsPage
from tests.ui import QtTestCase


class UpdateInteractionTest(QtTestCase):
    """Update checks notify users, offer the release, and never interrupt dictation when applying it."""

    def test_system_notification_announces_each_update_once_and_only_when_unfocused(self):
        app, _page, _banner = self.make_ui("notify")
        app.tray = Mock()
        release = updates.Release("1.2.0", "https://example.invalid/release")
        with patch("speak.ui.app.updates.can_install", return_value=True):
            SpeakApp._on_update_found(app, release, False)
            SpeakApp._on_update_found(app, release, False)
            self.assertEqual(1, app.tray.showMessage.call_count)
            self.assertIn("1.2.0 is available", app.tray.showMessage.call_args.args[1])

            SpeakApp._on_update_ready(app, Path("Speak.exe.new"))
            self.assertEqual(2, app.tray.showMessage.call_count)
            self.assertIn("1.2.0 is ready", app.tray.showMessage.call_args.args[1])

            app.tray.reset_mock()
            app._toasted.clear()
            app.window.isVisible = lambda: True
            app.window.isActiveWindow = lambda: True
            SpeakApp._on_update_found(app, release, False)
            app.tray.showMessage.assert_not_called()

    def make_ui(self, update_mode):
        settings = {**config.DEFAULTS, "updates": update_mode}
        with patch("speak.audio.input_devices", return_value=[]), \
                patch("speak.platform_utils.launch_at_login_enabled", return_value=False), \
                patch("speak.updates.updatable", return_value=True):
            page = SettingsPage(settings)
        banner = Banner()
        banner.resize(680, banner.sizeHint().height())
        banner.findChild(QPushButton, "primary").setMinimumWidth(140)
        banner.findChild(QPushButton, "ghost").setFixedWidth(36)
        page.show()
        banner.show()
        self.addCleanup(page.close)
        self.addCleanup(banner.close)

        app = SimpleNamespace(
            settings=settings,
            window=SimpleNamespace(
                settings=page,
                notify=lambda key, text, level="info", action="", enabled=True:
                    banner.show_notice(key, text, level, action, enabled),
                clear_notice=banner.clear,
                set_status=Mock(),
                isVisible=lambda: False,
                isActiveWindow=lambda: False,
                allow_close=False,
            ),
            palette=theme.LIGHT,
            bridge=Bridge(),
            _downloading=False,
            _downloaded=None,
            _release=None,
            _restart=False,
            _restart_when_idle=False,
            _toasted=set(),
            tray=None,
            overlay=Mock(),
            dictation=Mock(state=State.IDLE),
            app=SimpleNamespace(quit=Mock()),
        )
        app._set_update = lambda label, message="", enabled=True: SpeakApp._set_update(
            app, label, message, enabled
        )
        app._download = lambda: SpeakApp._download(app)
        app._on_update_clicked = lambda: SpeakApp._on_update_clicked(app)
        app._toast = lambda kind, version, message: SpeakApp._toast(app, kind, version, message)
        app._restart_for_update = lambda: SpeakApp._restart_for_update(app)
        app._on_state = lambda state: SpeakApp._on_state(app, state)
        app.quit = lambda: SpeakApp.quit(app)
        app.bridge.update_found.connect(lambda release, manual: SpeakApp._on_update_found(app, release, manual))
        app.bridge.update_ready.connect(lambda path: SpeakApp._on_update_ready(app, path))
        self.addCleanup(app.bridge.update_found.disconnect)
        self.addCleanup(app.bridge.update_ready.disconnect)
        page.check_updates.connect(lambda: SpeakApp._check_updates(app, manual=True))
        banner.action_clicked.connect(lambda key: SpeakApp._on_notice_action(app, key))
        return app, page, banner

    def check_button(self, page):
        return next(button for button in page.findChildren(QPushButton) if button.text() == "Check now")

    def test_manual_check_reports_available_version_and_opens_release_page(self):
        app, page, banner = self.make_ui("notify")
        release = updates.Release("1.2.0", "https://example.invalid/release")
        with patch("speak.ui.app.threading.Thread", side_effect=lambda target, **_: SimpleNamespace(start=target)), \
                patch("speak.ui.app.updates.newer_release", return_value=release), \
                patch("speak.ui.app.updates.can_install", return_value=False), \
                patch("speak.ui.app.updates.updatable", return_value=True), \
                patch("speak.ui.app.QDesktopServices.openUrl") as open_url:
            QTest.mouseClick(self.check_button(page), Qt.LeftButton)
            self.app.processEvents()

            self.capture(banner, "update-available")
            self.assertEqual("1.2.0 available", page.update_status.text())
            self.assertEqual("Speak 1.2.0 is available.", banner.findChild(type(page.update_status)).text())
            action = banner.findChild(QPushButton, "primary")
            self.assertEqual("Download", action.text())
            QTest.mouseClick(action, Qt.LeftButton)

        open_url.assert_called_once()
        self.assertEqual(release.page, open_url.call_args.args[0].toString())
        self.assertIs(app._release, release)

    def test_manual_check_reports_up_to_date_and_clears_old_update_notice(self):
        app, page, banner = self.make_ui("notify")
        banner.show_notice("update", "Old update notice", action="Download")
        with patch("speak.ui.app.threading.Thread", side_effect=lambda target, **_: SimpleNamespace(start=target)), \
                patch("speak.ui.app.updates.newer_release", return_value=None), \
                patch("speak.ui.app.updates.updatable", return_value=True):
            QTest.mouseClick(self.check_button(page), Qt.LeftButton)
            self.app.processEvents()

        self.assertEqual("Up to date", page.update_status.text())
        self.assertFalse(banner.isVisible())
        self.assertIsNone(app._release)

    def test_automatic_update_waits_for_dictation_to_finish_before_restarting(self):
        app, page, banner = self.make_ui("auto")
        release = updates.Release("1.2.0", "https://example.invalid/release")
        with patch("speak.ui.app.threading.Thread", side_effect=lambda target, **_: SimpleNamespace(start=target)), \
                patch("speak.ui.app.updates.newer_release", return_value=release), \
                patch("speak.ui.app.updates.can_install", return_value=True), \
                patch("speak.ui.app.updates.updatable", return_value=True):
            with patch("speak.ui.app.updates.download",
                       side_effect=[RuntimeError("offline"), Path("Speak.exe.new")]) as download:
                QTest.mouseClick(self.check_button(page), Qt.LeftButton)
                self.app.processEvents()
                self.assertEqual("Try again", banner.findChild(QPushButton, "primary").text())
                QTest.mouseClick(banner.findChild(QPushButton, "primary"), Qt.LeftButton)
                self.assertEqual(2, download.call_count)

            self.capture(banner, "update-ready")
            self.assertEqual("Speak 1.2.0 is ready to install.", banner.findChild(type(page.update_status)).text())
            self.assertEqual("Restart to update", banner.findChild(QPushButton, "primary").text())
            self.assertEqual(Path("Speak.exe.new"), app._downloaded)

            with tempfile.TemporaryDirectory() as directory:
                exe = Path(directory) / "Speak.exe"
                new = Path(directory) / "Speak.exe.new"
                exe.write_text("current", encoding="utf-8")
                new.write_text("updated", encoding="utf-8")
                app._downloaded = new
                app.dictation.state = State.LISTENING
                with patch("speak.ui.app.hotkey.unregister"), \
                        patch("speak.ui.app.updates.exe_path", return_value=exe), \
                        patch("speak.ui.app.updates.restart") as restart, \
                        patch("speak.ui.app.platform_utils.repoint_launch_at_login") as repoint:
                    QTest.mouseClick(banner.findChild(QPushButton, "primary"), Qt.LeftButton)

                    app.dictation.cancel.assert_not_called()
                    app.app.quit.assert_not_called()
                    restart.assert_not_called()
                    self.assertEqual("Speak will restart when your dictation finishes.",
                                     banner.findChild(type(page.update_status)).text())

                    app.dictation.state = State.IDLE
                    app._on_state(State.IDLE.value)

                    app.app.quit.assert_called_once()
                    app.dictation.cancel.assert_not_called()
                    app.dictation.shutdown.assert_called_once()
                    restart.assert_called_once_with(exe)
                    repoint.assert_called_once_with(exe, exe)
                    self.assertEqual("updated", exe.read_text(encoding="utf-8"))
                    self.assertEqual("current", Path(str(exe) + ".old").read_text(encoding="utf-8"))
                    self.assertIsNone(app._downloaded)

    def test_restart_to_update_applies_immediately_when_not_dictating(self):
        app, _page, _banner = self.make_ui("auto")
        app._release = updates.Release("1.2.0", "https://example.invalid/release")
        app._downloaded = Path("Speak.exe.new")
        with patch("speak.ui.app.hotkey.unregister"), \
                patch("speak.ui.app.updates.exe_path", return_value=Path("Speak.exe")), \
                patch("speak.ui.app.updates.install", return_value=Path("Speak.exe")), \
                patch("speak.ui.app.updates.restart") as restart, \
                patch("speak.ui.app.platform_utils.repoint_launch_at_login"):
            SpeakApp._on_update_clicked(app)

        app.dictation.cancel.assert_not_called()
        restart.assert_called_once_with(Path("Speak.exe"))

