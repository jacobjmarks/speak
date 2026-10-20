"""Global hotkey registration, capture, and key sending.

Windows uses `keyboard` (no elevation needed); macOS and Linux X11 use `pynput`.
Combos are stored in `keyboard` syntax, e.g. "ctrl+shift+space".
Wayland has no global key grabs; see docs/wayfinder/research/cross-platform.md (GlobalShortcuts portal).
"""
import threading
from typing import Callable

from .platform_utils import IS_MAC, IS_WINDOWS

_handle = None

_ALIASES = {"control": "ctrl", "option": "alt", "command": "cmd", "win": "cmd", "windows": "cmd",
            "super": "cmd", "return": "enter", "escape": "esc"}
_MODIFIERS = ("ctrl", "alt", "shift", "cmd")


def _parts(combo: str) -> list:
    return [_ALIASES.get(p.strip(), p.strip()) for p in combo.lower().split("+") if p.strip()]


def _to_pynput(combo: str) -> str:
    return "+".join(f"<{p}>" if len(p) > 1 else p for p in _parts(combo))


def _key_name(key) -> str:
    name = (getattr(key, "char", None) or getattr(key, "name", None) or str(key)).lower()
    for suffix in ("_l", "_r", "_gr"):
        name = name.removesuffix(suffix)
    return _ALIASES.get(name, name)


def register(combo: str, callback: Callable[[], None]) -> None:
    unregister()
    global _handle
    if IS_WINDOWS:
        import keyboard

        _handle = keyboard.add_hotkey(combo, callback)
    else:
        from pynput import keyboard as kb

        _handle = kb.GlobalHotKeys({_to_pynput(combo): callback})
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
