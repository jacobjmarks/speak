"""Onboarding microphone and shortcut steps: the mic check listens as soon as it appears, shortcut capture and
dimming are saved as they are chosen (animation off)."""
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from speak import hotkey
from speak.ui.onboarding import common
from tests.ui.onboarding.support import OnboardingCase, dark_variant, wait_for


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

        with patch("speak.permissions.missing", return_value=[]), \
                patch("speak.hotkey.unregister"), \
                patch("speak.hotkey.capture", return_value="f9"):
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
            with patch("speak.permissions.missing", return_value=[]), \
                    patch("speak.hotkey.unregister"), \
                    patch("speak.hotkey.capture", **kwargs):
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


MicStepDarkTest = dark_variant(MicStepTest)
KeysStepDarkTest = dark_variant(KeysStepTest)
