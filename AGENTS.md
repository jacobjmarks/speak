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
| `ui/app.py` | PySide6 `SpeakApp`: tray, hotkey wiring, close behaviour, update flow, dictation → window/overlay, `main()` |
| `ui/bridge.py` | `Bridge`: `Listener` callbacks (worker threads) re-emitted as Qt signals on the UI thread; coalesces live text |
| `ui/single_instance.py` | `claim(wait_ms)`: `QLockFile` + `QLocalServer` so a second launch shows the running window and exits |
| `ui/window.py` | `MainWindow` (sidebar + pages), `app_icon()`, first-close `CloseDialog` |
| `ui/banner.py` | `Banner`: keyed in-window notices (errors, permission warnings, updates); use `window.notify(key, text, level, action)`. User-facing text must be plain language |
| `ui/pages/dictate.py` | `DictatePage`: mic button, wave, live/final transcript, Copy |
| `ui/pages/history.py` | `HistoryPage`: opt-in transcript list, click to copy, clear all |
| `ui/pages/settings.py` | `SettingsPage`: basic card + collapsible Advanced; every control emits `changed` with a partial settings dict |
| `ui/pages/about.py` | `AboutPage`: version, sponsor links, licence/notices |
| `ui/pages/setup.py` | `SetupPage`: macOS first-run permissions, shown until all are granted |
| `ui/controls.py` | Shared page building blocks: `Page`, `make_card`/`make_label`/`make_combo`, `SettingRow`, `MicCombo`, `LanguageItemDelegate` |
| `ui/onboarding/` | `OnboardingPage`: animated 8-step first-run flow (welcome, theme, mic check + retry, shortcut/mode/dimming, tidy level + model + speed test, overlay preview via real `Overlay.snapshot`, updates + pre-releases, done); changes apply live; changing tidy options cancels the running test (`Dictation.cancel_benchmark`) and re-tests; rerun from Settings |
| `benchmark.py` | `run(...)`: times a recording through ASR + tidy; `Result.verdict` plain-language rating |
| `ui/overlay.py` | Floating pill: waveform / phase word / check; position (cursor/top/bottom); live text (line/full/off) |
| `ui/widgets.py` | Painted widgets: `MicButton`, `WaveStrip`, `Spinner`, `Toggle`, `ShortcutButton`; base class `Animated` |
| `ui/paint.py` | Drawing helpers shared by widgets, overlay and onboarding: glyphs (`draw_mic/check/cross/ring`), `draw_wave`, `draw_shimmer_text`, `BARS` |
| `ui/theme.py` | Light/dark palettes + the app style sheet (all colours live here) |

Entry point: `main.py` (repo root) or `python -m speak`; both call `speak.ui.app.main()`. `--background` starts hidden in the tray.

## Where do I change…

| Task | File |
|---|---|
| Add or rename a setting | `config.DEFAULTS` + `ui/pages/settings.py` `SettingsPage` (basic = user-level only; technical → Advanced) |
| Cleanup prompt / behaviour | `cleanup.py` |
| Which tidy model/device, speed presets | `tidy.py` (benchmarks in its docstring) |
| Runtime CLI flags, ports, readiness | `runtimes.py` |
| What happens on hotkey press / after recognition | `controller.py` |
| Windows/macOS/Linux difference | `platform_utils.py` (never inline `sys.platform` checks elsewhere) |
| Overlay look / states | `ui/overlay.py` |
| Colours, fonts, rounding | `ui/theme.py` |
| Tray, close-to-tray, hotkey `shortcut_mode` auto/hold/toggle (`HOLD_SECONDS`) + capture guard, overlay-on-focus rule, update flow | `ui/app.py` |
| Single instance (`claim`, lock + local server; `--restarted` waits) | `ui/single_instance.py` |
| Lint rules, pytest path, dev tools | `pyproject.toml`, `requirements-dev.txt` |
| CI test workflow (PRs and `main`) | `.github/workflows/ci.yml`, shared steps in `.github/actions/python-ci-checks/action.yml` |
| Idle unload of runtimes (`unload_after`, `_schedule_unload`), preload (`warm_up`) | `controller.py` |
| Enter before/after paste (only if `platform_utils.foreground_window()` unchanged since start) | `controller.py`, `output.py` |
| Exe icon | `tools/make_icon.py` (called by `build.ps1`) |
| Third-party licence notices bundled in the exe | `tools/make_notices.py` (called by `build.ps1`); new pip deps are picked up from `requirements.txt`, anything bundled another way needs a section |
| What PyInstaller bundles for sounddevice | `tools/hooks/hook-sounddevice.py` |
| Donation / repo URLs | `config.py` (`SPONSOR_URL`, `COFFEE_URL`, `REPO_URL`), `.github/FUNDING.yml`, README |
| CI build, manual release (semver input, Latest choice, issue comments) | `.github/workflows/build.yml`, `release.yml`; see `docs/releases-and-updates.md` |

