"""Step-by-step behaviour of the onboarding page (animation off: screens are complete the moment they appear)."""
from unittest.mock import patch

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from speak import config, hotkey, tidy
from speak.ui import theme as ui_theme
from speak.ui.onboarding import common
from tests.ui.onboarding_support import (GPU, STEP_NAMES, OnboardingCase, button, cpu_plan, distinct_colours,
                                         low_memory_plan, result, wait_for)


class NavigationTest(OnboardingCase):
    """The flow is eight screens; every one renders inside the window, the chrome (Skip, Back, dots) follows the
    step, and Next/Back/Get started move one screen at a time."""

    def test_every_step_renders_completely_inside_the_window(self):
        page = self.make()
        for index, name in enumerate(STEP_NAMES):
            with self.subTest(step=name):
                page.go(index)
                self.capture(page, f"step{index}_{name}")
                self.assertEqual(index, page.steps.currentIndex())
                self.assertGreater(distinct_colours(page), 8)
                for widget in page._reveals[index]:
                    top_left = widget.mapTo(page, QPoint(0, 0))
                    self.assertTrue(page.rect().contains(top_left), (name, widget))
                    self.assertTrue(page.rect().contains(top_left + QPoint(widget.width() - 1, widget.height() - 1)),
                                    (name, widget))

    def test_chrome_follows_the_step(self):
        page = self.make()
        expected = {page.WELCOME: (False, True, False), page.THEME: (True, True, False),
                    page.APP: (True, True, True), page.DONE: (False, False, False)}
        for index, (bar, skip, back) in expected.items():
            page.go(index)
            self.assertEqual((bar, skip, back),
                             (page.bar.isVisible(), page.skip_button.isVisible(), page.back_button.isVisible()), index)
        page.go(page.MIC)
        self.assertEqual(page.MIC - page.THEME, page.dots._value)

    def test_get_started_next_and_back_walk_one_step_at_a_time(self):
        page = self.make()
        QTest.mouseClick(button(page, "Get started"), Qt.LeftButton)
        seen = [page.steps.currentIndex()]
        while page.steps.currentIndex() < page.APP:
            QTest.mouseClick(page.next_button, Qt.LeftButton)
            seen.append(page.steps.currentIndex())
        QTest.mouseClick(page.next_button, Qt.LeftButton)
        seen.append(page.steps.currentIndex())
        for _ in range(3):
            QTest.mouseClick(page.back_button, Qt.LeftButton)
            seen.append(page.steps.currentIndex())

        self.assertEqual([1, 2, 3, 4, 5, 6, 7, 6, 5, 4], seen)

    def test_go_clamps_to_the_first_and_last_step(self):
        page = self.make()
        page.go(99)
        self.assertEqual(page.DONE, page.steps.currentIndex())
        page.go(-4)
        self.assertEqual(page.WELCOME, page.steps.currentIndex())

    def test_reset_returns_to_welcome_with_a_clean_test_and_mic_check(self):
        page = self.make()
        cancels = []
        page.test_cancelled.connect(lambda: cancels.append(1))
        page.go(page.MIC)
        page._read_level()
        page.go(page.TIDY)
        page._start_test()
        page.go(page.DONE)

        page.reset()

        self.capture(page, "after_reset")
        self.assertEqual(page.WELCOME, page.steps.currentIndex())
        self.assertEqual([1], cancels)
        self.assertFalse(page._heard)
        self.assertEqual("idle", page.test_stage._phase[0])

    def test_hiding_cancels_a_running_test_and_stops_the_mic_and_showing_resumes_the_mic(self):
        page = self.make()
        cancels = []
        page.test_cancelled.connect(lambda: cancels.append(1))
        page.go(page.TIDY)
        page._start_test()
        page.hide()
        self.assertEqual([1], cancels)
        self.assertFalse(page.ambient._timer.isActive())
        page.show()

        page.go(page.MIC)
        self.assertEqual(1, self.mic.call_count)
        page.hide()
        self.assertFalse(page._poll.isActive())
        self.mic.return_value.stop.assert_called()
        page.show()

        self.assertEqual(2, self.mic.call_count)
        self.assertTrue(page._poll.isActive())

    def test_welcome_waves_only_play_on_the_welcome_screen(self):
        page = self.make()
        self.assertTrue(page.ambient._timer.isActive())
        page.go(page.THEME)
        self.assertFalse(page.ambient._timer.isActive())


