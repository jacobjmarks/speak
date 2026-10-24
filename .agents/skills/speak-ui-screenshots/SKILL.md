---
name: speak-ui-screenshots
description: Render and visually inspect the Speak window and overlay across states for broad visual changes, visual regressions, or bugs spanning multiple screens. Use for shared layout/theme changes; focused UI behavior should use a targeted test instead.
---

# See the UI without driving it

`tools/screenshots.py` builds the real `SpeakApp`, forces each state with the page/overlay setters, and saves `QWidget.grab()` PNGs. Takes ~15 s, needs no human, microphone, or downloaded model.

This is a broad visual sweep, not the default check for every `ui/` change. For a single control or state, use a focused test and capture just that state if appearance is the requirement. For behavior such as a click, state transition, or saved setting, assert the behavior directly.

Before running, follow the process and instance collision preflight in `speak-verify`. The screenshot runner creates a separate `SpeakApp`; keep its output isolated and leave any pre-existing app or runtime process untouched.

```powershell
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe -m tools.screenshots              # -> %TEMP%\speak-shots\*.png
.\.venv\Scripts\python.exe -m tools.screenshots $env:TEMP\before   # custom dir
```

Then **open the PNGs with the `view` tool** (absolute path) and judge them: clipped text, wrong spacing, low contrast, misaligned items, the wrong state label. Fix, rerun, view again. Capture before/after into separate dirs to compare.

## What it does (so you can adapt it)

- Patches `config.SETTINGS_FILE` / `HISTORY_FILE` to a temp dir first, so real settings are untouched, and replaces `hotkey.register` with a no-op.
- `w = SpeakApp(...).window`; states via `w.dictate.set_mode("listening"|"processing"|"preparing", pct)`, `s.overlay.set_mode(...)`, `s.overlay.set_text(...)`, `s._on_result(text, note)`, `w.show_page(i)` (0 Dictate, 1 History, 2 Settings, 3 About), `w.settings.advanced_toggle.setChecked(True)`, `s._update({"theme": "Dark"})`.
- Fake mic level: `w.dictate.mic.level_source = s.overlay.level_source = lambda: ...` so the waveform animates.
- Steps run in a `QTimer` chain, 500 ms apart, so animations/layout settle. Add a `QTimer.singleShot(300, ...)` inside a step if something animates open (e.g. the Advanced section).

To capture a new state, add a lambda to `STEPS` that sets it and one that calls `shot("name")`. If an attribute name has changed, grep `speak/ui/pages.py` and `window.py` for the current one.

## Capturing the real screen (overlay on a live app, packaged exe)

Overlays are separate top-level windows and the real overlay only shows while dictating. For a live app, grab the screen from a second Python process:

```python
from PySide6.QtWidgets import QApplication
app = QApplication([])
QApplication.primaryScreen().grabWindow(0).save(r"C:\path\out.png")   # whole screen
```

The overlay appears near the cursor by default: crop around `QCursor.pos()` (multiply by `devicePixelRatio`) to get a small image that's cheap to view. Window-only grabs of a hidden or minimised window come out blank; show it first.

## Gotchas

- `grab()` renders the widget tree, not the OS compositor: it won't show native window shadows or the tray.
- If the script fails, it prints a traceback and exits 1 (a step raised inside a Qt callback). Read the output. If it ever hangs, stop it with `Stop-Process -Id`, then check for stray `llama-server`/`nemo-speech`.
- Colours and fonts belong in `ui/theme.py`; don't hard-code them in pages to fix a screenshot.
