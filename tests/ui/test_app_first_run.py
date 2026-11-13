"""The real `SpeakApp` wired to the real onboarding page: first-run flow, speed test plumbing, and finishing/skipping.
Only OS and hardware boundaries are mocked (settings files, permissions, hotkey hook, tray, microphone, model
servers, updater)."""
import json
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from speak import benchmark, config
from speak.runtimes import ModelDownloadError
from speak.ui import theme as ui_theme
from speak.ui.app import SpeakApp
from tests.ui import QtTestCase
from tests.ui.onboarding.support import GPU, button, fake_plan, result, wait_for


class FirstRunAppTest(QtTestCase):
    """On first run the app opens onboarding instead of the dictation page, keeps the global hotkey quiet while it
    shows, saves every choice, runs the speed test on a worker thread, and leaves setup on Finish or Skip."""

    def make_app(self, **settings):
        scratch = Path(tempfile.mkdtemp(prefix="speak-onboarding-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(scratch, ignore_errors=True))
        self.settings_file = scratch / "settings.json"
        if settings:
            self.settings_file.write_text(json.dumps(settings))
        patches = [patch.object(config, "SETTINGS_FILE", self.settings_file),
                   patch.object(config, "HISTORY_FILE", scratch / "history.sqlite3"),
                   patch("speak.ui.app.permissions.missing", return_value=[]),
                   patch("speak.ui.app.hotkey.register"), patch("speak.ui.app.hotkey.unregister"),
                   patch("speak.ui.app.updates.cleanup"), patch("speak.ui.app.updates.newer_release",
                                                                return_value=None),
                   patch("speak.ui.app.tidy.probed", return_value=True),
                   patch("speak.ui.app.tidy.gpus", return_value=[]),
                   patch("speak.ui.app.tidy.plan", side_effect=fake_plan),
                   patch("speak.ui.onboarding.steps.tidy.tidy.plan", side_effect=fake_plan),
                   patch("speak.ui.onboarding.page.tidy.gpus", return_value=[]),
                   patch("speak.ui.onboarding.steps.mic.audio.Microphone"),
                   patch("speak.audio.input_devices", return_value=["Desk mic"]),
                   patch("speak.platform_utils.launch_at_login_enabled", return_value=False),
                   patch("speak.ui.onboarding.common.ANIMATE", False),
                   patch("speak.ui.app.Dictation.cancel_benchmark"),
                   patch.object(SpeakApp, "_make_tray", return_value=None)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.app = SpeakApp(QApplication.instance(), background=True)
        self.addCleanup(self.shutdown, self.app)
        self.page = self.app.window.onboarding
        return self.app

    def shutdown(self, app):
        app._update_timer.stop()
        app.window.allow_close = True
        app.window.close()
        QApplication.instance().setStyleSheet("")

    def saved(self) -> dict:
        return json.loads(self.settings_file.read_text())

    def test_first_run_opens_onboarding_and_the_hotkey_stays_quiet(self):
        app = self.make_app()

        self.assertTrue(app.window.isVisible())
        self.assertIs(app.window.screens.currentWidget(), self.page)
        self.assertEqual(self.page.WELCOME, self.page.steps.currentIndex())
        self.capture(app.window, "first_run")
        app.dictation.start = MagicMock()
        app._on_hotkey_down()
        app.dictation.start.assert_not_called()

    def test_completed_setup_goes_straight_to_the_app(self):
        app = self.make_app(onboarding_done=True)

        self.assertIsNot(app.window.screens.currentWidget(), self.page)
        self.assertFalse(app._onboarding)

    def test_choices_are_saved_restyle_the_app_and_finish_returns_to_it(self):
        app = self.make_app()
        self.page.go(self.page.THEME)
        self.page.theme_options.cards["Dark"].click()
        self.capture(app.window, "dark_chosen")
        self.page.go(self.page.KEYS)
        self.page.mode_options.cards["toggle"].click()
        self.page.go(self.page.TIDY)
        self.page.tidy_options.cards["fast"].click()
        self.page.go(self.page.LOOK)
        self.page.live_options.chips["full"].click()
        self.page.go(self.page.APP)
        self.page.prereleases.setChecked(True)
        self.page.go(self.page.DONE)
        self.capture(app.window, "done")

        QTest.mouseClick(button(self.page, "Finish"), Qt.LeftButton)

        saved = self.saved()
        self.assertEqual(("Dark", "toggle", "fast", "full", True, True),
                         (saved["theme"], saved["shortcut_mode"], saved["tidy"], saved["live_preview"],
                          saved["prereleases"], saved["onboarding_done"]))
        self.assertIs(ui_theme.resolve("Dark"), app.palette)
        self.assertIs(ui_theme.resolve("Dark"), self.page.palette_)
        self.assertFalse(app._onboarding)
        self.assertIsNot(app.window.screens.currentWidget(), self.page)
        self.assertEqual("Tap to start. Tap again to stop", self.page.shortcut_hint.text())

    def test_prerelease_switched_off_during_setup_reads_off_on_the_settings_page(self):
        app = self.make_app(prereleases=True)
        self.page.go(self.page.APP)
        self.assertTrue(self.page.prereleases.isChecked())

        QTest.mouseClick(self.page.prereleases, Qt.LeftButton)
        self.page.go(self.page.DONE)
        QTest.mouseClick(button(self.page, "Finish"), Qt.LeftButton)

        self.assertFalse(self.saved()["prereleases"])
        self.assertFalse(app.window.settings.prereleases.isChecked())

    def test_prerelease_switched_off_in_rerun_setup_reads_off_on_the_settings_page(self):
        app = self.make_app(onboarding_done=True, prereleases=True)
        app._start_onboarding()
        self.page.go(self.page.APP)
        self.assertTrue(self.page.prereleases.isChecked())

        QTest.mouseClick(self.page.prereleases, Qt.LeftButton)
        self.page.go(self.page.DONE)
        QTest.mouseClick(button(self.page, "Finish"), Qt.LeftButton)

        self.assertFalse(self.saved()["prereleases"])
        self.assertFalse(app.window.settings.prereleases.isChecked())

    def test_appearance_and_shortcut_choices_reflect_on_the_settings_page(self):
        app = self.make_app()
        settings = app.window.settings

        self.page.theme_options.cards["Dark"].click()
        self.assertEqual("Dark", settings.theme.currentData())
        self.page.shortcut.captured.emit("f9")
        self.assertEqual("f9", settings.shortcut.combo)
        self.page.mode_options.cards["toggle"].click()
        self.assertEqual("toggle", settings.shortcut_mode.currentData())

    def test_audio_dimming_choices_reflect_on_the_settings_page(self):
        app = self.make_app()
        settings = app.window.settings

        self.page.dim_toggle.setChecked(False)
        self.assertFalse(settings.audio_dim.isChecked())
        self.assertFalse(settings.audio_dim_slider.isEnabled())
        self.page.dim_toggle.setChecked(True)
        self.page.dim_slider.setValue(40)
        self.assertEqual(config.snap_audio_dim_percent(40), settings.audio_dim_slider.value())

    def test_microphone_choice_reflects_on_the_settings_page(self):
        app = self.make_app()

        self.page.mic_combo.setCurrentIndex(self.page.mic_combo.findData("Desk mic"))
        self.assertEqual("Desk mic", app.window.settings.mic.currentData())

    def test_tidy_choices_reflect_on_the_settings_page(self):
        app = self.make_app()
        settings = app.window.settings

        self.page.tidy_options.cards["fast"].click()
        self.assertEqual("fast", settings.tidy.currentData())
        self.page.tidy_options.cards["ai"].click()

        def tidy_and_model():
            return settings.tidy.currentData(), settings.cleanup_model.currentData()

        self.page.model_options.chips["small"].click()
        self.assertEqual(("auto", config.SMALL_MODEL), tidy_and_model())
        self.page.model_options.chips["large"].click()
        self.assertEqual(("best", "auto"), tidy_and_model())
        self.page.model_options.chips["auto"].click()
        self.assertEqual(("auto", "auto"), tidy_and_model())
        self.page.device.setCurrentIndex(self.page.device.findData("cpu"))
        self.assertEqual("cpu", settings.cleanup_device.currentData())
        self.page.corrections.setChecked(False)
        self.assertFalse(settings.corrections.isChecked())

    def test_gpu_choice_reflects_on_the_settings_page(self):
        app = self.make_app()
        with patch("speak.ui.app.tidy.gpus", return_value=[GPU]), \
                patch("speak.ui.onboarding.page.tidy.gpus", return_value=[GPU]):
            app._on_probed()

        self.page.device.setCurrentIndex(self.page.device.findData(GPU.device))
        self.assertEqual(GPU.device, app.window.settings.cleanup_device.currentData())

    def test_look_and_update_choices_reflect_on_the_settings_page(self):
        app = self.make_app()
        settings = app.window.settings

        self.page.live_options.chips["full"].click()
        self.assertEqual("full", settings.live.currentData())
        self.page.position_options.chips["top"].click()
        self.assertEqual("top", settings.position.currentData())
        self.page.updates_options.cards["off"].click()
        self.assertEqual("off", settings.updates.currentData())
        self.page.prereleases.setChecked(True)
        self.assertTrue(settings.prereleases.isChecked())

    def test_skipping_setup_counts_as_done(self):
        app = self.make_app()

        QTest.mouseClick(self.page.skip_button, Qt.LeftButton)

        self.assertTrue(self.saved()["onboarding_done"])
        self.assertFalse(app._onboarding)

    def test_finishing_again_does_not_rewrite_a_completed_setup(self):
        app = self.make_app(onboarding_done=True)
        app._start_onboarding()

        with patch("speak.ui.app.config.save_settings") as save:
            app._finish_onboarding()

        save.assert_not_called()
        self.assertFalse(app._onboarding)

    def test_rerunning_setup_from_settings_starts_again_at_welcome(self):
        app = self.make_app(onboarding_done=True)
        self.page.go(self.page.DONE)

        app.window.settings.rerun_setup.emit()

        self.assertTrue(app._onboarding)
        self.assertIs(app.window.screens.currentWidget(), self.page)
        self.assertEqual(self.page.WELCOME, self.page.steps.currentIndex())

    def test_setup_waits_for_permissions_then_starts_onboarding(self):
        with patch("speak.ui.app.permissions.REQUIRED", []):
            app = self.make_app()
        app._onboarding = False
        app.window.show_onboarding(False)
        with patch("speak.ui.app.permissions.granted", return_value=True), \
                patch("speak.ui.app.permissions.REQUIRED", [MagicMock(id="mic")]):
            app._setup_timer = MagicMock()
            app._check_setup()

        self.assertTrue(app._onboarding)
        self.assertIs(app.window.screens.currentWidget(), self.page)

    # ----- speed test -----

    def run_test(self, run_benchmark):
        app = self.make_app()
        app.dictation.run_benchmark = run_benchmark
        self.page.go(self.page.TIDY)
        QTest.mouseClick(button(self.page, "Test speed"), Qt.LeftButton)
        return app

    def test_speed_test_runs_the_bundled_sample_and_shows_the_result_and_progress(self):
        seen = []

        def run_benchmark(pcm, rate, progress):
            seen.append((pcm, rate, threading.current_thread() is not threading.main_thread()))
            progress("Listening to the sample", None)
            return result(0.4)

        with patch("speak.ui.app.benchmark.read_wav", return_value=(b"pcm", 16000)) as read, \
                patch("speak.ui.app.platform_utils.sample_audio_file", return_value="sample.wav"):
            self.run_test(run_benchmark)
            self.assertTrue(wait_for(lambda: self.page.verdict_label.text() == "Fast", 3000))

        read.assert_called_once_with("sample.wav")
        self.assertEqual([(b"pcm", 16000, True)], seen)
        self.assertEqual("0.4 s", self.page.latency_label.text())
        self.capture(self.app.window, "speed_result")

    def test_speed_test_failures_are_explained_in_plain_language(self):
        cases = [(ModelDownloadError("Download failed."), "Download failed."),
                 (RuntimeError("Speech server didn't start."), "Speech server didn't start."),
                 (ValueError("boom"), "The test didn't work. Please try again.")]
        for error, message in cases:
            with self.subTest(error=type(error).__name__):
                def fail(pcm, rate, progress, error=error):
                    raise error
                with patch("speak.ui.app.benchmark.read_wav", return_value=(b"", 16000)), \
                        patch("speak.ui.app.platform_utils.sample_audio_file", return_value="sample.wav"):
                    self.run_test(fail)
                    self.assertTrue(wait_for(lambda: self.page.test_stage._phase == ("idle", message), 3000))
                self.assertTrue(self.page.sample_button.isEnabled())

    def test_a_cancelled_run_reports_nothing(self):
        def cancelled(pcm, rate, progress):
            raise benchmark.Cancelled()

        with patch("speak.ui.app.benchmark.read_wav", return_value=(b"", 16000)), \
                patch("speak.ui.app.platform_utils.sample_audio_file", return_value="sample.wav"):
            self.run_test(cancelled)
            QTest.qWait(200)

        self.assertEqual(("preparing", "Getting ready"), self.page.test_stage._phase)

    def test_recorded_audio_is_used_when_the_page_supplies_it(self):
        app = self.make_app()
        app.dictation.run_benchmark = MagicMock(return_value=result())

        app._run_test(b"recorded", 8000)
        self.page._testing = True
        self.assertTrue(wait_for(lambda: app.dictation.run_benchmark.called, 3000))

        self.assertEqual((b"recorded", 8000), app.dictation.run_benchmark.call_args.args[:2])

    def test_changing_a_choice_during_a_test_cancels_the_running_benchmark(self):
        with patch("speak.ui.app.benchmark.read_wav", return_value=(b"", 16000)), \
                patch("speak.ui.app.platform_utils.sample_audio_file", return_value="sample.wav"):
            release = threading.Event()
            app = self.run_test(lambda pcm, rate, progress: release.wait(2) and result())
            self.page.tidy_options.cards["off"].click()
            release.set()

        app.dictation.cancel_benchmark.assert_called()
        self.assertEqual("off", self.saved()["tidy"])

    def test_leaving_the_app_stops_a_running_benchmark(self):
        app = self.make_app()
        app.dictation.cancel_benchmark = MagicMock()
        app.dictation.shutdown = MagicMock()

        with patch("speak.ui.app.hotkey.unregister"), patch.object(app.app, "quit"):
            app.quit()

        app.dictation.cancel_benchmark.assert_called_once()