class SyncTest(OnboardingCase):
    """Settings changed elsewhere (the app echoes every change) are reflected in every control without emitting."""

    def test_every_control_reflects_synced_settings_without_emitting(self):
        page = self.make()
        changes = []
        page.changed.connect(changes.append)
        settings = {**config.DEFAULTS, "tidy": "best", "cleanup_model": "auto", "cleanup_device": "cpu",
                    "corrections": False, "live_preview": "off", "overlay_position": "bottom",
                    "shortcut_mode": "hold", "theme": "Dark", "updates": "off", "prereleases": True,
                    "hotkey": "f8", "audio_dim_enabled": True, "audio_dim_percent": 40}

        page.sync(settings)
        for index in (page.TIDY, page.KEYS, page.LOOK, page.APP, page.THEME):
            page.go(index)
            self.capture(page, f"synced_{STEP_NAMES[index]}")

        self.assertEqual([], changes)
        self.assertTrue(page.level_cards["ai"].isChecked())
        self.assertTrue(page.model_options.chips["large"].isChecked())
        self.assertEqual("cpu", page.device.currentData())
        self.assertFalse(page.corrections.isChecked())
        self.assertTrue(page.live_options.chips["off"].isChecked())
        self.assertTrue(page.position_options.chips["bottom"].isChecked())
        self.assertEqual(("off", "bottom"), (page.stage.live, page.stage.position))
        self.assertTrue(page.mode_options.cards["hold"].isChecked())
        self.assertTrue(page.theme_options.cards["Dark"].isChecked())
        self.assertTrue(page.updates_options.cards["off"].isChecked())
        self.assertTrue(page.prereleases.isChecked())
        self.assertEqual("f8", page.shortcut.combo)
        self.assertTrue(page.dim_toggle.isChecked())
        self.assertTrue(page.dim_slider.isEnabled())
        self.assertEqual((40, "40%"), (page.dim_slider.value(), page.dim_value.text()))
        self.assertEqual(hotkey.display("f8"), page.keycap.text())

    def test_turning_tidy_off_elsewhere_keeps_the_remembered_model_choice(self):
        page = self.make({"tidy": "auto", "cleanup_model": config.SMALL_MODEL})
        self.assertEqual("small", page._model)

        page.sync({**config.DEFAULTS, "tidy": "off", "cleanup_model": "auto"})
        page.go(page.TIDY)

        self.assertEqual("small", page._model)
        self.assertTrue(page.level_cards["off"].isChecked())
        self.assertEqual("", next((k for k, c in page.model_options.chips.items() if c.isChecked()), ""))

    def test_unknown_device_falls_back_to_the_first_entry(self):
        page = self.make()

        page.sync({**config.DEFAULTS, "cleanup_device": "Vulkan7"})

        self.assertEqual(0, page.device.currentIndex())

    def test_new_palette_reaches_every_painted_widget(self):
        page = self.make()
        dark = ui_theme.DARK

        page.set_palette(dark)

        for widget in (page.dots, page.pulse, page.burst, page.stage, page.test_stage, page.stage._overlay,
                       page.test_stage._overlay, *page.theme_cards, *page.mode_cards,
                       *page.model_options.chips.values()):
            self.assertIs(dark, widget.palette_, widget)
        self.assertIs(dark, page.palette_)

    def test_tidy_summary_and_gpu_list_refresh_the_tidy_card(self):
        page = self.make()

        page.set_tidy_summary("whatever", True)
        page.set_gpus([GPU], "Vulkan0")
        page.go(page.TIDY)

        self.assertEqual("Vulkan0", page.device.currentData())
        self.assertIn("GPU: Test GPU 8GB", [page.device.itemText(i) for i in range(page.device.count())])

    def test_a_saved_gpu_that_vanished_is_listed_as_unavailable_and_kept(self):
        page = self.make()

        page.set_gpus([], "Vulkan9")

        self.assertEqual("GPU: Unavailable (Vulkan9)", page.device.currentText())
        self.assertEqual("Vulkan9", page.device.currentData())


