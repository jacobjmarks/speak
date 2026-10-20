"""Clipboard copy and paste-into-focused-app."""
import time

from .platform_utils import paste_shortcut


def copy(text: str) -> None:
    import pyperclip

    pyperclip.copy(text)


def paste(text: str) -> None:
    """Paste via the clipboard, then restore the previous clipboard contents. Raises on failure."""
    import pyperclip

    from . import hotkey

    previous = pyperclip.paste()
    pyperclip.copy(text)
    hotkey.send(paste_shortcut())
    time.sleep(0.8)
    if pyperclip.paste() == text:
        pyperclip.copy(previous)
