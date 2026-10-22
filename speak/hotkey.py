"""Global hotkey: press + release callbacks (tap or hold-to-talk), shortcut capture, key sending, display names.

Windows and Linux use `pynput`; macOS uses its own Quartz event tap (`keytap_mac`) for listening and a pynput
Controller for typing. Combos are "+"-joined lowercase names, e.g. "ctrl+shift+space" or "right alt". Modifiers
may be sided ("right alt", "left ctrl"); unsided "alt" matches either side.
Wayland has no global key grabs; see docs/wayfinder/research/cross-platform.md (GlobalShortcuts portal).
"""
import threading
from typing import Callable

from .platform_utils import IS_MAC, IS_WINDOWS

_listener = None
_controller = None  # macOS: built on the main thread by prepare()
_held = threading.Event()

_ALIASES = {"control": "ctrl", "option": "alt", "command": "cmd", "win": "cmd", "windows": "cmd", "super": "cmd",
            "return": "enter", "escape": "esc", "altgr": "right alt", "alt gr": "right alt",
            "right option": "right alt", "left option": "left alt"}
_MODIFIERS = ("ctrl", "alt", "shift", "cmd")
_CAPTURE_TIMEOUT = 15


def _parts(combo: str) -> list:
    return [_ALIASES.get(p.strip(), p.strip()) for p in combo.lower().split("+") if p.strip()]


def prepare() -> None:
    """macOS only: call on the main thread at startup and when the app is brought forward.

    Building a pynput Controller reads the keyboard layout through the Text Services Manager, which macOS 14+
    only allows on the main thread; `send` then reuses it from any thread.
    """
    if not IS_MAC:
        return
    global _controller
    from pynput import keyboard as kb

    from .keytap_mac import refresh_layout

    refresh_layout()
    _controller = kb.Controller()


def _names(key) -> set:
    """All names a pynput key answers to, e.g. Key.alt_gr -> {"alt", "right alt"}."""
    name = getattr(key, "name", None)
    if name:
        for suffix, side in (("_l", "left"), ("_r", "right"), ("_gr", "right")):
            if name.endswith(suffix):
                base = _ALIASES.get(name.removesuffix(suffix), name.removesuffix(suffix))
                return {base, f"{side} {base}"}
        return {_ALIASES.get(name, name)}
    char = getattr(key, "char", None)
    if char and ord(char[0]) < 32:  # ctrl+letter arrives as a control character on some platforms
        char = chr(ord(char[0]) + 96)
    vk = getattr(key, "vk", None)
    if not char and vk is not None and (48 <= vk <= 57 or 65 <= vk <= 90):
        char = chr(vk)  # Windows reports ctrl+letter as a bare virtual-key code
    return {(char or str(key)).lower()}


def _is_modifier(name: str) -> bool:
    return name.split(" ")[-1] in _MODIFIERS


def _mask_menu() -> None:
    """Tapping Alt or Win alone opens app menus / Start. A dummy key while it's down cancels that (like AutoHotkey)."""
    import ctypes

    user32 = ctypes.windll.user32
    user32.keybd_event(0xE8, 0, 0, 0)  # 0xE8: unassigned virtual key
    user32.keybd_event(0xE8, 0, 2, 0)


def _listen(on_press: Callable[[set], None], on_release: Callable[[set], None], suppress: bool = False):
    """Start a global key listener whose callbacks get the set of names each key answers to; returns it (`.stop()`).

    Raises PermissionError on macOS when Input Monitoring (or, to suppress keys, Accessibility) is missing.
    """
    if IS_MAC:
        from .keytap_mac import KeyTap

        tap = KeyTap(on_press, on_release, suppress)
        tap.start()
        return tap
    from pynput import keyboard as kb

    listener = kb.Listener(on_press=lambda key: on_press(_names(key)), on_release=lambda key: on_release(_names(key)),
                           suppress=suppress)
    listener.start()
    return listener


def register(combo: str, on_press: Callable[[], None], on_release: Callable[[], None]) -> None:
    """Call `on_press` when the combo goes down and `on_release` when any of its keys comes up.

    Key autorepeat while held does not re-fire `on_press`. Callbacks run on the listener thread.
    """
    unregister()
    global _listener
    _held.clear()
    wanted, down = set(_parts(combo)), set()
    mask = IS_WINDOWS and all(_is_modifier(p) for p in wanted) and any(p.endswith(("alt", "cmd")) for p in wanted)

    def press(names):
        down.update(names)
        if wanted <= down and not _held.is_set():
            _held.set()
            if mask:
                threading.Thread(target=_mask_menu, daemon=True).start()
            on_press()

    def release(names):
        down.difference_update(names)
        if wanted & names and _held.is_set():
            _held.clear()
            on_release()

    _listener = _listen(press, release)


def unregister() -> None:
    global _listener
    if _listener is not None:
        try:
            _listener.stop()
        except Exception:
            pass
    _listener = None


def capture() -> str:
    """Block until the user presses and releases a key combination; returns it ("" on timeout).

    Keys are swallowed while capturing so they don't act on the focused window. A lone modifier keeps its side
    ("right alt"); modifiers in a combo don't ("ctrl+shift+space").
    """
    order, down, done = [], set(), threading.Event()

    def press(names):
        down.update(names)
        name = max(names, key=len)  # sided name if there is one
        if name not in order:
            order.append(name)

    def release(names):
        down.difference_update(names)
        if order and not down:
            done.set()

    listener = _listen(press, release, suppress=True)
    try:
        done.wait(_CAPTURE_TIMEOUT)
    finally:
        listener.stop()
    if not done.is_set():
        return ""
    if all(_is_modifier(n) for n in order):
        return order[0] if len(order) == 1 else "+".join(sorted({n.split(" ")[-1] for n in order}, key=_MODIFIERS.index))
    mods = {n.split(" ")[-1] for n in order if _is_modifier(n)}
    return "+".join([m for m in _MODIFIERS if m in mods] + [n for n in order if not _is_modifier(n)])


def _pynput_key(part: str):
    from pynput import keyboard as kb

    if len(part) == 1:
        return part
    side, _, base = part.rpartition(" ")
    return getattr(kb.Key, f"{base}_{side[0]}" if side else base)


def send(combo: str) -> None:
    from pynput import keyboard as kb

    if IS_MAC:
        if _controller is None:
            raise RuntimeError("hotkey.prepare() must run on the main thread before send()")
        controller = _controller
    else:
        controller = kb.Controller()
    keys = [_pynput_key(p) for p in _parts(combo)]
    for key in keys:
        controller.press(key)
    for key in reversed(keys):
        controller.release(key)


def display(combo: str) -> str:
    """Human-friendly label, e.g. "Ctrl + Shift + Space", "Right Alt" (⌘/⌥ names on macOS)."""
    names = {"cmd": "⌘" if IS_MAC else "Win", "alt": "⌥" if IS_MAC else "Alt"}

    def label(part):
        side, _, base = part.rpartition(" ")
        if base.startswith("key") and base[3:].isdigit():  # a key with no known name (macOS keycode)
            base = f"key {base[3:]}"
        return " ".join(([side.capitalize()] if side else []) + [names.get(base, base.capitalize())])
    return " + ".join(label(p) for p in _parts(combo))
