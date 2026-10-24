"""macOS global key listener on a Quartz event tap.

Used instead of pynput's listener, which asks the Text Services Manager for the keyboard layout from its own
thread (macOS 14+ kills the process for that) and only fails silently when Input Monitoring is missing.
Callbacks get the set of names a key answers to, e.g. {"cmd", "right cmd"} or {"v"}, and run on the tap's thread.
"""
import logging
import threading
from typing import Callable

from Quartz import (CFMachPortCreateRunLoopSource, CFRunLoopAddSource, CFRunLoopGetCurrent, CFRunLoopRunInMode,
                    CFRunLoopStop, CGEventGetFlags, CGEventGetIntegerValueField, CGEventMaskBit, CGEventTapCreate,
                    CGEventTapEnable, kCFRunLoopDefaultMode, kCGEventFlagMaskAlternate, kCGEventFlagMaskCommand,
                    kCGEventFlagMaskControl, kCGEventFlagMaskShift, kCGEventFlagsChanged, kCGEventKeyDown,
                    kCGEventKeyUp, kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput,
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

# Keys that type nothing. Same keycodes on every keyboard (ANSI, ISO, JIS), unlike printable keys.
_SPECIAL = {36: "enter", 48: "tab", 49: "space", 51: "backspace", 53: "esc", 57: "caps_lock", 117: "delete",
            123: "left", 124: "right", 125: "down", 126: "up", 115: "home", 119: "end", 116: "page_up",
            121: "page_down", 122: "f1", 120: "f2", 99: "f3", 118: "f4", 96: "f5", 97: "f6", 98: "f7", 100: "f8",
            101: "f9", 109: "f10", 103: "f11", 111: "f12", 105: "f13", 107: "f14", 113: "f15", 106: "f16",
            64: "f17", 79: "f18", 80: "f19", 90: "f20",
            # numpad: named apart from the main-row keys that type the same character
            82: "num0", 83: "num1", 84: "num2", 85: "num3", 86: "num4", 87: "num5", 88: "num6", 89: "num7",
            91: "num8", 92: "num9", 65: "num_decimal", 67: "num_multiply", 69: "num_plus", 78: "num_minus",
            75: "num_divide", 81: "num_equals", 76: "num_enter", 71: "num_clear"}


_chars = {}  # keycode -> the character the current layout types for it (no modifiers); see refresh_layout()


def refresh_layout() -> None:
    """Read the active keyboard layout. Main thread only: macOS 14+ kills the process for asking from another."""
    import ctypes
    import ctypes.util

    carbon = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Carbon"))
    core = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
    for name in ("TISCopyCurrentKeyboardLayoutInputSource", "TISCopyCurrentASCIICapableKeyboardLayoutInputSource"):
        getattr(carbon, name).restype = ctypes.c_void_p
    carbon.TISGetInputSourceProperty.restype = ctypes.c_void_p
    carbon.TISGetInputSourceProperty.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    carbon.LMGetKbdType.restype = ctypes.c_uint8
    core.CFDataGetBytePtr.restype = ctypes.c_void_p
    core.CFDataGetBytePtr.argtypes = [ctypes.c_void_p]
    core.CFRelease.argtypes = [ctypes.c_void_p]
    carbon.UCKeyTranslate.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint32,
                                      ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
                                      ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_uint16)]
    property_key = ctypes.c_void_p.in_dll(carbon, "kTISPropertyUnicodeKeyLayoutData")

    # Input methods such as Japanese Romaji carry no layout data; fall back to the ASCII-capable layout.
    for name in ("TISCopyCurrentKeyboardLayoutInputSource", "TISCopyCurrentASCIICapableKeyboardLayoutInputSource"):
        source = getattr(carbon, name)()
        if not source:
            continue
        try:
            data = carbon.TISGetInputSourceProperty(source, property_key)
            layout = core.CFDataGetBytePtr(data) if data else None
            if not layout:
                continue
            kbd_type, found = carbon.LMGetKbdType(), {}
            for keycode in range(128):
                dead, length = ctypes.c_uint32(), ctypes.c_ulong()
                buffer = (ctypes.c_uint16 * 4)()
                carbon.UCKeyTranslate(layout, keycode, 0, 0, kbd_type, 1, ctypes.byref(dead), 4,  # 1: no dead keys
                                      ctypes.byref(length), buffer)
                text = "".join(chr(c) for c in buffer[:length.value])
                if text and text.isprintable() and text.strip():
                    found[keycode] = text.lower()
            global _chars
            _chars = found
            return
        finally:
            core.CFRelease(source)


def _key_name(keycode: int) -> str:
    """Special keys by name; any other key by the character the user's layout types for it, else \"key<code>\"."""
    return _SPECIAL.get(keycode) or _chars.get(keycode) or f"key{keycode}"


class KeyTap:
    def __init__(self, on_press: Callable[[set], bool | None], on_release: Callable[[set], bool | None], suppress: bool = False,
                 suppress_keys: bool = False):
        self._on_press, self._on_release, self._suppress = on_press, on_release, suppress
        self._suppress_keys = suppress_keys
        self._tap = None
        self._loop = None
        self._running = False

    def start(self) -> None:
        """Raises PermissionError if macOS refuses the tap (no Input Monitoring, or no Accessibility to suppress)."""
        mask = CGEventMaskBit(kCGEventKeyDown) | CGEventMaskBit(kCGEventKeyUp) | CGEventMaskBit(kCGEventFlagsChanged)
        options = kCGEventTapOptionDefault if self._suppress or self._suppress_keys else kCGEventTapOptionListenOnly
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
        consumed = False
        try:
            keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            flags = CGEventGetFlags(event)
            if event_type == kCGEventFlagsChanged:
                modifier = _MODIFIERS.get(keycode)
                if modifier is None:
                    return event
                names, device_bit, generic = modifier
                pressed = bool(flags & device_bit) if flags & _DEVICE_BITS else bool(flags & generic)
                consumed = (self._on_press if pressed else self._on_release)(set(names))
            else:
                names = {_key_name(keycode)}
                consumed = (self._on_press if event_type == kCGEventKeyDown else self._on_release)(names)
        except Exception:
            log.exception("key event handler failed")
        return None if self._suppress or (self._suppress_keys and consumed) else event
