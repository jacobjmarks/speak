"""Render the main window and overlay in each state to PNGs, no real mic/models/hotkey needed.

    python -m tools.screenshots [out_dir]      (default: %TEMP%\speak-shots)

Settings and history go to a throwaway dir, so your real ones are untouched.
Then open the PNGs with the `view` tool to check the UI.
Edit `STEPS` to capture other states; each step runs 500 ms after the previous one.
"""
import math
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from speak import config, hotkey

scratch = Path(tempfile.mkdtemp(prefix="speak-shots-"))
config.SETTINGS_FILE = scratch / "settings.json"
config.HISTORY_FILE = scratch / "history.sqlite3"
hotkey.register = lambda *a, **k: None

from speak.ui import app as A  # noqa: E402  (after the config patch)

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "speak-shots"
OUT.mkdir(parents=True, exist_ok=True)

qa = QApplication(sys.argv)
s = A.SpeakApp(qa, background=False)
w = s.window


def level():
    return 0.08 + 0.07 * math.sin(time.monotonic() * 5)


w.dictate.mic.level_source = level
s.overlay.level_source = level


def shot(name, widget=None):
    (widget or w).grab().save(str(OUT / f"{name}.png"))


STEPS = [
    lambda: shot("1-idle"),
    lambda: (w.dictate.set_mode("listening"), s.overlay.set_mode("listening"),
             s.overlay.set_text("so I was thinking we could meet on Tuesday no actually Wednesday")),
    lambda: (shot("2-listening"), shot("3-overlay-listening", s.overlay)),
    lambda: (w.dictate.set_mode("processing"), s.overlay.set_mode("processing")),
    lambda: (shot("4-processing"), shot("5-overlay-processing", s.overlay)),
    lambda: (w.dictate.set_mode("preparing", 42), s.overlay.set_mode("preparing", 42), s.overlay.set_text("")),
    lambda: (shot("6-download"), shot("7-overlay-download", s.overlay)),
    lambda: s._on_result("So I was thinking we could meet on Wednesday.", ""),
    lambda: (shot("8-done"), shot("9-overlay-done", s.overlay)),
    lambda: w.show_page(2),
    lambda: shot("10-settings"),
    lambda: w.settings.advanced_toggle.setChecked(True),
    lambda: QTimer.singleShot(300, lambda: shot("11-settings-advanced")),
    lambda: w.show_page(1),
    lambda: shot("12-history"),
    lambda: s._update({"theme": "Dark"}),
    lambda: (w.show_page(0), w.dictate.set_mode("listening"), s.overlay.set_mode("listening"),
             s.overlay.set_text("dark mode live preview")),
    lambda: (shot("13-dark"), shot("14-overlay-dark", s.overlay)),
    lambda: w.show_page(2),
    lambda: shot("15-dark-settings"),
]


def step(i=0):
    if i >= len(STEPS):
        s.quit()  # stops the runtime servers too; qa.quit() alone leaves them running
        return
    try:
        STEPS[i]()
    except Exception:  # an exception inside a Qt callback would otherwise hang the event loop
        import traceback
        traceback.print_exc()
        qa.exit(1)
        return
    QTimer.singleShot(500, lambda: step(i + 1))


QTimer.singleShot(800, step)
qa.exec()
print("wrote", len(list(OUT.glob("*.png"))), "images to", OUT)
