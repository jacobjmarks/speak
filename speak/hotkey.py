"""Global hotkey registration (press + release, for hold-to-talk), capture, and key sending.

Windows uses `keyboard` (no elevation needed); macOS and Linux X11 use `pynput`.
Combos are stored in `keyboard` syntax, e.g. "ctrl+shift+space".
Wayland has no global key grabs; see docs/wayfinder/research/cross-platform.md (GlobalShortcuts portal).
"""
import threading
import time
from typing import Callable

from .platform_utils import IS_MAC, IS_WINDOWS

_handle = None
_held = threading.Event()

_ALIASES = {"control": "ctrl", "option": "alt", "command": "cmd", "win": "cmd", "windows": "cmd",
            "super": "cmd", "return": "enter", "escape": "esc"}
_MODIFIERS = ("ctrl", "alt", "shift", "cmd")


def _parts(combo: str) -> list:
    return [_ALIASES.get(p.strip(), p.strip()) for p in combo.lower().split("+") if p.strip()]


def _to_pynput(combo: str) -> str:
    return "+".join(f"<{p}>" if len(p) > 1 else p for p in _parts(combo))


def _key_name(key) -> str:
    char = getattr(key, "char", None)
    if char and ord(char[0]) < 32:  # ctrl+letter arrives as a control character on some platforms
        char = chr(ord(char[0]) + 96)
    vk = getattr(key, "vk", None)
    if not char and getattr(key, "name", None) is None and vk is not None and (48 <= vk <= 57 or 65 <= vk <= 122):
        char = chr(vk)  # Windows reports ctrl+letter as a bare virtual-key code
    name = (char or getattr(key, "name", None) or str(key)).lower()
    for suffix in ("_l", "_r", "_gr"):
        name = name.removesuffix(suffix)
    return _ALIASES.get(name, name)


def register(combo: str, on_press: Callable[[], None], on_release: Callable[[], None]) -> None:
    """Call `on_press` when the combo goes down and `on_release` when any of its keys comes up.

    Key autorepeat while held does not re-fire `on_press`. Callbacks run on a background thread.
    """
    unregister()
    global _handle
    _held.clear()
    if IS_WINDOWS:
        import keyboard

        def pressed():
            if _held.is_set():
                return
            _held.set()
            on_press()

            def wait_release():
                while keyboard.is_pressed(combo):
                    time.sleep(0.02)
                _held.clear()
                on_release()
            threading.Thread(target=wait_release, daemon=True).start()

        _handle = keyboard.add_hotkey(combo, pressed)
    else:
        from pynput import keyboard as kb

        wanted, down = set(_parts(combo)), set()

        def press(key):
            down.add(_key_name(key))
            if wanted <= down and not _held.is_set():
                _held.set()
                on_press()

        def release(key):
            name = _key_name(key)
            down.discard(name)
            if name in wanted and _held.is_set():
                _held.clear()
                on_release()

        _handle = kb.Listener(on_press=press, on_release=release)
        _handle.start()


def unregister() -> None:
    global _handle
    if _handle is None:
        return
    try:
        if IS_WINDOWS:
            import keyboard

            keyboard.remove_hotkey(_handle)
        else:
            _handle.stop()
    except Exception:
        pass
    _handle = None


def capture() -> str:
    """Block until the user presses a key combination; returns it (e.g. "ctrl+shift+space")."""
    if IS_WINDOWS:
        import keyboard

        return keyboard.read_hotkey(suppress=True)
    from pynput import keyboard as kb

    pressed, done = [], threading.Event()

    def on_press(key):
        name = _key_name(key)
        if name not in pressed:
            pressed.append(name)
        if name not in _MODIFIERS:
            done.set()
            return False

    with kb.Listener(on_press=on_press):
        done.wait()
    return "+".join([m for m in _MODIFIERS if m in pressed] + [k for k in pressed if k not in _MODIFIERS])


def send(combo: str) -> None:
    if IS_WINDOWS:
        import keyboard

        keyboard.send(combo)
        return
    from pynput import keyboard as kb

    controller = kb.Controller()
    keys = [getattr(kb.Key, p) if len(p) > 1 else p for p in _parts(combo)]
    for key in keys:
        controller.press(key)
    for key in reversed(keys):
        controller.release(key)


def display(combo: str) -> str:
    """Human-friendly label, e.g. "Ctrl + Shift + Space" (⌘ names on macOS)."""
    names = {"cmd": "⌘" if IS_MAC else "Win", "alt": "⌥" if IS_MAC else "Alt"}
    return " + ".join(names.get(p, p.capitalize()) for p in _parts(combo))
