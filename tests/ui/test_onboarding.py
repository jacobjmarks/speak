from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from speak import config
from speak.ui import onboarding
from tests.ui.onboarding_support import OnboardingCase, button, result


class OnboardingPageTest(OnboardingCase):
    """First-run setup goes welcome -> mic -> shortcut -> tidy + speed test -> indicator -> look and updates ->
    done. Choices apply live; tidy options that don't apply are greyed out; changing a tidy option cancels the
    running speed test and re-runs it."""

    def test_welcome_starts_the_flow_and_mic_step_hears_you(self):
        page = self.make()
        self.capture(page, "welcome")
        QTest.mouseClick(button(page, "Get started"), Qt.LeftButton)
        self.assertEqual(page.THEME, page.steps.currentIndex())
        page.go(page.MIC)

        page._read_level()
        self.capture(page, "microphone")

        self.assertEqual(page.MIC, page.steps.currentIndex())
        self.assertEqual("Got you", page.mic_status.text())

    def test_returning_to_the_mic_step_starts_a_fresh_check(self):
        page = self.make()
        page.go(page.MIC)
        page._read_level()
        self.assertEqual("Got you", page.mic_status.text())

        page.go(page.KEYS)
        self.mic.return_value.level = 0.0
        page.go(page.MIC)

        self.assertEqual("Say something", page.mic_status.text())
        self.assertFalse(page._heard)

    def test_try_again_rechecks_the_same_device(self):
        page = self.make()
        page.go(page.MIC)
        page._read_level()
        self.mic.reset_mock()
        self.mic.return_value.level = 0.0

        QTest.mouseClick(button(page, "Try again"), Qt.LeftButton)

        self.assertEqual("Say something", page.mic_status.text())
        self.assertIsNone(self.mic.call_args.args[1])
        self.mic.return_value.start.assert_called_once()

    def test_unopenable_microphone_is_explained(self):
        page = self.make()
        self.mic.side_effect = OSError

        page.go(page.MIC)

        self.assertIn("Couldn't open", page.mic_status.text())

    def test_shortcut_mode_and_dimming_are_emitted(self):
        page = self.make()
        changes = []
        page.changed.connect(changes.append)
        page.go(page.KEYS)

        page.shortcut.captured.emit("f9")
        page.mode_options.cards["toggle"].click()
        page.dim_toggle.setChecked(True)
        page.dim_slider.setValue(60)
        self.capture(page, "shortcut")

        self.assertEqual([{"hotkey": "f9"}, {"shortcut_mode": "toggle"}, {"audio_dim_enabled": True},
                          {"audio_dim_percent": 60}], changes)

    def test_theme_is_the_first_step_and_updates_include_prereleases(self):
        page = self.make()
        changes = []
        page.changed.connect(changes.append)
        page.go(page.THEME)
        page.theme_options.cards["Dark"].click()
        self.capture(page, "theme")
        page.go(page.APP)

        page.updates_options.cards["notify"].click()
        page.prereleases.setChecked(True)
        self.capture(page, "app")

        self.assertEqual([{"theme": "Dark"}, {"updates": "notify"}, {"prereleases": True}], changes)
        self.assertEqual("Best fit", page.model_options.chips["auto"].sub)
        self.assertEqual("Uses ~4 GB", page.model_options.chips["large"].sub)

    def test_ai_card_applies_the_chosen_model(self):
        page = self.make()
        changes = []
        page.changed.connect(changes.append)
        page.go(page.TIDY)

        page.model_options.chips["small"].click()
        page.tidy_options.cards["fast"].click()
        page.tidy_options.cards["ai"].click()   # remembers Small
        page.model_options.chips["large"].click()

        self.assertEqual([{"tidy": "auto", "cleanup_model": config.SMALL_MODEL}, {"tidy": "fast"},
                          {"tidy": "auto", "cleanup_model": config.SMALL_MODEL},
                          {"tidy": "best", "cleanup_model": "auto"}], changes)

    def test_options_that_do_not_apply_are_disabled_and_say_so(self):
        page = self.make()
        page.go(page.TIDY)

        page.tidy_options.cards["fast"].click()
        self.capture(page, "tidy_quick")

        for row in (page.model_row, page.device_row, page.corrections_row):
            self.assertFalse(row.isEnabled())
            self.assertEqual("Not used with Off or Quick", row.hint.text())

        page.tidy_options.cards["ai"].click()
        self.assertTrue(page.model_row.isEnabled())
        self.assertTrue(page.corrections_row.isEnabled())

        page.model_options.chips["small"].click()
        self.capture(page, "tidy_small")
        self.assertFalse(page.corrections_row.isEnabled())
        self.assertFalse(page.corrections.isChecked())   # shows the truth: not applied
        self.assertEqual("Needs the Large model", page.corrections_row.hint.text())
        page.model_options.chips["large"].click()
        self.assertTrue(page.corrections.isChecked())    # stored choice returns

    def test_ai_example_follows_the_fix_changes_of_mind_setting(self):
        page = self.make()
        page.go(page.TIDY)
        self.assertIn(onboarding.EXAMPLE_SMART, page.level_cards["ai"].example_label.text())

        page.corrections.setChecked(False)
        self.capture(page, "tidy_literal")

        self.assertIn(onboarding.EXAMPLE_LITERAL, page.level_cards["ai"].example_label.text())

    def test_result_fills_the_speed_strip_and_changing_a_choice_retests(self):
        page = self.make()
        page.go(page.TIDY)
        requests, cancels = [], []
        page.test_requested.connect(lambda pcm, rate: requests.append(pcm))
        page.test_cancelled.connect(lambda: cancels.append(1))
        QTest.mouseClick(button(page, "Test speed"), Qt.LeftButton)

        page.set_result(result())
        self.capture(page, "result")
        self.assertEqual("0.5 s", page.latency_label.text())
        self.assertEqual("Fast", page.verdict_label.text())
        self.assertEqual("done", page.test_stage._phase[0])
        self.assertIn("Tidy-up: Quick", page.details_label.text())
        self.assertFalse(page.details_box.isVisible())
        QTest.mouseClick(button(page, "Details"), Qt.LeftButton)
        self.capture(page, "result_details")
        self.assertTrue(page.details_box.isVisible())
        page.tidy_options.cards["off"].click()

        self.assertEqual([], cancels)    # nothing was running
        self.assertTrue(page._retest.isActive())
        page._retest_now()
        self.assertEqual([None, None], requests)

    def test_change_during_a_running_test_cancels_it_and_ignores_its_late_result(self):
        page = self.make()
        page.go(page.TIDY)
        order = []
        page.test_cancelled.connect(lambda: order.append("cancel"))
        page.changed.connect(lambda change: order.append("change"))
        page._start_test()

        page.tidy_options.cards["fast"].click()
        page.set_result(result(2.0))   # the cancelled run still reports back
        page.set_progress("Loading", 50)

        self.assertEqual(["cancel", "change"], order)
        self.assertEqual(("preparing", "Updating"), page.test_stage._phase)
        self.assertTrue(page._retest.isActive())

    def test_leaving_the_tidy_step_cancels_a_running_test(self):
        page = self.make()
        page.go(page.TIDY)
        cancels = []
        page.test_cancelled.connect(lambda: cancels.append(1))
        page._start_test()

        page.go(page.LOOK)

        self.assertEqual([1], cancels)
        self.assertEqual(page.SPEED_IDLE, page.verdict_label.text())
        self.assertTrue(page.sample_button.isEnabled())

    def test_speed_stage_shows_the_indicator_for_each_test_phase(self):
        page = self.make()
        page.go(page.TIDY)
        self.assertEqual("idle", page.test_stage._phase[0])
        self.capture(page, "speed_idle")
        QTest.mouseClick(button(page, "Test speed"), Qt.LeftButton)
        self.assertEqual("preparing", page.test_stage._phase[0])
        self.capture(page, "speed_preparing")

        page.set_progress("Downloading", 40)
        self.assertEqual(("preparing", "Downloading 40%"), page.test_stage._phase)
        page.set_progress("Listening to the sample")
        self.assertEqual("listening", page.test_stage._phase[0])
        self.capture(page, "speed_listening")
        page.set_progress("Tidying up")
        self.assertEqual("processing", page.test_stage._phase[0])
        self.capture(page, "speed_processing")
        page.set_result(result())
        self.capture(page, "speed_done")

    def test_failed_test_reenables_the_buttons_with_message(self):
        page = self.make()
        page.go(page.TIDY)
        QTest.mouseClick(button(page, "Test speed"), Qt.LeftButton)

        page.set_failure("Download failed.")

        self.assertEqual(("idle", "Download failed."), page.test_stage._phase)
        self.assertTrue(page.next_button.isEnabled())
        self.assertTrue(page.sample_button.isEnabled())

    def test_indicator_options_emit_live_text_and_position_and_update_the_stage(self):
        page = self.make()
        changes = []
        page.changed.connect(changes.append)
        page.go(page.LOOK)

        page.live_options.chips["full"].click()
        page.position_options.chips["top"].click()
        self.capture(page, "indicator_top_full")
        page.position_options.chips["bottom"].click()
        self.capture(page, "indicator_bottom_full")
        page.live_options.chips["off"].click()
        page.position_options.chips["cursor"].click()
        self.capture(page, "indicator_cursor_off")

        self.assertEqual({"live_preview": "full"}, changes[0])
        self.assertEqual({"overlay_position": "top"}, changes[1])
        self.assertEqual(("off", "cursor"), (page.stage.live, page.stage.position))

    def test_skip_and_finish_signal_the_app_and_done_points_to_settings(self):
        page = self.make()
        events = []
        page.skipped.connect(lambda: events.append("skip"))
        page.finished.connect(lambda: events.append("finish"))

        QTest.mouseClick(button(page, "Skip setup"), Qt.LeftButton)
        page.go(page.DONE)
        self.capture(page, "done")
        QTest.mouseClick(button(page, "Finish"), Qt.LeftButton)

        self.assertEqual(["skip", "finish"], events)
        self.assertIn("Settings page", page.more_note.text())


class OnboardingPageDarkTest(OnboardingPageTest):
    """Same flow in the dark theme."""

    theme = "Dark"
