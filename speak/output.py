"""Clipboard copy and paste-into-focused-app."""
import time
from typing import Callable

from .platform_utils import paste_shortcut


def copy(text: str) -> None:
    import pyperclip

    pyperclip.copy(text)


def paste(text: str, press_enter: Callable[[], bool] = lambda: False,
          press_enter_before: Callable[[], bool] = lambda: False) -> bool:
    """Paste via the clipboard, then restore the previous clipboard contents. Raises on failure.

    Before pasting, presses Enter if `press_enter_before()` is true.
    After pasting, presses Enter if `press_enter()` (checked right after the paste) is true; returns whether it did.
    """
    import pyperclip

    from . import hotkey

    previous = pyperclip.paste()
    pyperclip.copy(text)
    if pyperclip.paste() != text:
        raise RuntimeError("Clipboard unavailable")
    if press_enter_before():
        hotkey.send("enter")
        time.sleep(0.3)  # Gives the target time to handle Enter before the paste arrives.
    hotkey.send(paste_shortcut())
    time.sleep(0.3)
    entered = press_enter()
    if entered:
        hotkey.send("enter")
    time.sleep(0.5)
    if pyperclip.paste() == text:
        pyperclip.copy(previous)
    return entered
