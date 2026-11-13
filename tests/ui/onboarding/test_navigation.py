"""Onboarding flow: navigation, settings sync, welcome/theme, look/updates and the last screen.

Animation is off, so every screen is complete the moment it appears.
"""
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from speak import config, hotkey
from speak.ui import theme as ui_theme
from speak.ui.onboarding import common
from tests.ui.onboarding.support import GPU, STEP_NAMES, OnboardingCase, button, dark_variant, distinct_colours


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


NavigationDarkTest = dark_variant(NavigationTest)
SyncDarkTest = dark_variant(SyncTest)
WelcomeAndThemeDarkTest = dark_variant(WelcomeAndThemeTest)
LookAndUpdatesDarkTest = dark_variant(LookAndUpdatesTest)
DoneStepDarkTest = dark_variant(DoneStepTest)
