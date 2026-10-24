import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from speak import tidy
from speak.ui.app import SpeakApp


class DevicePreferenceTest(unittest.TestCase):
    """A saved GPU that disappears is reset and communicated to the user."""

    def test_missing_saved_gpu_resets_and_notifies(self):
        settings = {"cleanup_device": "Vulkan9"}
        detected = [tidy.Gpu("Vulkan0", "RTX", 9000)]
        page = SimpleNamespace(set_gpus=Mock())
        window = SimpleNamespace(settings=page, notify=Mock(), isVisible=lambda: True)
        app = SimpleNamespace(settings=settings, window=window, tray=None, _refresh_tidy=Mock())
        app._update = lambda changes: settings.update(changes)

        with patch.object(tidy, "gpus", return_value=detected):
            SpeakApp._on_probed(app)

        self.assertEqual("auto", settings["cleanup_device"])
        window.notify.assert_called_once()
        self.assertIn("reset to Automatic", window.notify.call_args.args[1])
        page.set_gpus.assert_called_once_with(detected, "auto")
        app._refresh_tidy.assert_called_once()


if __name__ == "__main__":
    unittest.main()
