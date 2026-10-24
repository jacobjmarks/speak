---
name: speak-verify
description: Start here for any change to Speak. Picks the cheapest check that proves a change works (lint, unit tests, UI screenshots, headless pipeline, OS-level tests, packaged exe) and the iterate loop to follow. Use before declaring any code change done.
---

# Verify every change

Never say "done" from reading code. Run something that exercises the change, look at the result, fix, repeat.

## Pick the cheapest check that covers the change

| You changed | Run | Skill |
|---|---|---|
| Any Python | `uvx ruff check --select F speak tools` | this file |
| Pure logic (`tidy`, `cleanup`, `config`, `updates`, `hotkey` parsing, controller states) | `.\.venv\Scripts\python.exe -m unittest discover -s tools -p "test_*.py"` then a throwaway script for new logic | this file |
| Broad visual changes (shared layout/theme, several pages/states, visual regression) | `python -m tools.screenshots`, then **view the PNGs** | `speak-ui-screenshots` |
| Focused UI behavior or one-widget change | Use the real app flow to navigate and click the target control; assert widget state/signal output; capture only the affected state if appearance is part of the requirement | `speak-ui-harness` |
| ASR, cleanup prompt, tidy models, runtimes | `python -m tools.dictate_wav ...` | `speak-pipeline-checks` |
| Hotkey, paste, single instance, process lifetime, updater swap | cross-process scripts | `speak-os-checks` |
| `build.ps1`, bundling, hooks, notices, icon | build to a temp dir, inspect the exe | `speak-build-exe` |

## The loop

1. Write the smallest script/test that fails or shows the current behaviour.
2. Edit the code.
3. Re-run the same check. Read the actual output (or view the screenshot). Don't assume.
4. Run lint and the unit tests.
5. Clean up (see below), then commit.

## Choose the scope

Use the full screenshot sweep for broad visual changes or when several states need comparison. A `ui/*` path alone is not a reason to render every screen. For one control or interaction, drive the app via `speak-ui-harness`, assert the widget state or clicked behavior directly, and capture only its affected state when visual output matters. For nonvisual behavior, prefer a focused unit or Qt test.

## Check for collisions first

Before any check that can launch Speak or a runtime, register a global hook, or interact with the desktop, inventory existing `Speak`, `llama-server`, and `nemo-speech` processes. There may be none, or there may be one or more user-owned or test-owned processes. Inspect each PID's parent and command line to determine ownership; the app's single-instance startup can forward to an existing window, runtime servers can occupy the test ports, and hooks or paste tests affect the shared desktop.

Isolate test settings, history, app data, and ports where the test supports it. If an existing process could collide and the test cannot be isolated, stop and ask before proceeding. Leave pre-existing or unidentified processes alone; clean up only PIDs the test itself started.

## Rules that make this fast and safe

- Always use `.\.venv\Scripts\python.exe` (never system Python). Set `$env:PYTHONPATH=(Get-Location).Path` for scratch scripts outside the repo, and `$env:PYTHONIOENCODING="utf-8"` when output has non-ASCII.
- Put scratch scripts in `$env:TEMP`, never the repo. Write them with a PowerShell here-string: `@' ... '@ | Set-Content $env:TEMP\x.py -Encoding utf8`.
- Real user data lives in `%LOCALAPPDATA%\Speak` (`settings.json`, history, models, logs). Tests must not change it: patch `config.SETTINGS_FILE`/`HISTORY_FILE` to a temp dir (as `tools/screenshots.py` does) or back it up and restore it in `finally`.
- Models are large and already cached in `config.MODELS_DIR`; don't delete them. A first run of a new model downloads it (can take minutes): use `initial_wait` of 240+ s.
- Qt: an exception in a timer/slot callback does not exit the app; the event loop just hangs. Wrap steps in try/except and `qa.exit(1)`. Always give long-running scripts a timeout or a `QTimer.singleShot(..., quit)`.
- Quit the UI with `SpeakApp.quit()`, not `QApplication.quit()`, or runtime servers stay running.
- After a run, compare the process inventory with the preflight. Stop only test-owned leftovers by PID, then confirm they exited.
- Don't leave `.ruff_cache`, `__pycache__`, `dist-*`, or temp exes in the repo.
- Update `AGENTS.md` / `docs/DEVELOPMENT.md` when you change what they describe. Commit messages reference issues with `Closes #N`.