class WelcomeAndThemeTest(OnboardingCase):
    """Welcome starts the flow; each theme card applies its theme and shows its own miniature."""

    def test_welcome_shows_the_title_and_starts_the_flow(self):
        page = self.make()
        self.capture(page, "welcome")

        QTest.mouseClick(button(page, "Get started"), Qt.LeftButton)

        self.assertEqual(page.THEME, page.steps.currentIndex())

    def test_picking_each_theme_emits_it_and_checks_only_that_card(self):
        page = self.make()
        changes = []
        page.changed.connect(changes.append)
        page.go(page.THEME)
        self.capture(page, "theme_initial")

        for name in config.THEMES:
            page.theme_options.cards[name].click()
            self.capture(page, f"theme_{name.lower()}")
            self.assertEqual([n for n in config.THEMES if page.theme_options.cards[n].isChecked()], [name])

        self.assertEqual([{"theme": n} for n in config.THEMES], changes)


class MicStepTest(OnboardingCase):
    """The mic step listens as soon as it appears: silence keeps asking, a voice turns the mic into a check and
    offers a retry, and a broken or changed device is handled."""

    def test_silence_keeps_asking_you_to_speak(self):
        page = self.make()
        self.mic.return_value.level = 0.0
        page.go(page.MIC)
        self.capture(page, "mic_listening")

        page._read_level()

        self.assertEqual("Say something", page.mic_status.text())
        self.assertFalse(page.retry_button.isVisible())
        self.assertTrue(page._poll.isActive())

    def test_hearing_you_turns_the_mic_into_a_check_and_offers_to_retry(self):
        page = self.make()
        page.go(page.MIC)

        page._read_level()
        self.capture(page, "mic_heard")

        self.assertEqual("Got you", page.mic_status.text())
        self.assertTrue(page.retry_button.isVisible())
        self.assertIsNotNone(page.pulse._heard_at)

    def test_leaving_the_step_stops_listening(self):
        page = self.make()
        page.go(page.MIC)

        page.go(page.KEYS)

        self.mic.return_value.stop.assert_called_once()
        self.assertFalse(page._poll.isActive())
        self.assertFalse(page.pulse.active)

    def test_unopenable_microphone_is_explained_and_can_be_retried(self):
        page = self.make()
        self.mic.side_effect = OSError("busy")
        page.go(page.MIC)
        self.capture(page, "mic_failed")
        self.assertIn("Couldn't open", page.mic_status.text())
        self.assertTrue(page.retry_button.isVisible())

        page._read_level()
        self.assertEqual(0.0, page._level)
        self.mic.side_effect = None
        self.mic.return_value.level = 0.0
        QTest.mouseClick(page.retry_button, Qt.LeftButton)

        self.assertEqual("Say something", page.mic_status.text())
        self.assertTrue(page._poll.isActive())

    def test_changing_the_device_saves_it_and_restarts_the_check_on_that_device(self):
        page = self.make()
        changes = []
        page.changed.connect(changes.append)
        page.go(page.MIC)
        page._read_level()
        self.mic.return_value.level = 0.0

        page.mic_combo.setCurrentIndex(page.mic_combo.findData("Headset"))
        self.capture(page, "mic_other_device")

        self.assertEqual([{"mic_device": "Headset"}], changes)
        self.assertEqual("Headset", self.mic.call_args.args[1])
        self.assertEqual("Say something", page.mic_status.text())
        self.assertFalse(page._heard)

    def test_changing_the_device_on_another_screen_only_saves_it(self):
        page = self.make()
        page.go(page.KEYS)
        self.mic.reset_mock()

        page.mic_combo.setCurrentIndex(page.mic_combo.findData("Desk mic"))

        self.mic.assert_not_called()


