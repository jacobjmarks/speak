import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from speak import platform_utils


class PlatformUtilsTest(unittest.TestCase):
    """Platform helpers select native paths, commands, startup registration, and shortcuts."""

    def test_data_directories_follow_each_platform(self):
        home = Path("C:/Users/test")
        with patch.object(platform_utils.Path, "home", return_value=home), \
                patch.dict(platform_utils.os.environ, {"LOCALAPPDATA": "C:/Users/test/Local"}, clear=True), \
                patch.multiple(platform_utils, IS_WINDOWS=True, IS_MAC=False):
            self.assertEqual(Path("C:/Users/test/Local/Speak"), platform_utils.app_data_dir())

        with patch.object(platform_utils.Path, "home", return_value=home), \
                patch.multiple(platform_utils, IS_WINDOWS=False, IS_MAC=True):
            self.assertEqual(home / "Library/Application Support/Speak", platform_utils.app_data_dir())

        with patch.object(platform_utils.Path, "home", return_value=home), \
                patch.dict(platform_utils.os.environ, {"XDG_DATA_HOME": "/tmp/data"}, clear=True), \
                patch.multiple(platform_utils, IS_WINDOWS=False, IS_MAC=False):
            self.assertEqual(Path("/tmp/data/speak"), platform_utils.app_data_dir())

    def test_paste_shortcut_and_hidden_process_flags_are_platform_specific(self):
        with patch.multiple(platform_utils, IS_WINDOWS=True, IS_MAC=False), \
                patch.object(platform_utils.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
            self.assertEqual("ctrl+v", platform_utils.paste_shortcut())
            self.assertIn("creationflags", platform_utils.hidden_process_kwargs())
        with patch.multiple(platform_utils, IS_WINDOWS=False, IS_MAC=True):
            self.assertEqual("cmd+v", platform_utils.paste_shortcut())
            self.assertEqual({"start_new_session": True}, platform_utils.hidden_process_kwargs())

    def test_login_startup_files_use_native_format_and_can_be_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "speak-startup"
            command = ["python", "main.py"]
            with patch.object(platform_utils, "_autostart_file", return_value=path), \
                    patch.object(platform_utils, "_launch_command", return_value=command), \
                    patch.multiple(platform_utils, IS_WINDOWS=False, IS_MAC=True):
                platform_utils.set_launch_at_login(True)
                self.assertIn("<key>ProgramArguments</key>", path.read_text(encoding="utf-8"))
                self.assertIn("<string>--background</string>", path.read_text(encoding="utf-8"))
                platform_utils.set_launch_at_login(False)
                self.assertFalse(path.exists())

            with patch.object(platform_utils, "_autostart_file", return_value=path), \
                    patch.object(platform_utils, "_launch_command", return_value=command), \
                    patch.multiple(platform_utils, IS_WINDOWS=False, IS_MAC=False):
                platform_utils.set_launch_at_login(True)
                self.assertIn("[Desktop Entry]", path.read_text(encoding="utf-8"))
                self.assertTrue(platform_utils.launch_at_login_enabled())
                platform_utils.set_launch_at_login(False)
                self.assertFalse(platform_utils.launch_at_login_enabled())

    def test_windows_login_startup_uses_run_registry_key(self):
        key = MagicMock()
        winreg = SimpleNamespace(
            HKEY_CURRENT_USER=object(),
            KEY_SET_VALUE=2,
            REG_SZ=1,
            OpenKey=Mock(return_value=key),
            QueryValueEx=Mock(return_value=("python --background", 1)),
            SetValueEx=Mock(),
            DeleteValue=Mock(),
        )
        with patch.dict(sys.modules, {"winreg": winreg}), \
                patch.object(platform_utils, "IS_WINDOWS", True), \
                patch.object(platform_utils, "_launch_command", return_value=["python", "main.py"]):
            self.assertTrue(platform_utils.launch_at_login_enabled())
            platform_utils.set_launch_at_login(True)
            platform_utils.set_launch_at_login(False)

        self.assertIn("--background", winreg.SetValueEx.call_args.args[4])
        winreg.DeleteValue.assert_called_once()


if __name__ == "__main__":
    unittest.main()
