import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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

    def test_linux_and_mac_login_entries_quote_paths_with_spaces(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "speak-startup"
            command = ["/opt/My Apps/Speak", "--background"]
            with patch.object(platform_utils, "_autostart_file", return_value=path), \
                    patch.object(platform_utils, "_launch_command", return_value=command[:1]):
                for mac in (False, True):
                    with patch.multiple(platform_utils, IS_WINDOWS=False, IS_MAC=mac):
                        platform_utils.set_launch_at_login(True)
                        self.assertEqual(Path(command[0]), platform_utils._login_target())

    def test_windows_login_startup_respects_task_manager_and_follows_the_exe(self):
        class Key(SimpleNamespace):
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        class Registry:
            HKEY_CURRENT_USER = "HKCU"
            KEY_SET_VALUE = 2
            REG_SZ = 1

            def __init__(self):
                self.values = {}

            def OpenKey(self, root, path, *_):
                return Key(path=path)

            def QueryValueEx(self, key, name):
                try:
                    return self.values[(key.path, name)], 1
                except KeyError:
                    raise OSError(name) from None

            def SetValueEx(self, key, name, _reserved, _kind, value):
                self.values[(key.path, name)] = value

            def DeleteValue(self, key, name):
                try:
                    del self.values[(key.path, name)]
                except KeyError:
                    raise OSError(name) from None

        registry = Registry()
        run, approved = platform_utils._RUN_KEY, platform_utils._APPROVED_KEY

        def command(exe):
            return subprocess.list2cmdline([str(exe), "--background"])

        with tempfile.TemporaryDirectory() as directory:
            old, new = Path(directory) / "Speak-1.0.0.exe", Path(directory) / "Speak-1.1.0.exe"
            new.touch()
            with patch.dict(sys.modules, {"winreg": registry}), patch.object(platform_utils, "IS_WINDOWS", True), \
                    patch.object(platform_utils, "_launch_command", return_value=[str(old)]):
                self.assertFalse(platform_utils.launch_at_login_enabled())

                registry.values[(approved, "Speak")] = b"\x03" + b"\0" * 11  # switched off in Task Manager
                platform_utils.set_launch_at_login(True)
                self.assertEqual(command(old), registry.values[(run, "Speak")])
                self.assertTrue(platform_utils.launch_at_login_enabled())

                registry.values[(approved, "Speak")] = b"\x03" + b"\0" * 11
                self.assertFalse(platform_utils.launch_at_login_enabled())

                # the exe was moved away: only a packaged build re-points the entry, and never re-enables it
                with patch.object(platform_utils, "_launch_command", return_value=[str(new)]):
                    platform_utils.refresh_launch_at_login()
                    self.assertEqual(command(old), registry.values[(run, "Speak")])
                    with patch.object(platform_utils.sys, "frozen", True, create=True):
                        platform_utils.refresh_launch_at_login()
                    self.assertEqual(command(new), registry.values[(run, "Speak")])
                    self.assertFalse(platform_utils.launch_at_login_enabled())

                    registry.values[(run, "Speak")] = command(old)
                    old.touch()  # target still exists: another copy owns the entry
                    with patch.object(platform_utils.sys, "frozen", True, create=True):
                        platform_utils.refresh_launch_at_login()
                    self.assertEqual(command(old), registry.values[(run, "Speak")])

                    platform_utils.repoint_launch_at_login(old, new)
                    self.assertEqual(command(new), registry.values[(run, "Speak")])
                    platform_utils.repoint_launch_at_login(old, old)
                    self.assertEqual(command(new), registry.values[(run, "Speak")])

                registry.values.pop((approved, "Speak"), None)
                platform_utils.set_launch_at_login(True)  # no "disabled" mark to clear
                platform_utils.set_launch_at_login(False)
                platform_utils.set_launch_at_login(False)  # already gone
                self.assertNotIn((run, "Speak"), registry.values)
                self.assertIsNone(platform_utils._login_target())

    def test_missing_or_corrupt_login_entries_have_no_target(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "entry"
            with patch.object(platform_utils, "_autostart_file", return_value=path), \
                    patch.object(platform_utils, "IS_WINDOWS", False):
                for mac in (False, True):
                    with patch.object(platform_utils, "IS_MAC", mac):
                        self.assertIsNone(platform_utils._login_target())
                        path.write_text("not an entry", encoding="utf-8")
                        self.assertIsNone(platform_utils._login_target())
                        path.unlink()
                        platform_utils.set_launch_at_login(False)


if __name__ == "__main__":
    unittest.main()
