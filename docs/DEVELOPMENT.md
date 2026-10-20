# Development

Speak is a Python (PySide6) desktop app that bundles two local inference runtimes:

- **NeMo-Speech.cpp** for streaming ASR with NVIDIA Nemotron 3.5 (`nvidia/nemotron-3.5-asr-streaming-0.6b`).
- **llama.cpp** (Vulkan build, which falls back to CPU) for the optional tidy-up pass with Qwen models.

Model weights download from Hugging Face on first use into `%LOCALAPPDATA%\Speak\models` (or the platform equivalent).

## Run from source

Requires Python 3.11+. Windows is the supported build today; macOS/Linux support is in progress.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\build.ps1            # fetches + verifies the pinned runtimes into vendor/, builds dist\Speak.exe
python main.py         # or run the built dist\Speak.exe
```

The exe icon is rendered from `app_icon()` by `tools/make_icon.py` during the build.

Use `./build.ps1 -OutputDirectory ./dist-next` to build beside an open app copy without replacing locked files.

Headless pipeline check (real ASR + tidy, no UI), printing the plan and timing for each tidy level:

```powershell
python -m tools.dictate_wav path\to\16bit-mono.wav --tidy fast,balanced,best [--cpu]
```

## Code map

| Path | What |
|---|---|
| `speak/controller.py` | Dictation state machine (idle → preparing → listening → processing), warm-up |
| `speak/tidy.py` | Picks tidy model + device from the level and free GPU/RAM; user-facing summary |
| `speak/cleanup.py` | Rules (spoken commands, fillers, pauses), LLM prompts, output validation |
| `speak/runtimes.py` | Starts/stops the bundled ASR and llama.cpp servers; model downloads |
| `speak/asr.py`, `speak/audio.py` | Streaming ASR session, microphone capture |
| `speak/hotkey.py` | Global shortcut (press/release for hold-to-talk), capture, key sending |
| `speak/updates.py` | Update check against `vX.Y.Z` release tags; download, sha256 check, exe swap |
| `speak/ui/` | Window, pages, overlay, widgets, theme |

## Tidy levels

| Level | What happens | Typical speed |
|---|---|---|
| Off | Spoken commands only ("new paragraph") | instant |
| Fast | Rules: drop fillers/stutters, pauses after sentences → paragraphs | instant |
| Balanced | Large model (Qwen3 4B) on a GPU with ≥4 GB free, else Small (Qwen 2.5 0.5B) on CPU | ~0.5 s |
| Best | Large model on GPU, or CPU if there's RAM | 0.5 s GPU, a few s CPU |

The Large model handles self-corrections ("three, no wait, four"); Small only punctuates (literal mode).
Model output is validated (length/similarity bounds, no invented numbers, no dropped words in literal mode); on failure the rule-processed text is used.
The llama.cpp server runs with `--parallel 1`, a pinned `--device` (integrated GPUs are skipped), and a warm-up request so the first dictation hits a warm prompt cache.
Advanced settings can pin the Small or Large model.

## Releases

- `.github/workflows/build.yml` builds `Speak.exe` on every push and pull request (downloadable artifact). These builds have no version and never update themselves.
- `.github/workflows/release.yml` is run by hand (Actions → Release → Run workflow) with a version like `1.2.0`. It writes `VERSION` to `speak/_build.py`, builds, and publishes release `v1.2.0` with `Speak.exe`. Tick *pre-release* to publish without offering it to installed apps.

Installed apps check the GitHub releases API at start and daily. Depending on the Updates setting they download the new `Speak.exe` beside the running one (verified against GitHub's sha256 digest) and swap it in on quit or via "Restart to update", or just show the button. Source runs and non-Windows builds open the release page instead.

## Privacy

Microphone audio is held in memory only and sent to the app-owned local runtime on loopback. History stores transcript text only, and only when enabled. Network use: model downloads (Hugging Face) and the update check/download (GitHub releases; can be turned off).
