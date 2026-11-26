import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QPushButton

from tests.ui import QtTestCase
from speak import config
from speak.ui import theme as ui_theme
from speak.ui.window import DICTATE, SETTINGS, CloseDialog, MainWindow


class MainWindowInteractionTest(QtTestCase):
    """The sidebar holds Find a setting, Dictate, History, every settings category and About; it always marks where
    the user is, and settings can be reached from other pages."""

    def make_window(self):
        with patch("speak.audio.input_devices", return_value=[]), \
                patch("speak.platform_utils.launch_at_login_enabled", return_value=False):
            window = MainWindow({**config.DEFAULTS}, lambda: 0.0)
        window.allow_close = True  # as SpeakApp.quit does; otherwise close() is ignored and it's destroyed while shown
        window.setStyleSheet(ui_theme.stylesheet(ui_theme.DARK))
        window.show()
        self.addCleanup(window.close)
        return window

    def test_selecting_a_settings_category_opens_that_category(self):
        window = self.make_window()

        QTest.mouseClick(window.nav_buttons["text"], Qt.LeftButton)

        self.capture(window, "settings-navigation")
        self.assertIs(window.settings, window.stack.currentWidget())
        self.assertIs(window.settings.pages["text"], window.settings.stack.currentWidget())
        self.assertTrue(window.nav_buttons["text"].isChecked())

    def test_finding_a_setting_shows_results_then_marks_the_category_it_opens(self):
        window = self.make_window()

        QTest.keyClicks(window.settings.search, "memory")

        self.assertIs(window.settings, window.stack.currentWidget())
        self.assertIsNone(window.nav.checkedButton())
        self.capture(window, "find-a-setting")
        QTest.keyClick(window.settings.search, Qt.Key_Return)
        self.assertTrue(window.nav_buttons["app"].isChecked())

        QTest.mouseClick(window.nav_buttons[DICTATE], Qt.LeftButton)
        self.assertIs(window.dictate, window.stack.currentWidget())

    def test_returning_to_settings_after_leaving_a_search_shows_the_category_not_old_results(self):
        window = self.make_window()
        QTest.keyClicks(window.settings.search, "mic")
        QTest.mouseClick(window.nav_buttons[DICTATE], Qt.LeftButton)

        window.show_page(SETTINGS)

        self.assertEqual("", window.settings.search.text())
        self.assertIs(window.settings.pages[window.settings.category], window.settings.stack.currentWidget())
        self.assertTrue(window.nav_buttons[window.settings.category].isChecked())

    def test_related_settings_on_dictate_open_the_setting(self):
        window = self.make_window()

        window.dictate.links["tidy"].activated.emit()
        self.app.processEvents()

        self.assertIs(window.settings, window.stack.currentWidget())
        self.assertTrue(window.nav_buttons["text"].isChecked())
        self.assertTrue(window.settings.tidy_row.property("highlight"))

    def test_page_shortcuts_switch_pages_but_not_while_onboarding_covers_the_window(self):
        window = self.make_window()
        shortcuts = {s.key().toString(): s for s in window.findChildren(QShortcut)}

        shortcuts["Ctrl+2"].activated.emit()
        self.assertIs(window.history, window.stack.currentWidget())
        shortcuts["Ctrl+,"].activated.emit()
        self.assertIs(window.settings, window.stack.currentWidget())
        self.assertTrue(window.nav_buttons[window.settings.category].isChecked())

        window.show_onboarding(True)
        shortcuts["Ctrl+1"].activated.emit()
        self.assertIs(window.settings, window.stack.currentWidget())


class CloseDialogInteractionTest(QtTestCase):
    """The first-close prompt records the user's tray or quit choice; dismissal is neutral."""

    def test_keep_and_quit_buttons_record_their_choices(self):
        for label_prefix, expected in (("Keep in ", "tray"), ("Quit Speak", "exit")):
            with self.subTest(choice=expected):
                dialog = CloseDialog()
                dialog.setStyleSheet(ui_theme.stylesheet(ui_theme.DARK))
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
        dialog.setStyleSheet(ui_theme.stylesheet(ui_theme.DARK))
        dialog.show()
        self.addCleanup(dialog.close)
        self.capture(dialog, "dismissible-close-prompt")

        QTest.keyClick(dialog, Qt.Key_Escape)

        self.assertEqual(QDialog.DialogCode.Rejected, dialog.result())
        self.assertIsNone(dialog.choice)

if __name__ == "__main__":
    unittest.main()
