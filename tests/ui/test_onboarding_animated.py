"""The onboarding page with animation switched ON: real timers and animation groups run, and every screen must end
fully revealed, in place, with the progress dots on the right step."""
from unittest.mock import patch

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from speak import config
from speak.ui.onboarding.common import Revealer
from tests.ui import QtTestCase
from tests.ui.onboarding_support import (STEP_NAMES, OnboardingCase, button, distinct_colours, jump_to, result,
                                         wait_for)


def positions(page, index):
    return [w.mapTo(page, QPoint(0, 0)) for w in page._reveals[index]]


class AnimatedFlowTest(OnboardingCase):
    """Screens fade and rise in one after another, navigation fades the old screen out first and ignores clicks
    meanwhile, and the animations leave no effects or offsets behind."""

    animate = True

    def test_welcome_fades_in_and_lands_exactly_where_a_static_layout_puts_it(self):
        self.animate = False
        static = positions(self.make(), 0)
        self.animate = True

        page = self.make()
        self.assertTrue(all(w.graphicsEffect() is not None for w in page._reveals[0]))
        QTest.qWait(250)
        self.capture(page, "welcome_revealing")
        self.assertTrue(wait_for(lambda: self.revealed(page, 0), 5000))

        self.assertEqual(static, positions(page, 0))
        self.assertEqual({}, page._revealer._ends)
        self.capture(page, "welcome_revealed")

    def test_navigating_fades_out_then_reveals_and_ignores_clicks_in_between(self):
        page = self.make()
        wait_for(lambda: self.revealed(page, 0), 5000)

        QTest.mouseClick(button(page, "Get started"), Qt.LeftButton)
        page.go(page.KEYS)    # arrives mid-fade: ignored
        self.assertEqual(page.WELCOME, page.steps.currentIndex())
        self.assertTrue(wait_for(lambda: page.steps.currentIndex() == page.THEME, 3000))

        self.assertTrue(wait_for(lambda: self.revealed(page, page.THEME), 5000))
        self.assertEqual(page.THEME, page.steps.currentIndex())

    def test_every_step_ends_fully_revealed_with_the_dots_on_that_step(self):
        page = self.make()
        for index, name in enumerate(STEP_NAMES):
            with self.subTest(step=name):
                self.tour(page, index)
                if page.THEME <= index <= page.APP:
                    self.assertTrue(wait_for(lambda: abs(page.dots._value - (index - page.THEME)) < 1e-6, 3000))
                self.capture(page, f"animated_step{index}_{name}")
                self.assertEqual(index, page.steps.currentIndex())
                self.assertTrue(self.revealed(page, index))
                self.assertGreater(distinct_colours(page), 8)
        self.assertTrue(wait_for(lambda: page.burst._started is not None, 2000))
        self.assertTrue(wait_for(lambda: not page.burst._timer.isActive(), 4000))
        self.capture(page, "animated_done_after_burst")

    def test_leaving_mid_reveal_leaves_no_leftover_effects_or_offsets(self):
        page = self.make()
        wait_for(lambda: self.revealed(page, 0), 5000)
        self.tour(page, page.THEME)
        QTest.qWait(120)

        page.hide()

        self.assertTrue(self.revealed(page, page.THEME))
        self.assertEqual({}, page._revealer._ends)

    def test_back_goes_through_the_same_fade(self):
        page = self.make()
        self.tour(page, page.KEYS)

        QTest.mouseClick(page.back_button, Qt.LeftButton)

        self.assertTrue(wait_for(lambda: page.steps.currentIndex() == page.MIC, 3000))
        self.assertTrue(wait_for(lambda: self.revealed(page, page.MIC), 5000))

    def test_dots_slide_between_steps(self):
        page = self.make()
        self.tour(page, page.THEME)
        wait_for(lambda: page.dots._value == 0.0, 3000)

        page.go(page.KEYS)
        self.assertTrue(wait_for(lambda: page.dots._anim.state() == page.dots._anim.State.Running, 3000))
        self.assertTrue(wait_for(lambda: page.dots._value == 2.0, 3000))


