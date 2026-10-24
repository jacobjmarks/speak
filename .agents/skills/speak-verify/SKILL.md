---
name: speak-verify
description: Start here for any change to Speak. Picks the cheapest check that proves a change works (lint, unit tests, UI screenshots, headless pipeline, OS-level tests, packaged exe) and the iterate loop to follow. Use before declaring any code change done.
---

# Verify every change

Never say "done" from reading code. Run something that exercises the change, look at the result, fix, repeat.

## Pick the cheapest check that covers the change

| You changed | Run | Skill |
|---|---|---|
| Any Python | `uvx ruff check --select F speak tools tests` | this file |
| Python behavior or pure logic | Add/update a regression test; run its focused module, e.g. `.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_tidy.py"`; use the full suite for cross-module or broad changes | this file |
| Focused UI behavior | Prefer a focused Qt test in `tests/ui/`; use `speak-ui-harness` when the real app interaction is not covered by the automated tests | `speak-ui-harness` |
| Broad visual changes (shared layout/theme, several pages/states, visual regression) | `.\.venv\Scripts\python.exe -m tools.screenshots`, then **view the PNGs** | `speak-ui-screenshots` |
| ASR, cleanup prompt, tidy models, runtimes | `.\.venv\Scripts\python.exe -m tools.dictate_wav ...` | `speak-pipeline-checks` |
| Hotkey, paste, single instance, process lifetime, updater swap | cross-process scripts | `speak-os-checks` |
| `build.ps1`, bundling, hooks, notices, icon | build to a temp dir, inspect the exe | `speak-build-exe` |

## The loop

1. Find or add the smallest regression test in `tests/` that captures the behavior. Use a scratch script for diagnosis only when the suite cannot express the check.
2. Edit the code.
3. Re-run the focused test. Read the actual output (or view the screenshot). Don't assume.
4. Run lint for Python changes. Run the full suite for cross-module, broad, or high-risk changes; CI runs the full unittest suite with coverage and lint.
5. Clean up (see below).

## Choose the scope

Use the full screenshot sweep for broad visual changes or when several states need comparison. A `ui/*` path alone is not a reason to render every screen. For one control or interaction, drive the app via `speak-ui-harness`, assert the widget state or clicked behavior directly, and capture only its affected state when visual output matters. For nonvisual behavior, prefer a focused unit or Qt test.

## Check for collisions first

Before any check that can launch Speak or a runtime, register a global hook, or interact with the desktop, inventory existing `Speak`, `llama-server`, and `nemo-speech` processes. There may be none, or there may be one or more user-owned or test-owned processes. Inspect each PID's parent and command line to determine ownership; the app's single-instance startup can forward to an existing window, runtime servers can occupy the test ports, and hooks or paste tests affect the shared desktop.

Isolate test settings, history, app data, and ports where the test supports it. If an existing process could collide and the test cannot be isolated, stop and ask before proceeding. Leave pre-existing or unidentified processes alone; clean up only PIDs the test itself started.

## Rules that make this fast and safe

- Always use `.\.venv\Scripts\python.exe` (never system Python) for Python commands. Set `$env:PYTHONPATH=(Get-Location).Path` for scratch scripts outside the repo, and `$env:PYTHONIOENCODING="utf-8"` when output has non-ASCII.
- Put scratch scripts in `$env:TEMP`, never the repo. Write them with a PowerShell here-string: `@' ... '@ | Set-Content $env:TEMP\x.py -Encoding utf8`.
- Real user data lives in `%LOCALAPPDATA%\Speak` (`settings.json`, history, models, logs). Tests must not change it: patch `config.SETTINGS_FILE`/`HISTORY_FILE` to a temp dir (as `tools/screenshots.py` does) or back it up and restore it in `finally`.
- Models are large and already cached in `config.MODELS_DIR`; don't delete them. A first run of a new model downloads it (can take minutes): use `initial_wait` of 240+ s.
- Qt: an exception in a timer/slot callback does not exit the app; the event loop just hangs. Wrap steps in try/except and `qa.exit(1)`. Always give long-running scripts a timeout or a `QTimer.singleShot(..., quit)`.
- Quit the UI with `SpeakApp.quit()`, not `QApplication.quit()`, or runtime servers stay running.
- After a run, compare the process inventory with the preflight. Stop only test-owned leftovers by PID, then confirm they exited.
- Don't leave `.ruff_cache`, `__pycache__`, `dist-*`, or temp exes in the repo.
- Update `AGENTS.md` / `docs/DEVELOPMENT.md` when you change what they describe. Commit messages reference issues with `Closes #N`.
