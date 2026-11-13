from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from tests.ui import QtTestCase
from speak import config
from speak.ui.app import SpeakApp
from speak.ui.pages.settings import SettingsPage
from speak.ui import theme


class SettingsInteractionTest(QtTestCase):
    """Settings controls emit user changes and keep dependent controls in sync."""

    def make_page(self, settings=None):
        with patch("speak.audio.input_devices", return_value=[]), \
                patch("speak.platform_utils.launch_at_login_enabled", return_value=False):
            page = SettingsPage({**config.DEFAULTS, **(settings or {})})
        page.setStyleSheet(theme.stylesheet(theme.DARK))
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
        page = self.make_page({"auto_paste": True, "press_enter": True, "press_enter_before": True})
        changes = []
        page.changed.connect(changes.append)

        QTest.mouseClick(page.paste, Qt.LeftButton)

        self.capture(page, "auto-paste-disabled")
        self.assertFalse(page.enter.isEnabled())
        self.assertTrue(page.enter.isChecked())
        self.assertFalse(page.enter_before.isEnabled())
        self.assertTrue(page.enter_before.isChecked())
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

    def test_sync_reflects_every_setting_changed_elsewhere_without_emitting(self):
        page = self.make_page()
        changes = []
        page.changed.connect(changes.append)

        page.sync({**config.DEFAULTS, "mic_device": "Headset", "language": "de-DE",
                   "unload_after": "never", "corrections": False, "prereleases": True})

        self.assertEqual("Headset", page.mic.currentData())
        self.assertEqual("de-DE", page.language.currentData())
        self.assertEqual("never", page.unload.currentData())
        self.assertFalse(page.corrections.isChecked())
        self.assertTrue(page.prereleases.isChecked())
        self.assertEqual([], changes)