class KeysStepTest(OnboardingCase):
    """Shortcut capture, hold/tap/auto mode and the optional audio dimming are saved as they are chosen."""

    def test_recording_a_shortcut_saves_it_and_pauses_the_global_hotkey_meanwhile(self):
        page = self.make()
        changes, recording = [], []
        page.changed.connect(changes.append)
        page.shortcut_recording.connect(recording.append)
        page.go(page.KEYS)

        with patch("speak.ui.widgets.permissions.missing", return_value=[]), \
                patch("speak.ui.widgets.hotkey.unregister"), \
                patch("speak.ui.widgets.hotkey.capture", return_value="f9"):
            QTest.mouseClick(page.shortcut, Qt.LeftButton)
            self.assertEqual("Press keys…", page.shortcut.text())
            self.capture(page, "shortcut_recording")
            wait_for(lambda: bool(changes), 3000)

        self.assertEqual([{"hotkey": "f9"}], changes)
        self.assertEqual([True, False], recording)
        self.assertEqual(hotkey.display("f9"), page.shortcut.text())

    def test_escape_or_a_failed_capture_keeps_the_current_shortcut(self):
        page = self.make({"hotkey": "f8"})
        changes = []
        page.changed.connect(changes.append)
        page.go(page.KEYS)

        for captured in ("esc", OSError):
            changes.clear()
            kwargs = {"side_effect": captured} if captured is OSError else {"return_value": captured}
            with patch("speak.ui.widgets.permissions.missing", return_value=[]), \
                    patch("speak.ui.widgets.hotkey.unregister"), \
                    patch("speak.ui.widgets.hotkey.capture", **kwargs):
                QTest.mouseClick(page.shortcut, Qt.LeftButton)
                wait_for(lambda: bool(changes), 3000)
            self.assertEqual([{"hotkey": "f8"}], changes)

    def test_each_mode_is_saved_and_the_done_screen_describes_it(self):
        page = self.make()
        changes = []
        page.changed.connect(changes.append)
        page.go(page.KEYS)

        for mode in ("hold", "toggle", "auto"):
            page.mode_options.cards[mode].click()
            self.capture(page, f"mode_{mode}")
            page.set_shortcut("f9", mode)
            self.assertEqual(common.SHORTCUT_HINTS[mode], page.shortcut_hint.text())

        self.assertEqual([{"shortcut_mode": m} for m in ("hold", "toggle", "auto")], changes)
        page.set_shortcut("f9", "unknown")
        self.assertEqual("", page.shortcut_hint.text())

    def test_dimming_switch_enables_the_slider_and_the_slider_snaps_to_steps(self):
        page = self.make()
        changes = []
        page.changed.connect(changes.append)
        page.go(page.KEYS)
        self.assertFalse(page.dim_slider.isEnabled())
        self.capture(page, "dimming_off")

        page.dim_toggle.setChecked(True)
        page.dim_slider.setValue(63)
        self.capture(page, "dimming_on")

        self.assertTrue(page.dim_slider.isEnabled())
        self.assertEqual("65%", page.dim_value.text())
        self.assertEqual([{"audio_dim_enabled": True}, {"audio_dim_percent": 65}], changes)

    def test_dimming_card_is_hidden_where_the_system_cannot_dim(self):
        self.dim_supported = False
        page = self.make()
        page.go(page.KEYS)
        self.capture(page, "dimming_unsupported")

        self.assertFalse(page.dim_card.isVisible())


