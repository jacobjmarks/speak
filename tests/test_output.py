import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from speak import output, platform_utils


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

    def test_enter_before_paste_is_sent_before_the_paste_keystroke(self):
        clipboard = {"text": "previous"}
        pyperclip = SimpleNamespace(paste=lambda: clipboard["text"],
                                    copy=lambda text: clipboard.update(text=text))
        with patch.dict(sys.modules, {"pyperclip": pyperclip}), \
                patch("speak.hotkey.send") as send, patch.object(output.time, "sleep"), \
                patch.object(platform_utils, "IS_MAC", False):
            output.paste("dictated", lambda: True, lambda: True)

        self.assertEqual(["enter", "ctrl+v", "enter"], [call.args[0] for call in send.call_args_list])

    def test_paste_fails_if_clipboard_does_not_accept_text(self):
        pyperclip = SimpleNamespace(paste=lambda: "unchanged", copy=lambda text: None)
        with patch.dict(sys.modules, {"pyperclip": pyperclip}), \
                patch("speak.hotkey.send") as send:
            with self.assertRaisesRegex(RuntimeError, "Clipboard unavailable"):
                output.paste("dictated")
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
