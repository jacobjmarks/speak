from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from tests.ui import QtTestCase
from speak import config, platform_utils
from speak.ui.app import SpeakApp
from speak.ui.pages import settings as settings_page
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
        window = SimpleNamespace(history=Mock(), settings=Mock(), onboarding=Mock(), dictate=Mock())
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
        self.assertEqual(settings_page.ENTER_OFF_HINT, page.enter_row.hint.text())
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
        page = self.make_page()
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

    def test_reduce_by_row_appears_only_while_dimming_is_on(self):
        page = self.make_page({"audio_dim_enabled": False})
        page.show_category("indicator")
        self.assertFalse(page.audio_dim_level_row.isVisible())

        page.audio_dim.click()

        self.assertTrue(page.audio_dim_level_row.isVisible())
        self.assertTrue(page.audio_dim_slider.isEnabled())


    def test_sync_reflects_every_setting_changed_elsewhere_without_emitting(self):
        page = self.make_page()
        changes = []
        page.changed.connect(changes.append)

        page.sync({**config.DEFAULTS, "mic_device": "Headset", "language": "de-DE", "tidy": "best",
                   "unload_after": "never", "corrections": False, "prereleases": True})

        self.assertEqual("Headset", page.mic.currentData())
        self.assertEqual("de-DE", page.language.currentData())
        self.assertEqual("never", page.unload.currentData())
        self.assertFalse(page.corrections.isChecked())
        self.assertEqual(("ai", "large"), (page.tidy.value(), page.model_size.value()))
        self.assertTrue(page.prereleases.isChecked())
        self.assertEqual([], changes)


class SettingsTidyTest(QtTestCase):
    """Tidy-up is set the same way as in first-run setup: Off / Quick / Smart, then a model size and device that only
    apply to Smart, and corrections that need the Large model."""

    make_page = SettingsInteractionTest.make_page

    def test_model_size_and_device_only_apply_to_smart(self):
        page = self.make_page({"tidy": "fast"})
        changes = []
        page.changed.connect(changes.append)
        self.assertEqual("fast", page.tidy.value())
        self.assertFalse(page.model_size.isEnabled())
        self.assertEqual(config.TIDY_NOT_USED, page.device_row.hint.text())

        page.tidy.chips["ai"].click()
        page.model_size.chips["large"].click()

        self.capture(page, "smart-large")
        self.assertEqual([{"tidy": "auto", "cleanup_model": "auto"}, {"tidy": "best", "cleanup_model": "auto"}],
                         changes)
        self.assertTrue(page.model_size.isEnabled())
        self.assertEqual(config.DEVICE_HINT, page.device_row.hint.text())

    def test_corrections_read_as_off_and_explain_why_without_the_large_model(self):
        page = self.make_page({"tidy": "auto", "corrections": True})

        page.set_tidy_summary("Small model on your processor", large_model=False)

        self.assertFalse(page.corrections.isEnabled())
        self.assertFalse(page.corrections.isChecked())
        self.assertEqual(config.CORRECTIONS_NEEDS_LARGE, page.corrections_row.hint.text())
        page.set_tidy_summary("Large model on your graphics card", large_model=True)
        self.assertTrue(page.corrections.isChecked())


class SettingsMoreOptionsTest(QtTestCase):
    """Two or more technical rows sit behind their section's More options, which remembers being open and counts
    hidden rows changed from their defaults."""

    def make_page(self, settings=None):
        with patch.object(platform_utils, "IS_WINDOWS", True):  # the Enter options only exist on Windows
            return SettingsInteractionTest.make_page(self, settings)

    def test_more_options_reveals_technical_rows_and_remembers_open_sections(self):
        page = self.make_page()
        page.show_category("text")
        changes = []
        page.changed.connect(changes.append)
        self.assertFalse(page.enter.isVisible())

        QTest.mouseClick(page.sections["typing"].more, Qt.LeftButton)

        self.capture(page, "typing-more-options")
        self.assertTrue(page.enter.isVisible())
        self.assertEqual([{"expanded_sections": ["typing"]}], changes)

    def test_changed_count_tracks_hidden_settings_that_differ_from_defaults(self):
        page = self.make_page({"press_enter": True})
        typing = page.sections["typing"].more
        self.assertEqual(1, typing.changed_count)

        page.sync({**config.DEFAULTS, "press_enter_before": True, "press_enter": True})
        self.assertEqual(2, typing.changed_count)
        page.enter.click()
        self.assertEqual(1, typing.changed_count)

    def test_rows_the_platform_cannot_use_are_neither_shown_nor_searchable(self):
        with patch.object(platform_utils, "IS_WINDOWS", False):
            page = SettingsInteractionTest.make_page(self)
        page.show_category("text")

        self.assertFalse(page.enter_row.isVisible())
        self.assertFalse(page.sections["typing"].more.isVisible())
        self.assertEqual([], page.matches("enter"))


class SettingsSearchTest(QtTestCase):
    """Search finds settings by their words or synonyms and jumps to them, opening More options when needed."""

    make_page = SettingsMoreOptionsTest.make_page

    def test_return_opens_first_match_in_its_category_and_highlights_it(self):
        page = self.make_page()
        changes = []
        page.changed.connect(changes.append)

        QTest.keyClicks(page.search, "enter")

        self.assertIs(page.results_page, page.stack.currentWidget())
        self.assertEqual(["Press Enter before pasting", "Press Enter after pasting"],
                         [r.row.title for r in page.results])
        self.capture(page, "search-results")

        QTest.keyClick(page.search, Qt.Key_Return)
        self.app.processEvents()

        self.assertEqual("text", page.category)
        self.assertIs(page.pages["text"], page.stack.currentWidget())
        self.assertTrue(page.sections["typing"].expanded)
        self.assertTrue(page.enter_before.isVisible())
        self.assertIs(page.enter_before, page.focusWidget())
        self.assertTrue(page.enter_before_row.property("highlight"))
        self.assertEqual("", page.search.text())
        self.assertEqual([], changes)  # revealing a row doesn't change the saved open sections
        self.capture(page, "search-revealed-row")

    def test_opening_a_result_focuses_the_control_inside_a_wrapped_row(self):
        page = self.make_page()

        QTest.keyClicks(page.search, "language")
        QTest.keyClick(page.search, Qt.Key_Return)

        self.assertIs(page.language, page.focusWidget())

    def test_synonyms_find_settings_named_differently(self):
        page = self.make_page()

        self.assertEqual(["Runs on"], [r.title for r in page.matches("gpu")])
        self.assertEqual(config.AUDIO_DIM_LABEL, page.matches("volume")[0].title)

    def test_title_matches_rank_first_and_unknown_words_say_so(self):
        page = self.make_page()

        self.assertEqual("Microphone", page.matches("mic")[0].title)

        page.search.setText("zzz")

        self.assertEqual([], page.results)
        self.assertTrue(page.no_results.isVisible())
        self.assertIn("zzz", page.no_results.text())
        shown = []
        page.category_shown.connect(shown.append)
        QTest.keyClick(page.search, Qt.Key_Escape)
        self.assertIs(page.pages["dictation"], page.stack.currentWidget())
        self.assertEqual(["dictation"], shown)