class TidyStepTest(OnboardingCase):
    """Tidy level cards, model size, device and corrections stay consistent with what this computer can run."""

    gpus = (GPU,)

    def test_each_level_card_is_selected_and_saved(self):
        page = self.make()
        changes = []
        page.changed.connect(changes.append)
        page.go(page.TIDY)

        for key in ("off", "fast", "ai"):
            page.tidy_options.cards[key].click()
            self.capture(page, f"level_{key}")
            self.assertEqual([k for k, c in page.level_cards.items() if c.isChecked()], [key])

        self.assertEqual([{"tidy": "off"}, {"tidy": "fast"}, {"tidy": "auto", "cleanup_model": "auto"}], changes)

    def test_model_hints_say_what_each_choice_means_on_this_computer(self):
        page = self.make()
        page.go(page.TIDY)
        self.assertEqual("Picks what suits this computer: Large model on your graphics card",
                         page.model_row.hint.text())

        page.model_options.chips["small"].click()
        self.assertEqual("Quick on any computer. Punctuation and capitals only", page.model_row.hint.text())

        page.model_options.chips["large"].click()
        self.capture(page, "model_large")
        self.assertEqual("Best results. About half a second here", page.model_row.hint.text())
        self.assertEqual("“Tuesday, no wait, Wednesday” becomes “Wednesday”", page.corrections_row.hint.text())

    def test_large_without_enough_memory_says_small_is_used_instead(self):
        self.plan = low_memory_plan
        page = self.make()
        page.go(page.TIDY)

        page.model_options.chips["large"].click()
        self.capture(page, "model_large_unavailable")

        self.assertEqual("Not enough free memory for Large, so Small is used", page.model_row.hint.text())
        self.assertFalse(page.corrections_row.isEnabled())
        self.assertEqual("Needs the Large model", page.corrections_row.hint.text())
        self.assertIn("Small model · processor", page.level_cards["ai"].subtitle_label.text())

    def test_large_on_the_processor_warns_it_takes_a_few_seconds(self):
        self.plan = cpu_plan
        page = self.make()
        page.go(page.TIDY)

        page.model_options.chips["large"].click()
        self.capture(page, "model_large_processor")

        self.assertEqual("Best results. A few seconds here", page.model_row.hint.text())
        self.assertIn("processor", page.level_cards["ai"].subtitle_label.text())

    def test_options_are_greyed_out_for_off_and_quick(self):
        page = self.make()
        page.go(page.TIDY)

        for level in ("off", "fast"):
            page.tidy_options.cards[level].click()
            self.capture(page, f"options_na_{level}")
            for row in (page.model_row, page.device_row, page.corrections_row):
                self.assertFalse(row.isEnabled())
            self.assertFalse(page.corrections.isChecked())
            self.assertTrue(all(not c.isChecked() for c in page.model_options.chips.values()))

    def test_device_choice_lists_detected_graphics_cards_and_is_saved(self):
        page = self.make()
        changes = []
        page.changed.connect(changes.append)
        page.go(page.TIDY)

        page.device.setCurrentIndex(page.device.findData("Vulkan0"))
        page.device.setCurrentIndex(page.device.findData("cpu"))
        self.capture(page, "device_processor")

        self.assertEqual([{"cleanup_device": "Vulkan0"}, {"cleanup_device": "cpu"}], changes)

    def test_fix_changes_of_mind_switch_is_saved_and_shows_in_the_example(self):
        page = self.make()
        changes = []
        page.changed.connect(changes.append)
        page.go(page.TIDY)

        page.corrections.setChecked(False)

        self.assertEqual([{"corrections": False}], changes)
        self.assertIn(common.EXAMPLE_LITERAL, page.level_cards["ai"].example_label.text())


