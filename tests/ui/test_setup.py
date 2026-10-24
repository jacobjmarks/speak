from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QPushButton

from tests.ui import QtTestCase
from speak import permissions
from speak.ui.pages import SetupPage
from speak.ui.theme import LIGHT


class SetupPageInteractionTest(QtTestCase):
    """Permission setup routes allow, settings, and restart actions to the app."""

    def test_permission_actions_emit_the_selected_permission_and_restart(self):
        permission = permissions.Permission("microphone", "Microphone", "Needed to hear speech.", "Privacy_Microphone")
        with patch("speak.ui.pages.permissions.REQUIRED", (permission,)):
            page = SetupPage()
        page.show()
        self.addCleanup(page.close)
        allowed, settings, restarted = [], [], []
        page.allow_clicked.connect(allowed.append)
        page.settings_clicked.connect(settings.append)
        page.restart_clicked.connect(lambda: restarted.append(True))
        buttons = page.findChildren(QPushButton)
        allow = next(button for button in buttons if button.text() == "Allow")
        open_settings = next(button for button in buttons if button.text() == "Open Settings")
        restart = next(button for button in buttons if button.text() == "Restart Speak")

        self.capture(page, "permissions-needed")
        QTest.mouseClick(allow, Qt.LeftButton)
        QTest.mouseClick(open_settings, Qt.LeftButton)
        QTest.mouseClick(restart, Qt.LeftButton)

        self.assertEqual(["microphone"], allowed)
        self.assertEqual(["microphone"], settings)
        self.assertEqual([True], restarted)

    def test_granted_permission_hides_actions_and_marks_status(self):
        permission = permissions.Permission("microphone", "Microphone", "Needed to hear speech.", "Privacy_Microphone")
        with patch("speak.ui.pages.permissions.REQUIRED", (permission,)):
            page = SetupPage()
        page.show()
        self.addCleanup(page.close)
        page.set_status({"microphone": True}, LIGHT)
        self.capture(page, "permission-granted")
        mark = next(label for label in page.findChildren(QLabel) if label.text() == "✓")
        buttons = page.findChildren(QPushButton)
        allow = next(button for button in buttons if button.text() == "Allow")
        open_settings = next(button for button in buttons if button.text() == "Open Settings")

        self.assertEqual("✓", mark.text())
        self.assertFalse(allow.isVisible())
        self.assertFalse(open_settings.isVisible())
