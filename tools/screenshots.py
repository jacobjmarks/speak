"""Render the main window, overlay and first-run onboarding in each state to PNGs; no real mic/models/hotkey needed.

    python -m tools.screenshots [out_dir]      (default: %TEMP%\\speak-shots)

Settings and history go to a throwaway dir, so your real ones are untouched. The throwaway settings mark first-run
setup as done so the main window shows; onboarding is captured separately with a fake microphone and speed test.
Then open the PNGs with the `view` tool to check the UI.
Edit `STEPS` to capture other states; each step runs 500 ms after the previous one.
"""
import json
import math
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from speak import audio, config, history, hotkey, tidy
from speak.benchmark import Result

scratch = Path(tempfile.mkdtemp(prefix="speak-shots-"))
config.SETTINGS_FILE = scratch / "settings.json"
config.HISTORY_FILE = scratch / "history.sqlite3"
config.SETTINGS_FILE.write_text(json.dumps({"onboarding_done": True, "theme": "Light"}), encoding="utf-8")
hotkey.register = lambda *a, **k: None


def level():
    return 0.08 + 0.07 * math.sin(time.monotonic() * 5)


class FakeMicrophone:
    """Onboarding's mic check reads `level`; nothing is recorded."""

    def __init__(self, *args, **kwargs):
        pass

    level = property(lambda self: 0.3 + 0.2 * math.sin(time.monotonic() * 4))
    start = stop = close = lambda self: None


audio.Microphone = FakeMicrophone

from speak.ui import app as A  # noqa: E402  (after the config patch)
from speak.ui import onboarding  # noqa: E402

onboarding.common.ANIMATE = False  # screens are complete the moment they appear

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "speak-shots"
OUT.mkdir(parents=True, exist_ok=True)

qa = QApplication(sys.argv)
s = A.SpeakApp(qa, background=False)
w = s.window
w.dictate.mic.level_source = level
s.overlay.level_source = level

# The speed test answers after a moment with a plausible result instead of running the real pipeline.
plan = tidy.Plan("auto", config.SMALL_MODEL, "literal", None, "")
w.onboarding.test_requested.disconnect()
w.onboarding.test_requested.connect(lambda *_: QTimer.singleShot(200, lambda: w.onboarding.set_result(
    Result(4.0, 0.0, 0.42, 0.31, "so i was thinking we could meet on wednesday",
           "So I was thinking we could meet on Wednesday.", plan))))


def fake_history():
    now = datetime.now().astimezone()
    rows = [(now - timedelta(minutes=m), text) for m, text in (
        (3, "So I was thinking we could meet on Wednesday."),
        (48, "Can you send me the slides before the call? Thanks."),
        (60 * 26, "Remind me to book the car service for next week."),
        (60 * 24 * 6, "The draft looks good. Two small comments on the intro, otherwise ship it."))]
    history.recent = lambda limit=500: [(when.isoformat(timespec="seconds"), text) for when, text in rows]


def shot(name, widget=None):
    (widget or w).grab().save(str(OUT / f"{name}.png"))


def settings(category):
    w.show_page(2)
    w.settings.show_category(category)


def onboarding_step(index):
    w.show_onboarding(True)
    w.onboarding.go(index)


def step_names():
    return ("welcome", "theme", "mic", "keys", "tidy", "look", "updates", "done")


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
    # settings: each category, a changed hidden option, open More options, search, a narrow window
    lambda: settings("dictation"),
    lambda: shot("10-settings-dictation"),
    lambda: settings("text"),
    lambda: shot("11-settings-text"),
    lambda: settings("indicator"),
    lambda: shot("12-settings-indicator"),
    lambda: settings("app"),
    lambda: shot("13-settings-app"),
    lambda: settings("updates"),
    lambda: shot("14-settings-updates"),
    lambda: (settings("text"), s._update({"press_enter": True})),
    lambda: shot("15-settings-changed-hidden"),
    lambda: w.settings.sections["typing"].more.click(),
    lambda: shot("16-settings-more-options"),
    lambda: (w.settings.search.setFocus(), w.settings.search.setText("memory")),
    lambda: shot("17-settings-search"),
    lambda: w.settings.search.setText("zzz"),
    lambda: shot("18-settings-search-empty"),
    lambda: (w.settings.search.clear(), w.resize(640, 480)),
    lambda: shot("19-settings-compact"),
    lambda: w.resize(1000, 760),
    lambda: (fake_history(), s._update({"history_enabled": True}), w.show_page(1)),
    lambda: shot("20-history"),
    lambda: w.show_page(3),
    lambda: shot("21-about"),
    lambda: s._update({"theme": "Dark"}),
    lambda: (w.show_page(0), w.dictate.set_mode("listening"), s.overlay.set_mode("listening"),
             s.overlay.set_text("dark mode live preview")),
    lambda: (shot("22-dark"), shot("23-overlay-dark", s.overlay)),
    lambda: settings("text"),
    lambda: shot("24-dark-settings"),
    lambda: (w.settings.search.setText("enter"),),
    lambda: shot("25-dark-settings-search"),
    lambda: (w.settings.search.clear(), s._update({"theme": "Light"}), w.dictate.set_mode("idle")),
    # first-run onboarding, every step; the speed test shows a result
    *[f for i, name in enumerate(step_names()) for f in (
        lambda i=i: onboarding_step(i),
        lambda i=i, name=name: shot(f"{30 + i}-onboarding-{name}"),
    )],
    lambda: onboarding_step(w.onboarding.TIDY),
    lambda: w.onboarding.sample_button.click(),
    lambda: shot("38-onboarding-tidy-result"),
    lambda: (s._update({"theme": "Dark"}), onboarding_step(w.onboarding.KEYS)),
    lambda: shot("39-onboarding-dark-keys"),
    lambda: w.show_onboarding(False),
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
