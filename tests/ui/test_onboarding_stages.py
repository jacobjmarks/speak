"""The two indicator mock-ups: the speed-test strip and the look step's screen. Both play the app's real overlay."""
from unittest.mock import patch

from PySide6.QtTest import QTest

from speak import config
from speak.ui.onboarding import common
from speak.ui.onboarding.common import STAGE_FROZEN_WORDS, STAGE_TEXT
from speak.ui.onboarding.stages import OverlayStage, SpeedStage
from speak.ui import theme as ui_theme
from tests.ui import QtTestCase
from tests.ui.onboarding_support import distinct_colours, jump_to

PALETTES = {"light": ui_theme.LIGHT, "dark": ui_theme.DARK}
PHASES = (("idle", ""), ("idle", "Download failed."), ("preparing", "Getting ready"), ("listening", ""),
          ("processing", "Finishing up"), ("done", ""))


class StageCase(QtTestCase):
    animate = False

    def setUp(self):
        patcher = patch.object(common, "ANIMATE", self.animate)
        patcher.start()
        self.addCleanup(patcher.stop)

    def shown(self, stage, palette):
        stage.palette_ = palette
        stage.resize(max(stage.width(), 640), stage.height())
        stage.show()
        self.addCleanup(stage.close)
        return stage


class SpeedStageTest(StageCase):
    """The strip shows a hint while idle and the real indicator for each test phase, in both palettes."""

    def test_every_phase_draws_something_different(self):
        for name, palette in PALETTES.items():
            stage = self.shown(SpeedStage(), palette)
            images = []
            for mode, word in PHASES:
                stage.set_phase(mode, word)
                self.capture(stage, f"{name}_{mode}_{word.lower().replace(' ', '_').replace('.', '') or 'plain'}")
                self.assertGreater(distinct_colours(stage, 2), 1, (name, mode))
                images.append(stage.grab().toImage())
            with self.subTest(palette=name):
                for a in range(len(PHASES)):
                    for b in range(a + 1, len(PHASES)):
                        self.assertNotEqual(images[a], images[b], (PHASES[a], PHASES[b]))

    def test_palette_reaches_the_embedded_overlay(self):
        stage = SpeedStage()

        stage.palette_ = ui_theme.DARK

        self.assertIs(ui_theme.DARK, stage._overlay.palette_)
        self.assertIs(ui_theme.DARK, stage.palette_)

    def test_no_timer_runs_when_animation_is_off(self):
        stage = self.shown(SpeedStage(), ui_theme.LIGHT)

        stage.set_phase("listening")

        self.assertFalse(stage._timer.isActive())


class AnimatedSpeedStageTest(StageCase):
    """While a test is working the strip repaints on a timer; it rests when idle or done, and when hidden."""

    animate = True

    def test_timer_runs_only_for_the_working_phases_and_while_visible(self):
        stage = self.shown(SpeedStage(), ui_theme.LIGHT)
        running = {}
        for mode, word in PHASES:
            stage.set_phase(mode, word)
            running[mode] = stage._timer.isActive()
            QTest.qWait(40)
            self.capture(stage, f"animated_{mode}_{len(word)}")

        self.assertEqual({"idle": False, "preparing": True, "listening": True, "processing": True, "done": False},
                         running)
        stage.set_phase("listening")
        stage.hide()
        self.assertFalse(stage._timer.isActive())
        stage.show()
        self.assertTrue(stage._timer.isActive())    # resumes the phase it was in

    def test_listening_bars_move_over_time(self):
        stage = self.shown(SpeedStage(), ui_theme.LIGHT)
        stage.set_phase("listening")
        jump_to(stage, 0.1)
        first = stage.grab().toImage()
        jump_to(stage, 0.5)

        self.assertNotEqual(first, stage.grab().toImage())


class OverlayStageTest(StageCase):
    """The look step's mock screen: static and complete without animation; one frame per live-text/position."""

    def test_static_frame_shows_the_indicator_with_words_so_far(self):
        stage = self.shown(OverlayStage(), ui_theme.LIGHT)

        self.assertEqual(("listening", STAGE_FROZEN_WORDS, False), stage._moment())
        self.assertFalse(stage._timer.isActive())

    def test_every_live_text_and_position_draws_its_own_frame(self):
        for name, palette in PALETTES.items():
            stage = self.shown(OverlayStage(), palette)
            images = {}
            for live in config.LIVE_PREVIEWS:
                for position in config.OVERLAY_POSITIONS:
                    stage.set_options(live, position)
                    self.capture(stage, f"{name}_{live}_{position}")
                    self.assertGreater(distinct_colours(stage), 3)
                    images[live, position] = stage.grab().toImage()
            with self.subTest(palette=name):
                for position in config.OVERLAY_POSITIONS:
                    self.assertNotEqual(images["line", position], images["off", position])
                for live in config.LIVE_PREVIEWS:
                    self.assertNotEqual(images[live, "top"], images[live, "bottom"])

    def test_palette_reaches_the_embedded_overlay(self):
        stage = OverlayStage()

        stage.palette_ = ui_theme.DARK

        self.assertIs(ui_theme.DARK, stage._overlay.palette_)


class AnimatedOverlayStageTest(StageCase):
    """The mock plays a loop: words arrive, "Finishing up", the check, the text lands in the window, a rest."""

    animate = True

    def test_timeline_runs_listening_processing_done_landed_rest_and_loops(self):
        stage = self.shown(OverlayStage(), ui_theme.LIGHT)
        words = len(STAGE_TEXT.split())

        moments = []
        for seconds in (0.1, 1.0, 5.5, 6.5, 7.5, 8.8):
            jump_to(stage, seconds)
            moments.append(stage._moment())

        self.assertEqual([("listening", 0, False), ("listening", 3, False), ("processing", words, False),
                          ("done", words, True), (None, words, True), ("listening", 0, False)], moments)

    def test_each_moment_paints_and_differs_from_the_others(self):
        stage = self.shown(OverlayStage(), ui_theme.DARK)
        self.assertTrue(stage._timer.isActive())
        images = []
        for label, seconds in (("listening", 1.0), ("processing", 5.5), ("done", 6.5), ("landed", 7.5)):
            jump_to(stage, seconds)
            QTest.qWait(30)
            self.capture(stage, f"animated_{label}")
            self.assertGreater(distinct_colours(stage), 3)
            images.append(stage.grab().toImage())

        for a in range(len(images)):
            for b in range(a + 1, len(images)):
                self.assertNotEqual(images[a], images[b], (a, b))

    def test_every_position_and_live_mode_paints_while_animating(self):
        stage = self.shown(OverlayStage(), ui_theme.LIGHT)
        for live in config.LIVE_PREVIEWS:
            for position in config.OVERLAY_POSITIONS:
                stage.set_options(live, position)
                jump_to(stage, 2.0)
                self.assertGreater(distinct_colours(stage), 3, (live, position))

    def test_hiding_stops_the_loop_and_showing_restarts_it(self):
        stage = self.shown(OverlayStage(), ui_theme.LIGHT)

        stage.hide()
        self.assertFalse(stage._timer.isActive())
        stage.show()

        self.assertTrue(stage._timer.isActive())
