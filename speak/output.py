"""Clipboard copy and paste-into-focused-app."""
import time
from typing import Callable

from .platform_utils import paste_shortcut


def copy(text: str) -> None:
    import pyperclip

    pyperclip.copy(text)


def paste(text: str, press_enter: Callable[[], bool] = lambda: False) -> bool:
    """Paste via the clipboard, then restore the previous clipboard contents. Raises on failure.

    After pasting, presses Enter if `press_enter()` (checked after the paste lands) is true; returns whether it did.
    """
    import pyperclip

    from . import hotkey

    previous = pyperclip.paste()
    pyperclip.copy(text)
    if pyperclip.paste() != text:
        raise RuntimeError("Clipboard unavailable")
    hotkey.send(paste_shortcut())
    time.sleep(0.3)
    entered = press_enter()
    if entered:
        hotkey.send("enter")
    time.sleep(0.5)
    if pyperclip.paste() == text:
        pyperclip.copy(previous)
    return entered