class SpeedTestTest(OnboardingCase):
    """The speed strip walks through the test phases, rates the wait, explains the details, and recovers from
    failures or cancellation."""

    def start(self):
        page = self.make()
        page.go(page.TIDY)
        self.requests, self.cancels = [], []
        page.test_requested.connect(lambda pcm, rate: self.requests.append((pcm, rate)))
        page.test_cancelled.connect(lambda: self.cancels.append(1))
        QTest.mouseClick(button(page, "Test speed"), Qt.LeftButton)
        return page

    def test_starting_asks_the_app_for_the_sample_and_locks_the_button(self):
        page = self.start()

        self.assertEqual([(None, 0)], self.requests)
        self.assertFalse(page.sample_button.isEnabled())
        self.assertEqual(("preparing", "Getting ready"), page.test_stage._phase)

    def test_progress_messages_map_to_indicator_phases(self):
        page = self.start()

        page.set_progress("Loading the speech model")
        self.assertEqual(("preparing", "Loading the speech model"), page.test_stage._phase)
        page.set_progress("Downloading", 40.7)
        self.assertEqual(("preparing", "Downloading 40%"), page.test_stage._phase)
        page.set_progress("Listening to the sample")
        self.assertEqual("listening", page.test_stage._phase[0])
        page.set_progress("Tidying up")
        self.assertEqual("processing", page.test_stage._phase[0])

    def test_progress_and_failure_from_a_test_that_is_not_running_are_ignored(self):
        page = self.make()
        page.go(page.TIDY)

        page.set_progress("Listening to the sample")
        page.set_failure("Late failure")
        page.set_result(result())

        self.assertEqual(("idle", ""), page.test_stage._phase)
        self.assertEqual("", page.latency_label.text())

    def test_each_rating_colours_and_words_the_wait(self):
        page = self.start()
        outcomes = []
        for latency in (0.05, 0.5, 1.5, 3.0):
            page._testing = True
            page.set_result(result(latency))
            self.capture(page, f"rating_{latency}")
            outcomes.append((page.latency_label.text(), page.verdict_label.text()))

        self.assertEqual([("under 0.1 s", "Fast"), ("0.5 s", "Fast"), ("1.5 s", "Good"), ("3.0 s", "Slow")],
                         outcomes)
        self.assertIn(page.palette_.danger, page.latency_label.styleSheet())

    def test_result_text_and_details_describe_what_was_heard_and_tidied(self):
        page = self.start()
        plan = tidy.Plan("auto", config.LARGE_MODEL, "smart", "Vulkan0", "")

        page.set_result(result(raw="um hello  there", text="Hello there.", plan=plan))
        QTest.mouseClick(button(page, "Details"), Qt.LeftButton)
        self.capture(page, "details_open")

        self.assertEqual("“Hello there.”", page.text_label.text())
        self.assertIn("Smart · Large model on your graphics card", page.details_label.text())
        self.assertIn("Before tidy-up: “um hello there”", page.details_label.text())
        self.assertTrue(page.details_box.isVisible())
        QTest.mouseClick(button(page, "Details"), Qt.LeftButton)
        self.assertFalse(page.details_box.isVisible())

    def test_details_name_the_small_model_on_the_processor_and_the_non_ai_levels(self):
        page = self.start()
        cases = [(tidy.Plan("auto", config.SMALL_MODEL, "literal", None, ""), "Smart · Small model on your processor"),
                 (tidy.Plan("fast", None, "literal", None, ""), "Tidy-up: Quick"),
                 (tidy.Plan("off", None, "literal", None, ""), "Tidy-up: Off")]
        for plan, expected in cases:
            page._testing = True
            page.set_result(result(plan=plan, raw="same", text="same"))
            self.assertIn(expected, page.details_label.text())
            self.assertNotIn("Before tidy-up", page.details_label.text())

    def test_no_recognised_words_is_reported_plainly(self):
        page = self.start()

        page.set_result(result(raw="", text=" "))

        self.assertEqual("No words recognised.", page.text_label.text())

    def test_failure_shows_the_message_and_frees_the_buttons(self):
        page = self.start()

        page.set_failure("Download failed.")
        self.capture(page, "failed")

        self.assertEqual(("idle", "Download failed."), page.test_stage._phase)
        self.assertTrue(page.sample_button.isEnabled())
        self.assertGreater(distinct_colours(page.test_stage), 1)

    def test_leaving_resetting_or_hiding_cancels_and_clears_the_result(self):
        page = self.start()
        page.set_result(result())

        page.go(page.LOOK)

        self.assertEqual([], self.cancels)    # finished tests have nothing to cancel
        self.assertEqual("", page.latency_label.text())
        self.assertFalse(page.details_button.isVisible())
        self.assertEqual("idle", page.test_stage._phase[0])

    def test_changing_a_choice_after_a_result_shows_updating_then_retests(self):
        page = self.start()
        page.set_result(result())

        page.tidy_options.cards["off"].click()
        self.capture(page, "updating")
        self.assertEqual(("preparing", "Updating"), page.test_stage._phase)
        self.assertEqual("", page.latency_label.text())
        page._retest_now()

        self.assertEqual(2, len(self.requests))
        self.assertEqual(("preparing", "Getting ready"), page.test_stage._phase)


