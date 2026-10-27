import math
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from speak import audio, output, permissions, platform_utils


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


class AudioTest(unittest.TestCase):
    """Input enumeration chooses usable devices and microphone capture reports RMS audio."""

    def test_device_listing_prefers_directsound_on_windows_and_filters_unusable_inputs(self):
        devices = [
            {"name": "wrong host", "hostapi": 0, "max_input_channels": 1},
            {"name": "Microsoft Sound Mapper - Input", "hostapi": 1, "max_input_channels": 1},
            {"name": "No input", "hostapi": 1, "max_input_channels": 0},
            {"name": "Microphone", "hostapi": 1, "max_input_channels": 1},
        ]
        sd = SimpleNamespace(
            query_hostapis=lambda: [{"name": "MME"}, {"name": "Windows DirectSound"}],
            query_devices=lambda *args, **kwargs: devices,
        )
        with patch.dict(sys.modules, {"sounddevice": sd}), patch.object(audio.sys, "platform", "win32"):
            self.assertEqual(["Microphone"], audio.input_devices())
            self.assertIsNone(audio._resolve("missing"))
            self.assertEqual(3, audio._resolve("Microphone"))

    def test_microphone_callback_reports_rms_and_stop_closes_stream(self):
        stream = Mock()
        sd = SimpleNamespace(
            query_devices=lambda *args, **kwargs: {"default_samplerate": 16000},
            RawInputStream=Mock(return_value=stream),
        )
        chunks = []
        with patch.dict(sys.modules, {"sounddevice": sd}):
            mic = audio.Microphone(chunks.append)
            mic.start()
            mic._callback(struct.pack("<hh", 3000, 0), 2, None, None)
            self.assertTrue(math.isclose(mic.level, math.sqrt(0.5)))
            self.assertEqual([struct.pack("<hh", 3000, 0)], chunks)
            self.assertEqual(2, mic.frames)
            mic.stop()

        stream.start.assert_called_once()
        stream.stop.assert_called_once()
        stream.close.assert_called_once()
        self.assertEqual(0.0, mic.level)


class OutputTest(unittest.TestCase):
    """Paste uses the clipboard safely and sends Enter only when requested."""

    def test_paste_restores_clipboard_and_only_sends_enter_when_requested(self):
        clipboard = {"text": "previous"}
        pyperclip = SimpleNamespace(paste=lambda: clipboard["text"],
                                    copy=lambda text: clipboard.update(text=text))
        with patch.dict(sys.modules, {"pyperclip": pyperclip}), \
                patch("speak.hotkey.send") as send, patch.object(output.time, "sleep"), \
                patch.object(platform_utils, "IS_MAC", False):
            self.assertTrue(output.paste("dictated", lambda: True))

        self.assertEqual("previous", clipboard["text"])
        self.assertEqual(["ctrl+v", "enter"], [call.args[0] for call in send.call_args_list])

    def test_paste_fails_if_clipboard_does_not_accept_text(self):
        pyperclip = SimpleNamespace(paste=lambda: "unchanged", copy=lambda text: None)
        with patch.dict(sys.modules, {"pyperclip": pyperclip}), \
                patch("speak.hotkey.send") as send:
            with self.assertRaisesRegex(RuntimeError, "Clipboard unavailable"):
                output.paste("dictated")
        send.assert_not_called()


class PermissionTest(unittest.TestCase):
    """The setup flow reports required permissions that are not yet granted."""

    def test_missing_permissions_reports_only_ungranted_required_items(self):
        required = (permissions.Permission("mic", "Mic", "", ""), permissions.Permission("keys", "Keys", "", ""))
        with patch.object(permissions, "REQUIRED", required), \
                patch.object(permissions, "granted", side_effect=lambda item: item == "mic"):
            self.assertEqual([required[1]], permissions.missing())

    def test_input_monitoring_falls_back_to_settings_when_macos_wont_prompt(self):
        from types import SimpleNamespace
        quartz = SimpleNamespace(CGRequestListenEventAccess=Mock(return_value=False))
        with patch.dict(sys.modules, {"Quartz": quartz}), \
                patch.object(permissions, "open_settings") as open_settings:
            permissions.request("input_monitoring")
        open_settings.assert_called_once_with("input_monitoring")

    def test_input_monitoring_request_does_not_open_settings_when_granted(self):
        from types import SimpleNamespace
        quartz = SimpleNamespace(CGRequestListenEventAccess=Mock(return_value=True))
        with patch.dict(sys.modules, {"Quartz": quartz}), \
                patch.object(permissions, "open_settings") as open_settings:
            permissions.request("input_monitoring")
        open_settings.assert_not_called()


if __name__ == "__main__":
    unittest.main()
