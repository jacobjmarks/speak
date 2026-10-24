import unittest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QPushButton

from tests.ui import QtTestCase
from speak.ui.banner import Banner


class BannerInteractionTest(QtTestCase):
    """Visible banner actions identify their notice, prioritize errors, and dismiss correctly."""

    def test_action_emits_key_and_dismiss_removes_notice(self):
        banner = Banner()
        banner.show_notice("update", "A new version is ready", action="Restart")
        banner.show()
        self.addCleanup(banner.close)
        actions = []
        banner.action_clicked.connect(actions.append)

        self.capture(banner, "update-action")
        QTest.mouseClick(banner.findChild(QPushButton, "primary"), Qt.LeftButton)

        self.assertEqual(["update"], actions)
        self.assertTrue(banner.isVisible())
        dismiss = next(button for button in banner.findChildren(QPushButton) if button.toolTip() == "Dismiss")
        QTest.mouseClick(dismiss, Qt.LeftButton)
        self.assertFalse(banner.isVisible())

    def test_error_notice_precedes_info_and_info_returns_after_error_is_cleared(self):
        banner = Banner()
        banner.show_notice("update", "Update ready")
        banner.show_notice("permission", "Permission missing", level="error")
        banner.show()
        self.addCleanup(banner.close)

        self.capture(banner, "error-priority")
        self.assertEqual("Permission missing", banner.findChild(QLabel).text())
        banner.clear("permission")
        self.assertTrue(banner.isVisible())
        self.assertEqual("Update ready", banner.findChild(QLabel).text())


if __name__ == "__main__":
    unittest.main()