## Rules

- Core modules (everything outside `ui/`) must not import a UI toolkit.
- Import public names across modules. Don't import `_private` helpers from another module; promote them instead (e.g. `ui/controls.py`).
- New main-window page: its own module in `ui/pages/`. Reusable form/page pieces go in `ui/controls.py`; drawing helpers in `ui/paint.py`.
- `Listener` callbacks run on worker threads; the UI marshals them to its main thread.
- Qt 6 `app.quit()` sends close events to windows; set `window.allow_close` first (see `SpeakApp.quit`).
- Keep inference local. Weights download on first use into `config.MODELS_DIR`; never bundle them.
- Never write the version into source; the Release workflow stamps `speak/_build.py`.
- Bundled LGPL components (Qt/PySide6, pynput) must stay separate libraries; the source stays public so users can rebuild.
- Reference issues with `Closes #N` in commit messages; the release lists and comments on them.

## Run / test

Windows (macOS: use `.venv/bin/python` and `pwsh -File ./build.ps1` as is). Create the venv once with `py -3 -m venv .venv` and `.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`.

```powershell
pwsh -File ./build.ps1            # native package for Windows x64 or macOS arm64/x64
.\.venv\Scripts\python.exe main.py
# Lint (pyflakes rules, configured in pyproject.toml) and automated tests (no model downloads or hardware required):
.\.venv\Scripts\python.exe -m ruff check
.\.venv\Scripts\python.exe -m pytest -n auto --cov=speak
# Headless pipeline check (ASR + each tidy level) on a 16-bit mono WAV:
.\.venv\Scripts\python.exe -m tools.dictate_wav sample.wav --tidy fast,auto,best
```

Each test class documents its behavioral contract in a docstring; test names describe observable outcomes. Prefer
end-to-end logic flows with external services and OS APIs mocked at their boundaries over line-coverage-only tests.
Qt interaction tests use `QTest` on the platform-native Qt plugin; its system font fallback is needed for readable
screenshots. Set `SPEAK_UI_SNAPSHOT_DIR` to save screenshots of asserted UI states.

Verification skills (read `speak-verify` first) live in `.agents/skills/`: `speak-verify`, `speak-ui-harness` (for focused app-driving, page navigation, and specific UI interactions), `speak-ui-screenshots` (`python -m tools.screenshots` for broad visual checks), `speak-marketing-images` (`python -m tools.marketing_images`), `speak-pipeline-checks`, `speak-os-checks`, `speak-build-exe`. Choose focused tests for focused UI behavior; check existing Speak/runtime processes before checks that can launch or interact with them, and leave pre-existing processes alone. Always run a check and look at its output before calling a change done.

## Test map

Patch the module that owns a name (`speak.audio.input_devices`, `speak.history.recent`), not a module that merely imports it.

| Module | Tests |
|---|---|
| Core `speak/<m>.py` (one file each) | `tests/test_<m>.py`: `controller`, `benchmark`, `tidy`, `cleanup`, `asr`, `runtimes`, `config`, `history`, `hotkey`, `updates`, `system_audio`, `platform_utils`, `audio`, `output`, `permissions` |
| Dimming during dictation | also `tests/test_controller.py` and `tests/test_system_audio.py` |
| Benchmark cancel | `tests/test_controller_benchmark.py` |
| `tools/make_notices.py` | `tests/test_make_notices.py` |
| `ui/window.py`, `ui/banner.py`, `ui/overlay.py`, `ui/bridge.py`, `ui/controls.py` | `tests/ui/test_window.py`, `test_banner.py`, `test_overlay.py`, `test_bridge.py`, `test_controls.py` |
| `ui/pages/<p>.py` | `tests/ui/pages/test_<p>.py`: `dictate`, `settings`, `history`, `setup` |
| `ui/app.py` (app wiring, updates, GPU preference, first run) | `tests/ui/test_app_first_run.py`, `test_app_updates.py`, `test_app_device.py` |
| `ui/onboarding/<s>.py` | `tests/ui/onboarding/test_<s>.py`: `page`, `navigation`, `mic_keys`, `tidy` (incl. speed test), `animated`, `stages`, `widgets` |
| Shared fixtures | `tests/ui/__init__.py` (`QtTestCase`), `tests/ui/onboarding/support.py` (`OnboardingCase`, `dark_variant`) |

Rule: a test for `speak/a/b.py` goes in `tests/a/test_b.py`, or `tests/test_b.py` for top-level `speak/` modules. Keep one test file per source module; `ui/app.py` is the exception, split by flow.

More detail: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) (index), [runtimes-and-tidy.md](docs/runtimes-and-tidy.md), [releases-and-updates.md](docs/releases-and-updates.md), [licensing-and-privacy.md](docs/licensing-and-privacy.md).
