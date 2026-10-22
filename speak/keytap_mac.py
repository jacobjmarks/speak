"""macOS global key listener on a Quartz event tap.

Used instead of pynput's listener, which asks the Text Services Manager for the keyboard layout from its own
thread (macOS 14+ kills the process for that) and only fails silently when Input Monitoring is missing.
Callbacks get the set of names a key answers to, e.g. {"cmd", "right cmd"} or {"v"}, and run on the tap's thread.
"""
import logging
import threading
from typing import Callable

from Quartz import (CFMachPortCreateRunLoopSource, CFRunLoopAddSource, CFRunLoopGetCurrent, CFRunLoopRunInMode,
                    CFRunLoopStop, CGEventGetFlags, CGEventGetIntegerValueField, CGEventKeyboardGetUnicodeString,
                    CGEventMaskBit, CGEventTapCreate, CGEventTapEnable, kCFRunLoopDefaultMode, kCGEventFlagMaskAlternate,
                    kCGEventFlagMaskCommand, kCGEventFlagMaskControl, kCGEventFlagMaskShift, kCGEventFlagsChanged,
                    kCGEventKeyDown, kCGEventKeyUp, kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput,
                    kCGEventTapOptionDefault, kCGEventTapOptionListenOnly, kCGHeadInsertEventTap,
                    kCGKeyboardEventKeycode, kCGSessionEventTap)

log = logging.getLogger(__name__)

NOT_ALLOWED = ("macOS isn't letting Speak hear key presses. Under System Settings > Privacy & Security > "
               "Input Monitoring, remove Speak and add it again (use the + button), then restart Speak.")

# keycode -> (names, device-dependent flag bit, generic flag mask)
_MODIFIERS = {
    0x37: ({"cmd", "left cmd"}, 0x8, kCGEventFlagMaskCommand),
    0x36: ({"cmd", "right cmd"}, 0x10, kCGEventFlagMaskCommand),
    0x3A: ({"alt", "left alt"}, 0x20, kCGEventFlagMaskAlternate),
    0x3D: ({"alt", "right alt"}, 0x40, kCGEventFlagMaskAlternate),
    0x38: ({"shift", "left shift"}, 0x2, kCGEventFlagMaskShift),
    0x3C: ({"shift", "right shift"}, 0x4, kCGEventFlagMaskShift),
    0x3B: ({"ctrl", "left ctrl"}, 0x1, kCGEventFlagMaskControl),
    0x3E: ({"ctrl", "right ctrl"}, 0x2000, kCGEventFlagMaskControl),
}
_DEVICE_BITS = 0x1 | 0x2 | 0x4 | 0x8 | 0x10 | 0x20 | 0x40 | 0x2000

_SPECIAL = {36: "enter", 48: "tab", 49: "space", 51: "backspace", 53: "esc", 57: "caps_lock", 117: "delete",
            123: "left", 124: "right", 125: "down", 126: "up", 115: "home", 119: "end", 116: "page_up",
            121: "page_down", 122: "f1", 120: "f2", 99: "f3", 118: "f4", 96: "f5", 97: "f6", 98: "f7", 100: "f8",
            101: "f9", 109: "f10", 103: "f11", 111: "f12", 105: "f13", 107: "f14", 113: "f15", 106: "f16",
            64: "f17", 79: "f18", 80: "f19", 90: "f20"}

# US-layout fallback for when the typed character isn't usable (Option or Control held)
_ANSI = {0: "a", 1: "s", 2: "d", 3: "f", 4: "h", 5: "g", 6: "z", 7: "x", 8: "c", 9: "v", 11: "b", 12: "q", 13: "w",
         14: "e", 15: "r", 16: "y", 17: "t", 18: "1", 19: "2", 20: "3", 21: "4", 22: "6", 23: "5", 24: "=", 25: "9",
         26: "7", 27: "-", 28: "8", 29: "0", 30: "]", 31: "o", 32: "u", 33: "[", 34: "i", 35: "p", 37: "l", 38: "j",
         39: "'", 40: "k", 41: ";", 42: "\\", 43: ",", 44: "/", 45: "n", 46: "m", 47: ".", 50: "`"}


def _key_name(event, keycode: int, flags: int) -> str:
    special = _SPECIAL.get(keycode)
    if special:
        return special
    if not flags & kCGEventFlagMaskAlternate:
        length, chars = CGEventKeyboardGetUnicodeString(event, 8, None, None)
        if length and chars.isprintable() and chars.strip():
            return chars.lower()
    return _ANSI.get(keycode, f"key{keycode}")


class KeyTap:
    def __init__(self, on_press: Callable[[set], None], on_release: Callable[[set], None], suppress: bool = False):
        self._on_press, self._on_release, self._suppress = on_press, on_release, suppress
        self._tap = None
        self._loop = None
        self._running = False

    def start(self) -> None:
        """Raises PermissionError if macOS refuses the tap (no Input Monitoring, or no Accessibility to suppress)."""
        mask = CGEventMaskBit(kCGEventKeyDown) | CGEventMaskBit(kCGEventKeyUp) | CGEventMaskBit(kCGEventFlagsChanged)
        options = kCGEventTapOptionDefault if self._suppress else kCGEventTapOptionListenOnly
        self._tap = CGEventTapCreate(kCGSessionEventTap, kCGHeadInsertEventTap, options, mask, self._handle, None)
        if self._tap is None:
            raise PermissionError(NOT_ALLOWED)
        self._running = True
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self) -> None:
        self._running = False
        if self._tap is not None:
            CGEventTapEnable(self._tap, False)
        if self._loop is not None:
            CFRunLoopStop(self._loop)

    def _run(self) -> None:
        source = CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._loop = CFRunLoopGetCurrent()
        CFRunLoopAddSource(self._loop, source, kCFRunLoopDefaultMode)
        CGEventTapEnable(self._tap, True)
        while self._running:
            CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.5, False)

    def _handle(self, proxy, event_type, event, refcon):
        if event_type in (kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput):
            CGEventTapEnable(self._tap, True)  # macOS pauses a tap that stalls; turn it back on
            return event
        try:
            keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            flags = CGEventGetFlags(event)
            if event_type == kCGEventFlagsChanged:
                modifier = _MODIFIERS.get(keycode)
                if modifier is None:
                    return event
                names, device_bit, generic = modifier
                pressed = bool(flags & device_bit) if flags & _DEVICE_BITS else bool(flags & generic)
                (self._on_press if pressed else self._on_release)(set(names))
            else:
                names = {_key_name(event, keycode, flags)}
                (self._on_press if event_type == kCGEventKeyDown else self._on_release)(names)
        except Exception:
            log.exception("key event handler failed")
        return None if self._suppress else event
