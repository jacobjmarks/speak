import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from speak import config, history


class ConfigTest(unittest.TestCase):
    """Settings retain defaults, migrate old keys, and round-trip through disk."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings_file = self.root / "settings.json"
        self.paths = patch.multiple(config, APP_DIR=self.root, SETTINGS_FILE=self.settings_file)
        self.paths.start()
        self.addCleanup(self.paths.stop)

    def test_loads_defaults_and_migrates_legacy_settings(self):
        self.settings_file.write_text(
            '{"cleanup_enabled": false, "hold_to_talk": false, "check_updates": true, '
            '"live_preview": false}',
            encoding="utf-8",
        )

        settings = config.load_settings()

        self.assertEqual("off", settings["tidy"])
        self.assertEqual("toggle", settings["shortcut_mode"])
        self.assertEqual("auto", settings["updates"])
        self.assertEqual("off", settings["live_preview"])
        self.assertNotIn("cleanup_enabled", settings)

        self.settings_file.write_text('{"tidy": "balanced"}', encoding="utf-8")
        self.assertEqual("auto", config.load_settings()["tidy"])

    def test_onboarding_done_flag_defaults_and_explicit_values(self):
        # Fresh install (no settings file) should have onboarding_done = False
        self.assertFalse(config.load_settings()["onboarding_done"])

        # Existing settings without onboarding_done should also have onboarding_done = False
        self.settings_file.write_text('{"tidy": "fast"}', encoding="utf-8")
        self.assertFalse(config.load_settings()["onboarding_done"])

        # Explicitly setting onboarding_done = false should still be respected
        self.settings_file.write_text('{"onboarding_done": false}', encoding="utf-8")
        self.assertFalse(config.load_settings()["onboarding_done"])

        # Explicitly setting onboarding_done = true should skip onboarding
        self.settings_file.write_text('{"onboarding_done": true}', encoding="utf-8")
        self.assertTrue(config.load_settings()["onboarding_done"])

    def test_invalid_json_falls_back_to_defaults_and_save_round_trips(self):
        self.settings_file.write_text("{", encoding="utf-8")
        self.assertEqual(config.DEFAULTS, config.load_settings())

        settings = {**config.DEFAULTS, "hotkey": "ctrl+space"}
        config.save_settings(settings)

        self.assertEqual(settings, config.load_settings())

    def test_unknown_language_selection_falls_back_to_automatic_detection(self):
        for value in ("xx", ["en"], None):
            with self.subTest(value=value):
                self.settings_file.write_text(
                    json.dumps({"language": value}),
                    encoding="utf-8",
                )
                self.assertEqual("auto", config.load_settings()["language"])



class HistoryTest(unittest.TestCase):
    """Transcript history is isolated, newest-first, limited, and clearable."""

    def test_opt_in_store_returns_newest_first_and_clears(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(history, "HISTORY_FILE", Path(directory) / "history.sqlite3"):
            self.assertEqual([], history.recent())
            history.add("first")
            history.add("second")

            self.assertEqual(["second", "first"], [text for _, text in history.recent()])
            self.assertEqual(["second"], [text for _, text in history.recent(1)])
            history.clear()
            self.assertEqual([], history.recent())


if __name__ == "__main__":
    unittest.main()
