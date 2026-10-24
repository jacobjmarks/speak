import importlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from speak import hotkey


class HotkeyRegistrationTest(unittest.TestCase):
    """Shortcut handling consumes only matching keys and cancels only active dictation."""

    def test_only_matching_shortcut_events_are_consumed(self):
        callbacks = {}
        pressed, released = [], []
        with patch.object(hotkey, "_listen", side_effect=lambda down, up, **_: callbacks.update(
                press=down, release=up)), patch.object(hotkey, "IS_WINDOWS", False):
            hotkey.register("ctrl+space", lambda: pressed.append(True), lambda: released.append(True),
                            lambda: None, lambda: False)

        try:
            self.assertFalse(callbacks["press"]({"ctrl", "left ctrl"}))
            self.assertFalse(callbacks["press"]({"x"}))
            self.assertTrue(callbacks["press"]({"space"}))
            self.assertTrue(callbacks["press"]({"space"}))
            self.assertEqual(pressed, [True])
            self.assertTrue(callbacks["release"]({"space"}))
            self.assertFalse(callbacks["release"]({"x"}))
            self.assertFalse(callbacks["release"]({"ctrl", "left ctrl"}))
            self.assertEqual(released, [True])
        finally:
            hotkey.unregister()

    def test_escape_is_consumed_only_when_dictation_is_active(self):
        callbacks = {}
        cancellations = []
        active = False
        with patch.object(hotkey, "_listen", side_effect=lambda down, up, **_: callbacks.update(
                press=down, release=up)), patch.object(hotkey, "IS_WINDOWS", False):
            hotkey.register("right alt", lambda: None, lambda: None, lambda: cancellations.append(True),
                            lambda: active)

        try:
            self.assertFalse(callbacks["press"]({"esc"}))
            active = True
            self.assertTrue(callbacks["press"]({"esc"}))
            self.assertTrue(callbacks["release"]({"esc"}))
            self.assertEqual(cancellations, [True])
        finally:
            hotkey.unregister()

    def test_windows_filter_suppresses_only_consumed_events(self):
        instances = []

        class FakeListener:
            def __init__(self, **options):
                self.event_filter = options["win32_event_filter"]
                self.suppressed = 0
                instances.append(self)

            def _event_to_key(self, message, vk):
                return SimpleNamespace(name="space" if vk == 0x20 else None,
                                      char=None if vk == 0x20 else chr(vk).lower(), vk=vk)

            def suppress_event(self):
                self.suppressed += 1

            def start(self):
                pass

        pynput = SimpleNamespace(keyboard=SimpleNamespace(Listener=FakeListener))
        presses, releases = [], []
        with patch.object(hotkey, "IS_WINDOWS", True), patch.object(hotkey, "IS_MAC", False), \
                patch.dict(sys.modules, {"pynput": pynput}):
            listener = hotkey._listen(lambda names: presses.append(names) or names == {"space"},
                                      lambda names: releases.append(names) or names == {"space"},
                                      suppress_keys=True)

        self.assertFalse(listener.event_filter(0x100, SimpleNamespace(vkCode=ord("A"))))
        self.assertEqual(listener.suppressed, 0)
        self.assertFalse(listener.event_filter(0x100, SimpleNamespace(vkCode=0x20)))
        self.assertEqual(listener.suppressed, 1)
        self.assertFalse(listener.event_filter(0x101, SimpleNamespace(vkCode=0x20)))
        self.assertEqual(listener.suppressed, 2)
        self.assertEqual(presses, [{"a"}, {"space"}])
        self.assertEqual(releases, [{"space"}])


class MacKeyTapTest(unittest.TestCase):
    """The macOS Quartz tap suppresses only events consumed by Speak."""

    def test_only_consumed_shortcut_events_are_suppressed(self):
        names = (
            "CFMachPortCreateRunLoopSource", "CFRunLoopAddSource", "CFRunLoopGetCurrent", "CFRunLoopRunInMode",
            "CFRunLoopStop", "CGEventGetFlags", "CGEventGetIntegerValueField", "CGEventMaskBit",
            "CGEventTapCreate", "CGEventTapEnable", "kCFRunLoopDefaultMode", "kCGEventFlagMaskAlternate",
            "kCGEventFlagMaskCommand", "kCGEventFlagMaskControl", "kCGEventFlagMaskShift", "kCGEventFlagsChanged",
            "kCGEventKeyDown", "kCGEventKeyUp", "kCGEventTapDisabledByTimeout",
            "kCGEventTapDisabledByUserInput", "kCGEventTapOptionDefault", "kCGEventTapOptionListenOnly",
            "kCGHeadInsertEventTap", "kCGKeyboardEventKeycode", "kCGSessionEventTap",
        )
        quartz = types.ModuleType("Quartz")
        for index, name in enumerate(names):
            setattr(quartz, name, index + 1 if name.startswith("k") else Mock())
        with patch.dict(sys.modules, {"Quartz": quartz}):
            keytap_module = importlib.import_module("speak.keytap_mac")

        event = object()
        presses = []
        tap = keytap_module.KeyTap(lambda pressed: presses.append(pressed) or pressed == {"space"},
                                   lambda released: released == {"space"}, suppress_keys=True)
        with patch.object(keytap_module, "CGEventGetIntegerValueField", side_effect=[49, 0]), \
                patch.object(keytap_module, "CGEventGetFlags", return_value=0), \
                patch.object(keytap_module, "_key_name", side_effect=["space", "x"]):
            self.assertIsNone(tap._handle(None, keytap_module.kCGEventKeyDown, event, None))
            self.assertIs(event, tap._handle(None, keytap_module.kCGEventKeyDown, event, None))
        self.assertEqual(presses, [{"space"}, {"x"}])


if __name__ == "__main__":
    unittest.main()