class LookAndUpdatesTest(OnboardingCase):
    """The indicator preview follows the live-text and position choices; update choices are saved."""

    def test_every_live_text_and_position_combination_is_saved_and_previewed(self):
        page = self.make()
        changes = []
        page.changed.connect(changes.append)
        page.go(page.LOOK)

        for live in config.LIVE_PREVIEWS:
            for position in config.OVERLAY_POSITIONS:
                page.live_options.chips[live].click()
                page.position_options.chips[position].click()
                self.capture(page, f"look_{live}_{position}")
                self.assertEqual((live, position), (page.stage.live, page.stage.position))
                self.assertGreater(distinct_colours(page.stage), 3)

        self.assertEqual(18, len(changes))

    def test_each_update_mode_and_prereleases_are_saved(self):
        page = self.make()
        changes = []
        page.changed.connect(changes.append)
        page.go(page.APP)

        for mode in config.UPDATE_MODES:
            page.updates_options.cards[mode].click()
            self.capture(page, f"updates_{mode}")
        page.prereleases.setChecked(True)
        self.capture(page, "updates_prereleases")

        self.assertEqual([{"updates": m} for m in config.UPDATE_MODES] + [{"prereleases": True}], changes)


class DoneStepTest(OnboardingCase):
    """The last screen names the chosen shortcut; Finish and Skip setup both tell the app."""

    def test_done_names_the_shortcut_and_finish_is_emitted(self):
        page = self.make({"hotkey": "f9", "shortcut_mode": "toggle"})
        events = []
        page.finished.connect(lambda: events.append("finish"))
        page.go(page.DONE)
        self.capture(page, "done")

        QTest.mouseClick(button(page, "Finish"), Qt.LeftButton)

        self.assertEqual(hotkey.display("f9"), page.keycap.text())
        self.assertEqual(common.SHORTCUT_HINTS["toggle"], page.shortcut_hint.text())
        self.assertEqual(["finish"], events)

    def test_skip_setup_is_emitted_from_any_step(self):
        page = self.make()
        events = []
        page.skipped.connect(lambda: events.append("skip"))

        for index in (page.WELCOME, page.TIDY):
            page.go(index)
            QTest.mouseClick(page.skip_button, Qt.LeftButton)

        self.assertEqual(["skip", "skip"], events)


class _Dark:
    theme = "Dark"


def _dark(cls):
    return type(f"{cls.__name__}Dark", (_Dark, cls), {"__doc__": f"{cls.__doc__} (dark theme)"})


NavigationDarkTest = _dark(NavigationTest)
SyncDarkTest = _dark(SyncTest)
WelcomeAndThemeDarkTest = _dark(WelcomeAndThemeTest)
MicStepDarkTest = _dark(MicStepTest)
KeysStepDarkTest = _dark(KeysStepTest)
TidyStepDarkTest = _dark(TidyStepTest)
SpeedTestDarkTest = _dark(SpeedTestTest)
LookAndUpdatesDarkTest = _dark(LookAndUpdatesTest)
DoneStepDarkTest = _dark(DoneStepTest)
