---
name: speak-ui-harness
description: Start Speak, navigate the existing UI, and drive a specific screen or interaction that needs real-app validation beyond the automated Qt tests. Use for focused behavior checks on a page, control, state transition, or widget interaction; use the full screenshot sweep only for broad visual/regression coverage.
---

# Drive the app by the UI, not by guessing

Use this when a behavior needs validation in the real app beyond what the automated Qt tests cover: open a page, click a button, toggle a setting, check a state, or verify an interaction. Prefer a focused test in `tests/ui/` for repeatable UI behavior. Keep manual app-driving narrow and assert the actual widget state or signals, not a whole-window screenshot unless the requirement is visual.

## First: respect app collisions

Before starting Speak or changing the desktop state, do the process preflight in `speak-verify`: inspect existing `Speak`, `llama-server`, and `nemo-speech` processes, note whether the app is already running, and decide whether the test can be isolated. Do not close or interfere with a user's pre-existing Speak instance. Prefer an isolated temp settings dir, or a single existing instance that the test can target, not a second conflicting app.

## Start the app safely

Use the existing app entry point and the same process model as the app itself:

```powershell
$env:PYTHONIOENCODING="utf-8"
$env:PYTHONPATH=(Get-Location).Path
.\.venv\Scripts\python.exe main.py --background
```

For a script-driven test, prefer a `SpeakApp` object in-process with temp settings/history paths patched first, so the test is isolated and no user data is touched:

```python
from pathlib import Path
import tempfile
from PySide6.QtWidgets import QApplication
from speak import config
from speak.ui import app as app_mod

scratch = Path(tempfile.mkdtemp(prefix="speak-ui-"))
config.SETTINGS_FILE = scratch / "settings.json"
config.HISTORY_FILE = scratch / "history.sqlite3"
qa = QApplication([])
s = app_mod.SpeakApp(qa, background=False)
```

If the app is already running and the test can target it, use the existing instance instead of starting another. If the test cannot be isolated, stop and ask before continuing.

## Navigate to the screen you want

Use the window's page navigation API, not an ad hoc sequence of window operations. Names and indices are defined in `MainWindow`:

```python
w = s.window
w.show_page(0)  # Dictate
w.show_page(1)  # History
w.show_page(2)  # Settings
w.show_page(3)  # About
```

For settings, drive the real controls on the page object rather than poking the model directly:

```python
w.show_page(2)
w.settings.advanced_toggle.setChecked(True)
```

If an interaction is in a nested section or a dynamically shown widget, toggle the relevant UI element, then call `QApplication.processEvents()` or `QTimer.singleShot(...)` so the UI settles before asserting.

## Trigger the feature under test

Prefer the actual widget or signal path that users hit, not backend-only changes:

```python
w.dictate.mic.click()                  # click the mic button
w.dictate.copy_button.click()         # copy output
w.settings.keep_history_toggle.setChecked(True)
```

For quick behavioral assertions, interact with widgets and inspect their state or the text they expose:

```python
assert w.dictate.text.toPlainText() == "hello"
assert w.settings.advanced_toggle.isChecked()
```

Use `QSignalSpy` or direct widget state when the requirement is a state transition, setting persistence, or UI enabling/disabling; use a PNG only when the requirement is visual and broad enough to justify it.

## Helpful patterns

- For one page/state: keep the test focused on that page and only the widgets it touches.
- For dynamic UI: `QApplication.processEvents()` then assert the changed state.
- For animations or transitions: `QTimer.singleShot(250, ...)` or a tiny wait before asserting.
- For settings: patch temp settings/history files and restore them in `finally`.
- For app closing: call `SpeakApp.quit()` rather than `QApplication.quit()`, so the runtime servers clean up too.
- For tests that might start runtime servers or global hooks, follow the `speak-os-checks` / `speak-pipeline-checks` collision preflight before executing.

## Keep the scope honest

Do not default to a full screenshot sweep just because a file is under `speak/ui/`.

Use this skill when:
- you are checking a single screen or widget,
- you want to exercise a specific interaction,
- you need to assert the actual UI state or event path,
- you are verifying a behavior that is not broad visual coverage.

Use `speak-ui-screenshots` only when the task is visual: multiple states, layout/theme regression, overlay comparisons, or a multi-screen check.
