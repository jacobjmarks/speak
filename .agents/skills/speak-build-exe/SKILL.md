---
name: speak-build-exe
description: Build and smoke-test the packaged Speak exe without touching the user's running copy, inspect bundle contents, and read logs. Use when touching build.ps1, requirements, tools/hooks, tools/make_notices.py, the icon, bundled licences, or when a bug only reproduces in the frozen app.
---

# Build and smoke-test the package

Build to a temp dir so a running/locked `dist\Speak.exe` is never replaced:

```powershell
pwsh -File ./build.ps1 -OutputDirectory "$env:TEMP\speak-dist" *>&1 | Select-Object -Last 15   # minutes; initial_wait 300+
```

`build.ps1` fetches and verifies pinned runtimes into `vendor/` (gitignored), generates the icon and `THIRD_PARTY_NOTICES.txt`, then runs PyInstaller. It needs the repo `.venv` with pip; if it errors with "No module named pip" the venv is broken: recreate it (`py -3 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt`).

## Inspect what got bundled

```powershell
& .\.venv\Scripts\pyi-archive_viewer.exe --list "$env:TEMP\speak-dist\Speak.exe" 2>&1 | Select-String "portaudio|THIRD_PARTY|nemo|llama" | % Line
"{0:N1} MB" -f ((Get-Item "$env:TEMP\speak-dist\Speak.exe").Length/1MB)
```

Missing data files (PortAudio DLL, notices, icon) are the usual frozen-only bug: fix via `tools/hooks/` or `build.ps1`, then re-list. Resource lookups go through `platform_utils.bundle_root()` / `notices_file()`; check them against the source tree too.

## Smoke test the exe

```powershell
$p = Start-Process "$env:TEMP\speak-dist\Speak.exe" -ArgumentList "--background" -PassThru; Start-Sleep 25
"alive: " + (-not $p.HasExited)
Get-Process llama-server, nemo-speech -ErrorAction SilentlyContinue | Select Id, Name, @{n="MB";e={[int]($_.WorkingSet64/1MB)}}
Get-ChildItem "$env:LOCALAPPDATA\Speak" -Recurse -Filter *.log | Select FullName, LastWriteTime
Stop-Process -Id $p.Id; Start-Sleep 3
Get-Process llama-server, nemo-speech -ErrorAction SilentlyContinue   # expect none
```

Interact with the frozen app using the techniques in `speak-ui-screenshots` and `speak-os-checks` (hold right alt via `keybd_event`, wait ~1 s, grab the screen, crop around the cursor, view the PNG). Only one instance runs per user: if the user's real Speak is open, the smoke test just signals it, so ask before closing it. Remove `$env:TEMP\speak-dist` when done.

## Release / CI

Workflows live in `.github/workflows/` (`build.yml`, `release.yml`). Validate YAML edits by parsing them and by simulating shell/regex logic locally. Never write the version into source: the Release workflow stamps `speak/_build.py`. Details: `docs/DEVELOPMENT.md`.
