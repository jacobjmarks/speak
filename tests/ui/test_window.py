import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QPushButton

from tests.ui import QtTestCase
from speak import config
from speak.ui.window import CloseDialog, MainWindow


class MainWindowInteractionTest(QtTestCase):
    """Sidebar navigation selects the requested user-facing page."""

    def test_selecting_settings_navigation_opens_settings_page(self):
        with patch("speak.ui.pages.audio.input_devices", return_value=[]), \
                patch("speak.ui.pages.platform_utils.launch_at_login_enabled", return_value=False):
            window = MainWindow({**config.DEFAULTS}, lambda: 0.0)
        window.show()
        self.addCleanup(window.close)

        QTest.mouseClick(window.nav.button(2), Qt.LeftButton)

        self.capture(window, "settings-navigation")
        self.assertIs(window.stack.currentWidget(), window.settings)
        self.assertTrue(window.nav.button(2).isChecked())


class CloseDialogInteractionTest(QtTestCase):
    """The first-close prompt records the user's tray or quit choice; dismissal is neutral."""

    def test_keep_and_quit_buttons_record_their_choices(self):
        for label_prefix, expected in (("Keep in ", "tray"), ("Quit Speak", "exit")):
            with self.subTest(choice=expected):
                dialog = CloseDialog()
                dialog.show()
                self.addCleanup(dialog.close)
                button = next(button for button in dialog.findChildren(QPushButton)
                              if button.text().startswith(label_prefix))
                self.capture(dialog, f"{expected}-choice")

                QTest.mouseClick(button, Qt.LeftButton)

                self.assertEqual(QDialog.DialogCode.Accepted, dialog.result())
                self.assertEqual(expected, dialog.choice)

    def test_escape_dismisses_without_persisting_a_choice(self):
        dialog = CloseDialog()
        dialog.show()
        self.addCleanup(dialog.close)
        self.capture(dialog, "dismissible-close-prompt")

        QTest.keyClick(dialog, Qt.Key_Escape)

        self.assertEqual(QDialog.DialogCode.Rejected, dialog.result())
        self.assertIsNone(dialog.choice)

if __name__ == "__main__":
    unittest.main()
