from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from tests.ui import QtTestCase
from speak import config
from speak.ui.app import SpeakApp
from speak.ui.pages import HistoryEntry, HistoryPage, SettingsPage


class SettingsInteractionTest(QtTestCase):
    """Settings controls emit user changes and keep dependent controls in sync."""

    def make_page(self, settings=None):
        with patch("speak.ui.pages.audio.input_devices", return_value=[]), \
                patch("speak.ui.pages.platform_utils.launch_at_login_enabled", return_value=False):
            page = SettingsPage({**config.DEFAULTS, **(settings or {})})
        page.show()
        self.addCleanup(page.close)
        return page

    def test_turning_on_history_persists_setting_and_refreshes_history_view(self):
        page = self.make_page()
        window = SimpleNamespace(history=Mock(), settings=Mock())
        app = SimpleNamespace(settings={**config.DEFAULTS}, dictation=Mock(), window=window)
        page.changed.connect(lambda changes: SpeakApp._update(app, changes))

        with patch.object(config, "save_settings") as save:
            QTest.mouseClick(page.history, Qt.LeftButton)

        self.assertTrue(app.settings["history_enabled"])
        save.assert_called_once_with(app.settings)
        app.dictation.settings_changed.assert_called_once()
        window.history.refresh.assert_called_once_with(True)
        window.settings.sync.assert_called_once_with(app.settings)

    def test_disabling_auto_paste_disables_enter_without_changing_enter_preference(self):
        page = self.make_page({"auto_paste": True, "press_enter": True})
        changes = []
        page.changed.connect(changes.append)

        QTest.mouseClick(page.paste, Qt.LeftButton)

        self.assertFalse(page.enter.isEnabled())
        self.assertTrue(page.enter.isChecked())
        self.assertEqual([{"auto_paste": False}], changes)

    def test_audio_level_key_adjustment_emits_snapped_value_and_updates_label(self):
        page = self.make_page({"audio_dim_enabled": True, "audio_dim_percent": 35})
        changes = []
        page.changed.connect(changes.append)
        page.audio_dim_slider.setFocus()

        QTest.keyClick(page.audio_dim_slider, Qt.Key_Right)

        self.assertEqual(40, page.audio_dim_slider.value())
        self.assertEqual("40%", page.audio_dim_value.text())
        self.assertEqual([{"audio_dim_percent": 40}], changes)

    def test_shortcut_mode_selection_emits_the_selected_behavior(self):
        page = self.make_page()
        changes = []
        page.changed.connect(changes.append)
        page.shortcut_mode.setFocus()

        QTest.keyClick(page.shortcut_mode, Qt.Key_End)

        self.assertEqual("toggle", page.shortcut_mode.currentData())
        self.assertEqual([{"shortcut_mode": "toggle"}], changes)

    def test_advanced_toggle_reveals_technical_settings_and_emits_preference(self):
        page = self.make_page()
        changes = []
        page.changed.connect(changes.append)
        self.assertFalse(page.asr_model.parentWidget().isVisible())

        QTest.mouseClick(page.advanced_toggle, Qt.LeftButton)

        self.assertTrue(page.asr_model.parentWidget().isVisible())
        self.assertEqual([{"advanced_settings": True}], changes)


class HistoryInteractionTest(QtTestCase):
    """History actions clear saved entries and expose the empty state."""

    def test_clear_button_removes_rows_and_shows_empty_state(self):
        page = HistoryPage()
        page.show()
        self.addCleanup(page.close)
        with patch("speak.ui.pages.history.recent", side_effect=[
            [("2026-01-01T10:00:00+00:00", "A saved dictation")], []
        ]), patch("speak.ui.pages.history.clear") as clear:
            page.refresh(enabled=True)
            self.assertTrue(page.clear_button.isVisible())

            QTest.mouseClick(page.clear_button, Qt.LeftButton)
            self.app.processEvents()

        clear.assert_called_once()
        self.assertFalse(page.clear_button.isVisible())
        self.assertEqual("Nothing yet", page.empty_label.text())

    def test_selecting_a_saved_entry_copies_its_transcript(self):
        page = HistoryPage()
        page.show()
        self.addCleanup(page.close)
        with patch("speak.ui.pages.history.recent",
                   return_value=[("2026-01-01T10:00:00+00:00", "A saved dictation")]):
            page.refresh(enabled=True)
        entry = page.findChild(HistoryEntry)

        with patch("speak.ui.pages.output.copy") as copy:
            QTest.mouseClick(entry, Qt.LeftButton)

        copy.assert_called_once_with("A saved dictation")
