"""Onboarding tidy step: level cards, model size, device and corrections; plus the timed speed test (animation off)."""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from speak import config, tidy
from speak.ui.onboarding import common
from tests.ui.onboarding.support import (GPU, OnboardingCase, button, cpu_plan, dark_variant, distinct_colours,
                                         low_memory_plan, result)


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


TidyStepDarkTest = dark_variant(TidyStepTest)
SpeedTestDarkTest = dark_variant(SpeedTestTest)