class AnimatedMicAndTestTest(OnboardingCase):
    """Mic ripples, the heard check and the speed strip animate while their step is open, and stop when it isn't."""

    animate = True

    def test_mic_pulse_ripples_then_draws_the_check_once_it_hears_you(self):
        page = self.make()
        self.mic.return_value.level = 0.0
        self.tour(page, page.MIC)
        self.assertTrue(page.pulse._timer.isActive())
        QTest.qWait(150)
        listening = page.pulse.grab().toImage()
        self.capture(page, "animated_mic_listening")

        self.mic.return_value.level = 0.5
        self.assertTrue(wait_for(lambda: page._heard, 2000))
        QTest.qWait(500)
        self.capture(page, "animated_mic_heard")

        self.assertNotEqual(listening, page.pulse.grab().toImage())
        self.assertEqual("Got you", page.mic_status.text())
        page.go(page.KEYS)
        self.assertTrue(wait_for(lambda: page.steps.currentIndex() == page.KEYS, 3000))
        self.assertFalse(page.pulse._timer.isActive())

    def test_trying_again_clears_the_check_and_listens_afresh(self):
        page = self.make()
        self.tour(page, page.MIC)
        wait_for(lambda: page._heard, 2000)
        self.mic.return_value.level = 0.0

        QTest.mouseClick(page.retry_button, Qt.LeftButton)

        self.assertFalse(page._heard)
        self.assertIsNone(page.pulse._heard_at)
        self.assertTrue(page.pulse._timer.isActive())

    def test_speed_strip_animates_through_a_test_and_rests_when_finished(self):
        page = self.make()
        self.tour(page, page.TIDY)
        self.assertFalse(page.test_stage._timer.isActive())
        QTest.mouseClick(button(page, "Test speed"), Qt.LeftButton)

        states = []
        for message, percent in (("Downloading", 30), ("Listening to the sample", None), ("Tidying up", None)):
            page.set_progress(message, percent)
            QTest.qWait(60)
            states.append(page.test_stage._timer.isActive())
            self.capture(page, f"animated_speed_{page.test_stage._phase[0]}")
        page.set_result(result())
        states.append(page.test_stage._timer.isActive())
        self.capture(page, "animated_speed_done")

        self.assertEqual([True, True, True, False], states)
        self.assertEqual("Fast", page.verdict_label.text())

    def test_speed_strip_stops_animating_after_a_failure(self):
        page = self.make()
        self.tour(page, page.TIDY)
        QTest.mouseClick(button(page, "Test speed"), Qt.LeftButton)
        QTest.qWait(60)

        page.set_failure("Download failed.")

        self.assertFalse(page.test_stage._timer.isActive())

    def test_look_step_plays_its_loop_and_stops_when_hidden(self):
        page = self.make()
        self.tour(page, page.LOOK)
        self.assertTrue(page.stage._timer.isActive())
        images = []
        for label, seconds in (("listening", 1.0), ("processing", 5.5), ("done", 6.5), ("landed", 7.5)):
            jump_to(page.stage, seconds)
            QTest.qWait(40)
            self.capture(page, f"animated_look_{label}")
            images.append(page.stage.grab().toImage())

        self.assertNotEqual(images[0], images[3])
        page.hide()
        self.assertFalse(page.stage._timer.isActive())

    def test_change_during_animation_keeps_the_screen_consistent(self):
        page = self.make()
        self.tour(page, page.LOOK)

        page.live_options.chips["full"].click()
        page.position_options.chips["bottom"].click()

        self.assertEqual(("full", "bottom"), (page.stage.live, page.stage.position))
        self.assertEqual(config.LIVE_PREVIEWS["full"], page.live_options.chips["full"].text())


class RevealerTest(QtTestCase):
    """Stopping a reveal restores every widget still alive and tolerates ones deleted mid-animation."""

    def test_stopping_after_a_widget_was_deleted_still_restores_the_others(self):
        root = QWidget()
        self.addCleanup(root.close)
        first, second = QWidget(root), QWidget(root)
        root.show()
        revealer = Revealer()
        with patch("speak.ui.onboarding.common.ANIMATE", True):
            revealer.play([first, second], root)
        first.deleteLater()
        QTest.qWait(50)
        second.setGraphicsEffect(second.graphicsEffect())

        revealer.stop()

        self.assertIsNone(second.graphicsEffect())
        self.assertEqual({}, revealer._ends)


class DarkAnimatedFlowTest(AnimatedFlowTest):
    """Same animated flow in the dark theme."""

    theme = "Dark"


class DarkAnimatedMicAndTestTest(AnimatedMicAndTestTest):
    """Same animated mic/test/look behaviour in the dark theme."""

    theme = "Dark"

