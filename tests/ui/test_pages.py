from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QPushButton

from tests.ui import QtTestCase
from speak import config
from speak.ui.app import SpeakApp
from speak.ui.pages import HistoryEntry, HistoryPage, SettingRow, SettingsPage
from speak.ui import theme


class SettingRowConstructionTest(QtTestCase):
    """A visible hint remains parented instead of flashing as a top-level window."""

    def test_nonempty_hint_is_never_shown_without_its_row_parent(self):
        orphan_shows = []

        class ShowSpy(QObject):
            def eventFilter(self, watched, event):
                if (event.type() == QEvent.Show and isinstance(watched, QLabel)
                        and watched.text() == "Hint" and watched.parentWidget() is None):
                    orphan_shows.append(watched)
                return False

        spy = ShowSpy(self.app)
        self.app.installEventFilter(spy)
        try:
            row = SettingRow("Title", "Hint", QPushButton("Control"))
        finally:
            self.app.removeEventFilter(spy)

        self.assertEqual([], orphan_shows)
        self.assertIs(row.hint.parentWidget(), row)


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
        window = SimpleNamespace(history=Mock(), settings=Mock(), onboarding=Mock())
        app = SimpleNamespace(settings={**config.DEFAULTS}, dictation=Mock(), window=window)
        page.changed.connect(lambda changes: SpeakApp._update(app, changes))

        with patch.object(config, "save_settings") as save:
            QTest.mouseClick(page.history, Qt.LeftButton)

        self.capture(page, "history-enabled")
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

        self.capture(page, "auto-paste-disabled")
        self.assertFalse(page.enter.isEnabled())
        self.assertTrue(page.enter.isChecked())
        self.assertEqual([{"auto_paste": False}], changes)

    def test_audio_level_key_adjustment_emits_snapped_value_and_updates_label(self):
        page = self.make_page({"audio_dim_enabled": True, "audio_dim_percent": 35})
        changes = []
        page.changed.connect(changes.append)
        page.audio_dim_slider.setFocus()

        QTest.keyClick(page.audio_dim_slider, Qt.Key_Right)

        self.capture(page, "audio-dim-adjusted")
        self.assertEqual(40, page.audio_dim_slider.value())
        self.assertEqual("40%", page.audio_dim_value.text())
        self.assertEqual([{"audio_dim_percent": 40}], changes)

    def test_shortcut_mode_selection_emits_the_selected_behavior(self):
        page = self.make_page()
        changes = []
        page.changed.connect(changes.append)
        page.shortcut_mode.setFocus()

        QTest.keyClick(page.shortcut_mode, Qt.Key_End)

        self.capture(page, "toggle-shortcut-mode")
        self.assertEqual("toggle", page.shortcut_mode.currentData())
        self.assertEqual([{"shortcut_mode": "toggle"}], changes)

    def test_language_dropdown_selects_any_model_language_and_is_not_editable(self):
        page = self.make_page({"advanced_settings": True})
        changes = []
        page.changed.connect(changes.append)

        self.assertFalse(page.language.isEditable())
        self.assertEqual(set(config.TRANSCRIPTION_READY_LANGUAGES), {
            "en-US", "en-GB", "es-US", "es-ES", "fr-FR", "fr-CA", "it-IT", "pt-BR", "pt-PT",
            "nl-NL", "de-DE", "tr-TR", "ru-RU", "ar-AR", "hi-IN", "ja-JP", "ko-KR", "vi-VN",
            "uk-UA",
        })
        self.assertEqual(33, len(config.LANGUAGES))
        self.assertEqual(set(config.LANGUAGES), {page.language.itemData(i)
                                                  for i in range(page.language.count())
                                                  if page.language.itemData(i) is not None})
        transcription_header = page.language.findText("Transcription-ready")
        broad_header = page.language.findText("Broad coverage")
        self.assertLess(transcription_header, page.language.findData("en-US"))
        self.assertGreater(broad_header, page.language.findData("uk-UA"))
        self.assertFalse(page.language.model().item(transcription_header).flags() & Qt.ItemIsSelectable)
        self.assertFalse(page.language.model().item(broad_header).flags() & Qt.ItemIsSelectable)
        self.assertEqual("English (US)", page.language.itemText(page.language.findData("en-US")))
        self.assertEqual("French (Canada)", page.language.itemText(page.language.findData("fr-CA")))

        page.language.setFocus()
        QTest.keyClick(page.language, Qt.Key_U)

        self.assertEqual("uk-UA", page.language.currentData())
        self.assertEqual([{"language": "uk-UA"}], changes)
        page.set_palette(theme.DARK)
        page.language.showPopup()
        self.app.processEvents()
        page.language.view().scrollTo(page.language.model().index(0, 0))
        self.capture(page.language.view(), "language-dropdown")
        page.language.hidePopup()
        self.app.processEvents()
        self.capture(page.language.parentWidget(), "language-selected")

    def test_advanced_toggle_reveals_technical_settings_and_emits_preference(self):
        page = self.make_page()
        changes = []
        page.changed.connect(changes.append)
        self.assertFalse(page.asr_model.parentWidget().isVisible())

        QTest.mouseClick(page.advanced_toggle, Qt.LeftButton)

        self.capture(page, "advanced-settings")
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
            self.capture(page, "history-before-clear")

            QTest.mouseClick(page.clear_button, Qt.LeftButton)
            self.app.processEvents()

            self.capture(page, "history-after-clear")
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
        self.capture(page, "saved-history-entry")

        with patch("speak.ui.pages.output.copy") as copy:
            QTest.mouseClick(entry, Qt.LeftButton)

        copy.assert_called_once_with("A saved dictation")
