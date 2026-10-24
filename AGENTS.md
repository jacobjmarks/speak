# AGENTS.md

Speak is a local desktop dictation app. A global hotkey (hold or tap) records the mic. Audio streams to a bundled NeMo-Speech.cpp ASR server. The final text can be cleaned by a bundled llama.cpp server, then it is pasted into the focused app.

## Module index (`speak/`)

| Module | Owns |
|---|---|
| `config.py` | App paths, `DEFAULTS` settings, model catalogs (`ASR_MODELS`, `CLEANUP_MODELS`), option labels, `load_settings`/`save_settings` |
| `permissions.py` | macOS privacy permissions (Microphone, Input Monitoring, Accessibility): check, request, open Settings |
| `platform_utils.py` | OS branching: app data dir, exe suffix, bundle root, hidden-subprocess flags, paste shortcut, open folder, launch at login |
| `runtimes.py` | `ManagedServer` subprocess lifecycle; `AsrServer`, `CleanupServer`; cleanup model download |
| `asr.py` | `AsrSession`: realtime websocket (send PCM, receive deltas/finals) |
| `audio.py` | `Microphone(device_name)`, `input_devices()`: sounddevice capture + RMS level |
| `system_audio.py` | System output volume dimming and safe restore (Windows/macOS) |
| `tidy.py` | Hardware probe (`llama-server --list-devices`) + `plan(settings)`: tidy level → model, device, llm mode, user-facing summary |
| `cleanup.py` | `finalize(raw, level, llm_mode, port)`: regex rules (spoken punctuation, fillers, pauses) → LLM cleanup → `validate()` guardrails; `warm()` primes the prompt cache |
| `controller.py` | `Dictation` state machine (`State`: idle → preparing → listening → processing) and the `Listener` callbacks the UI implements |
| `history.py` | Opt-in SQLite transcript history |
| `output.py` | Clipboard copy, paste-into-focused-app |
| `hotkey.py` | Global hotkey `register(combo, on_press, on_release)` (hold-to-talk), capture, send, display (pynput on Windows/Linux, `keytap_mac.py` Quartz tap on macOS; lone modifiers like `right alt` supported) |
| `updates.py` | Updates: release-stamped `_build.VERSION` vs `v<semver>` tags (pre-release installs also take pre-releases); download + sha256 + exe swap (Windows frozen only) |
| `ui/app.py` | PySide6 `SpeakApp`: `Bridge` (Listener → Qt signals), tray, hotkey, close behaviour, `main()` |
| `ui/window.py` | `MainWindow` (sidebar + pages), `app_icon()`, first-close `CloseDialog` |
| `ui/banner.py` | `Banner`: keyed in-window notices (errors, permission warnings, updates); use `window.notify(key, text, level, action)`. User-facing text must be plain language |
| `ui/pages.py` | `DictatePage`, `HistoryPage`, `SettingsPage` (basic card + collapsible Advanced), `AboutPage` (version, sponsor links, licence/notices), `SetupPage` (macOS first-run permissions) |
| `ui/overlay.py` | Floating pill: waveform / phase word / check; position (cursor/top/bottom); live text (line/full/off) |
| `ui/widgets.py` | Painted widgets: `MicButton`, `WaveStrip`, `Spinner`, `Toggle`, `ShortcutButton`; `draw_wave`/`draw_shimmer_text` shared with the overlay; glyph helpers |
| `ui/theme.py` | Light/dark palettes + the app style sheet (all colours live here) |

Entry point: `main.py` (repo root) or `python -m speak`; both call `speak.ui.app.main()`. `--background` starts hidden in the tray.

## Where do I change…

| Task | File |
|---|---|
| Add or rename a setting | `config.DEFAULTS` + `ui/pages.py` `SettingsPage` (basic = user-level only; technical → Advanced) |
| Cleanup prompt / behaviour | `cleanup.py` |
| Which tidy model/device, speed presets | `tidy.py` (benchmarks in its docstring) |
| Runtime CLI flags, ports, readiness | `runtimes.py` |
| What happens on hotkey press / after recognition | `controller.py` |
| Windows/macOS/Linux difference | `platform_utils.py` (never inline `sys.platform` checks elsewhere) |
| Overlay look / states | `ui/overlay.py` |
| Colours, fonts, rounding | `ui/theme.py` |
| Tray, close-to-tray, hotkey `shortcut_mode` auto/hold/toggle (`HOLD_SECONDS`) + capture guard, overlay-on-focus rule, update flow | `ui/app.py` |
| Single instance (`_single_instance`, lock + local server; `--restarted` waits) | `ui/app.py` |
| Idle unload of runtimes (`unload_after`, `_schedule_unload`), preload (`warm_up`) | `controller.py` |
| Enter after paste (only if `platform_utils.foreground_window()` unchanged since start) | `controller.py`, `output.py` |
| Exe icon | `tools/make_icon.py` (called by `build.ps1`) |
| Third-party licence notices bundled in the exe | `tools/make_notices.py` (called by `build.ps1`); new pip deps are picked up from `requirements.txt`, anything bundled another way needs a section |
| What PyInstaller bundles for sounddevice | `tools/hooks/hook-sounddevice.py` |
| Donation / repo URLs | `config.py` (`SPONSOR_URL`, `COFFEE_URL`, `REPO_URL`), `.github/FUNDING.yml`, README |
| CI build, manual release (semver input, Latest choice, issue comments) | `.github/workflows/build.yml`, `release.yml`; see `docs/DEVELOPMENT.md` |

## Rules

- Core modules (everything outside `ui/`) must not import a UI toolkit.
- `Listener` callbacks run on worker threads; the UI marshals them to its main thread.
- Qt 6 `app.quit()` sends close events to windows; set `window.allow_close` first (see `SpeakApp.quit`).
- Keep inference local. Weights download on first use into `config.MODELS_DIR`; never bundle them.
- Never write the version into source; the Release workflow stamps `speak/_build.py`.
- Bundled LGPL components (Qt/PySide6, pynput) must stay separate libraries; the source stays public so users can rebuild.
- Reference issues with `Closes #N` in commit messages; the release lists and comments on them.

## Run / test

```powershell
pwsh -File ./build.ps1            # native package for Windows x64 or macOS arm64/x64
.\.venv\Scripts\python.exe main.py
# Headless pipeline check (ASR + each tidy level) on a 16-bit mono WAV:
.\.venv\Scripts\python.exe -m tools.dictate_wav sample.wav --tidy fast,auto,best
uvx ruff check --select F speak tools   # lint
```

Verification skills (read `speak-verify` first) live in `.agents/skills/`: `speak-verify`, `speak-ui-screenshots` (`python -m tools.screenshots`), `speak-pipeline-checks`, `speak-os-checks`, `speak-build-exe`. Always run a check and look at its output before calling a change done.

More detail (tidy levels, idle unload, single instance, releases, licensing): `docs/DEVELOPMENT.md`.
