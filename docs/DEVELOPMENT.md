# Development

Speak is a Python (PySide6) desktop app that bundles two local inference runtimes:

- **NeMo-Speech.cpp** for streaming ASR with NVIDIA Nemotron 3.5 (`nvidia/nemotron-3.5-asr-streaming-0.6b`).
- **llama.cpp** (Vulkan build, which falls back to CPU) for the optional tidy-up pass with Qwen models.

Model weights download from Hugging Face on first use into the OS-specific Speak data directory.

| Doc | Covers |
|---|---|
| [AGENTS.md](../AGENTS.md) | Module map, where to change what, test map, rules (start here for code changes) |
| [runtimes-and-tidy.md](runtimes-and-tidy.md) | Tidy levels, bundled runtimes, idle unload, single instance |
| [releases-and-updates.md](releases-and-updates.md) | Build and release workflows, CI, in-app updater |
| [licensing-and-privacy.md](licensing-and-privacy.md) | Third-party notices, LGPL rules, privacy and network use |
| [MODEL-VALUE-INVESTIGATION.md](MODEL-VALUE-INVESTIGATION.md) | Research: is the Large tidy-up model worth its size |

## Run from source

Requires Python 3.11+ and PowerShell Core (`pwsh`). CI releases Windows x64 and macOS arm64 packages. Running the script on an Intel Mac builds the macOS x64 package locally.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
pwsh -File ./build.ps1   # fetches + verifies pinned runtimes and builds the host OS package
python main.py           # or launch the package under dist/
```

The Windows exe icon is rendered from `app_icon()` by `tools/make_icon.py` during the build.

Use `pwsh -File ./build.ps1 -OutputDirectory ./dist-next` to build beside an open app copy without replacing locked files.

On macOS, create and activate `.venv` with `python3 -m venv .venv && source .venv/bin/activate` first, then run the same `pwsh` command:

```powershell
pwsh -File ./build.ps1
```

macOS emits a `.app` plus a zip archive and declares microphone access, but builds are unsigned; Gatekeeper requires manually approving the app. Linux is not supported yet.

Headless pipeline check (real ASR + tidy, no UI), printing the plan and timing for each tidy level:

```powershell
python -m tools.dictate_wav path\to\16bit-mono.wav --tidy fast,auto,best [--cpu]
```

## Automated tests

Install the dev tools once, then run lint and the hardware- and network-independent suite:

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check
python -m pytest -n auto --cov=speak
```

Lint rules and the pytest path live in `pyproject.toml`. The suite lives in `tests/`; `tests/ui/` holds Qt interaction
tests (`PySide6.QtTest.QTest`) grouped by UI area. Tests mock OS APIs, devices, clipboard, subprocesses and HTTP, so they
need no microphone, models or network, and never use the running executable. Each test file's docstrings state the
behaviour under test; [AGENTS.md](../AGENTS.md) has the file-to-area map.
Qt interaction tests run on the platform-native Qt plugin. To save screenshots of the tested states locally:

```powershell
$env:SPEAK_UI_SNAPSHOT_DIR = Join-Path $env:TEMP 'Speak-UI'
.\.venv\Scripts\python.exe -m pytest -n auto --cov=speak
```

CI uses each runner's native Qt platform and uploads these screenshots as a per-OS `ui-screenshots` artifact. The
offscreen Qt plugin has no font database on our Windows setup, so it produces misleading missing-glyph images; it is
intentionally not used. Tests exercise dictation controls, settings persistence/dependent controls, saved-history
actions, permission setup, navigation, notices, and first-close choices.
Update interaction tests cover available/up-to-date notifications, retry after download failure, immediately canceling
active dictation when applying an update, and installing a staged update with temporary files. Network access and the
running executable are never used.
CI runs lint and tests through the shared action (`.github/actions/python-ci-checks/action.yml`): `ci.yml` on pull requests and pushes to `main`, and `build.yml` and `release.yml` before packaging, on Windows and macOS. The step writes a coverage
table into the GitHub job summary for each matrix run. `coverage.xml` artifact upload is optional (off by default).
It does not download models or require a microphone.
Real hotkey/paste injection, packaged-app behavior, and inference pipelines remain separate manual or
hardware-dependent checks; see the verification skills in `AGENTS.md`.

Regenerate README product images from the real UI (no microphone or models required):

```powershell
python -m tools.marketing_images [output_dir]
```

See `.agents/skills/speak-marketing-images/SKILL.md` for the capture/composition workflow and review checklist.

## Code map

Module ownership and where to change things: the module index in [AGENTS.md](../AGENTS.md).
