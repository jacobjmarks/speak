import threading
import unittest
from unittest.mock import Mock, patch

from speak import config, system_audio
from speak.controller import Dictation, State


class SystemAudioTest(unittest.TestCase):
    """Audio dimming changes volume predictably and restores only Speak's own adjustment."""

    def test_audio_dim_percentage_snaps_to_five_point_steps(self):
        values = [config.snap_audio_dim_percent(value) for value in range(10, 91)]
        self.assertTrue(all(value % 5 == 0 and 10 <= value <= 90 for value in values))

    def test_dim_reduces_the_current_volume_by_the_requested_percentage(self):
        with patch.object(system_audio, "get_volume", return_value=0.8), \
                patch.object(system_audio, "set_volume") as set_volume:
            self.assertEqual(system_audio.dim(50), (0.8, 0.4))
        set_volume.assert_called_once_with(0.4)

    def test_restore_returns_to_original_volume_if_still_dimmed(self):
        with patch.object(system_audio, "get_volume", return_value=0.4), \
                patch.object(system_audio, "set_volume") as set_volume:
            self.assertTrue(system_audio.restore(0.8, 0.4))
        set_volume.assert_called_once_with(0.8)

    def test_restore_preserves_a_volume_change_made_while_dictating(self):
        with patch.object(system_audio, "get_volume", return_value=0.6), \
                patch.object(system_audio, "set_volume") as set_volume:
            self.assertFalse(system_audio.restore(0.8, 0.4))
        set_volume.assert_not_called()

    def test_restore_preserves_small_user_changes_at_low_volume(self):
        with patch.object(system_audio, "get_volume", return_value=0.01), \
                patch.object(system_audio, "set_volume") as set_volume:
            self.assertFalse(system_audio.restore(0.02, 0.0))
        set_volume.assert_not_called()


class DictationAudioDimmingTest(unittest.TestCase):
    """Dictation dims output while listening and restores it when processing begins."""

    def test_listening_dims_and_processing_restores_output(self):
        dictation = Dictation.__new__(Dictation)
        dictation._lock = threading.RLock()
        dictation.state = State.PREPARING
        dictation.settings = {"audio_dim_enabled": True, "audio_dim_percent": 50}
        dictation.listener = Mock()
        dictation._audio_volume = None
        with patch("speak.controller.system_audio.SUPPORTED", True), \
                patch("speak.controller.system_audio.dim", return_value=(0.8, 0.4)) as dim, \
                patch("speak.controller.system_audio.restore") as restore:
            dictation._set_state(State.LISTENING)
            dim.assert_called_once_with(50)
            self.assertEqual(dictation._audio_volume, (0.8, 0.4))
            dictation._set_state(State.PROCESSING)
        restore.assert_called_once_with(0.8, 0.4)
        self.assertIsNone(dictation._audio_volume)


if __name__ == "__main__":
    unittest.main()
