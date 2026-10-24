---
name: speak-os-checks
description: Test Speak's OS-level behaviour without a human - global hotkey hold/tap, key injection, paste + Enter into another window, single-instance locking, child-process cleanup, and the updater exe swap. Use when touching hotkey.py, output.py, platform_utils.py, ui/app.py single-instance code, runtimes.py, or updates.py.
---

# OS-level checks from scripts

Pattern: start a **separate process** as the "world" (a target window, a hook listener, a second instance), drive the code under test from another process, and print what the world observed. Run everything with `.\.venv\Scripts\python.exe` and `$env:PYTHONPATH=(Get-Location).Path`.

Before running, follow the process and instance collision preflight in `speak-verify`. These checks can register desktop-wide hooks, inject keys, paste into the focused app, or exercise single-instance forwarding. Use a test-owned target and isolated app data; do not interact with or close a pre-existing Speak instance. Only stop processes and release hooks started by the test.

## Hotkey hold / tap

Inject real key events and record callbacks (`hotkey.register(combo, on_press, on_release)`):

```powershell
@'
import time, keyboard
from speak import hotkey
ev = []
hotkey.register("ctrl+alt+f9", lambda: ev.append(("down", time.monotonic())), lambda: ev.append(("up", time.monotonic())))
time.sleep(0.3); t0 = time.monotonic()
keyboard.press("ctrl+alt+f9")
for _ in range(10): time.sleep(0.05); keyboard.press("f9")     # auto-repeat must not re-fire
keyboard.release("ctrl+alt+f9"); time.sleep(0.3)
keyboard.send("ctrl+alt+f9"); time.sleep(0.3)                    # tap
hotkey.unregister()
print([(k, round(t - t0, 2)) for k, t in ev])
'@ | Set-Content $env:TEMP\hk.py -Encoding utf8
.\.venv\Scripts\python.exe $env:TEMP\hk.py
```

`keyboard` is not an app dependency (the app uses `pynput`, needed for lone modifiers like right alt); `pip install keyboard` into the venv only if you need it for injection, or inject with `ctypes.windll.user32.keybd_event(vk, scan, flags, 0)` (right alt = vk `0xA5`, extended-key flag `1`, key-up flag `2`). Hooks can behave differently across processes: inject from a second process and verify the app process sees the events.

Pure parsing/matching logic goes in `tools/test_hotkey.py` with mocks.

## Paste (+ Enter) into another app

```powershell
@'
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QPlainTextEdit
app = QApplication([]); w = QPlainTextEdit(); w.resize(300, 200); w.show(); w.activateWindow(); w.raise_()
QTimer.singleShot(5000, lambda: (print(repr(w.toPlainText()), flush=True), app.quit()))
app.exec()
'@ | Set-Content $env:TEMP\target.py -Encoding utf8
@'
from speak import output, platform_utils
t = platform_utils.foreground_window()
print("entered1", output.paste("hello", lambda: platform_utils.foreground_window() == t))   # Enter sent
print("entered2", output.paste("world", lambda: False))                                    # focus changed: no Enter
'@ | Set-Content $env:TEMP\pt.py -Encoding utf8
$p = Start-Process .\.venv\Scripts\python.exe -ArgumentList "$env:TEMP\target.py" -NoNewWindow -PassThru -RedirectStandardOutput $env:TEMP\target.out
Start-Sleep 2; .\.venv\Scripts\python.exe $env:TEMP\pt.py; $p.WaitForExit(); Get-Content $env:TEMP\target.out
```

The target prints what it received; confirm the text arrived and the newline only when expected. Check the current `output.paste` signature first. Avoid leaving test text on the user's clipboard.

## Single instance / stale lock

Drive `speak.ui.app._single_instance(wait_ms)` with `config.APP_DIR` patched to a temp dir (so the real app isn't affected), using a tiny script per role that prints `owner / deferred / got show / exit`. Scenario: owner A runs 5 s; B launches (must print "deferred" and make A show); C with `--restarted` waits then takes over after A exits; a "crash" owner dies via `os._exit(1)` and the next instance must take over the stale lock. Compare printed timelines to the expected ones.

## Child processes must die with the app

The ASR and llama servers are tied to the app with a Windows job object (`platform_utils.tie_to_app`). Check by hard-killing the parent:

```powershell
$p = Start-Process "$env:TEMP\speak-dist\Speak.exe" -ArgumentList "--background" -PassThru; Start-Sleep 25
Get-Process Speak, llama-server, nemo-speech -ErrorAction SilentlyContinue | Select-Object Id, Name
Stop-Process -Id $p.Id; Start-Sleep 2
Get-Process llama-server, nemo-speech -ErrorAction SilentlyContinue | Select-Object Id, Name   # expect nothing
```

Parent/command line of a pid: `Get-CimInstance Win32_Process -Filter "ProcessId=<pid>" | Select ParentProcessId, CommandLine`.

## Updater swap (`updates.py`)

Test in a temp dir: `shutil.copy(sys.executable, exe)`, run that exe (`subprocess.Popen([exe, "-c", "import time; time.sleep(3)"])`) so it is locked, then `updates.install(new, exe)`: the running exe must be renamed to `.old` and the new file put in place. Also unit-test `updates.parse` / `pick` with fake release dicts (drafts, pre-releases, non-semver tags) and `config.load_settings` migrations (write a temp settings file, assert, restore in `finally`).

## Hygiene

Hooks and injected keys affect the whole desktop: keep injections short, always release keys in `finally`, and don't run these while the user is typing. Stop every process you started by id and confirm with `Get-Process`.
