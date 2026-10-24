# Development

Speak is a Python (PySide6) desktop app that bundles two local inference runtimes:

- **NeMo-Speech.cpp** for streaming ASR with NVIDIA Nemotron 3.5 (`nvidia/nemotron-3.5-asr-streaming-0.6b`).
- **llama.cpp** (Vulkan build, which falls back to CPU) for the optional tidy-up pass with Qwen models.

Model weights download from Hugging Face on first use into the OS-specific Speak data directory.

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

## Code map

| Path | What |
|---|---|
| `speak/controller.py` | Dictation state machine (idle → preparing → listening → processing), warm-up |
| `speak/tidy.py` | Picks tidy model + device from the level and free GPU/RAM; user-facing summary |
| `speak/cleanup.py` | Rules (spoken commands, fillers, pauses), LLM prompts, output validation |
| `speak/runtimes.py` | Starts/stops the bundled ASR and llama.cpp servers; model downloads |
| `speak/asr.py`, `speak/audio.py` | Streaming ASR session, microphone capture |
| `speak/hotkey.py` | Global shortcut (press/release for hold-to-talk), capture, key sending |
| `speak/updates.py` | Update check against `v<semver>` release tags; download, sha256 check, exe swap |
| `speak/ui/` | Window, pages, overlay, widgets, theme |

## Tidy levels

| Level | What happens | Typical speed |
|---|---|---|
| Off | Spoken commands only ("new paragraph") | instant |
| Fast | Rules: drop fillers/stutters, pauses after sentences → paragraphs | instant |
| Automatic | Large model (Qwen3 4B) on a GPU with ≥6 GB free, else Small (Qwen 2.5 0.5B) on CPU | ~0.5 s |
| Best | Large model on GPU, or CPU if there's RAM | 0.5 s GPU, a few s CPU |

The Large model handles self-corrections ("three, no wait, four"); Small only punctuates (literal mode). The *Fix changes of mind* setting (`corrections`) runs Large in literal mode when off. A correction *reach* ("only the last sentence") was tried via prompting; Qwen3 4B ignored it, so it's on/off only.

Single instance: `QLockFile` (`speak.lock` in the data folder; a dead owner's lock is taken over) plus a `QLocalServer` so a second launch shows the running window and exits. Two instances would each hear the shortcut and paste twice. An update relaunch passes `--restarted` and waits up to 15 s for the old lock.

Both runtimes unload after `unload_after` idle minutes (default 5; Advanced → *Free up memory when idle*): speech ~1 GB RAM, large tidy ~3 GB VRAM. Reload costs ~2-4 s on the next dictation. Launch preloads them unless started at login (background) or set to unload right away.

ASR runs with `--asr.streaming.rnnt_right_context=-1` (max lookahead, ~0.25 s): better words and punctuation on clean speech, same finish time, live text every 320 ms. A full offline re-pass (`POST /v1/audio/transcriptions`) was tested: ~1.6 s per 20 s of audio and worse on noisy audio, so not used. Context-dependent word fixes ("pair" → "pear") are left to the tidy model.
Model output is validated (length/similarity bounds, no invented numbers, no dropped words in literal mode); on failure the rule-processed text is used.
The llama.cpp server runs with `--parallel 1`, a pinned `--device` (integrated GPUs are skipped), and a warm-up request so the first dictation hits a warm prompt cache.
Advanced settings can pin the Small or Large model, and choose tidy-up hardware: Automatic, Processor only, or Graphics card only. If Graphics card is forced but unavailable/too full, cleanup falls back to CPU and the tidy summary explains why.

## Releases

- `.github/workflows/build.yml` is run by hand (Actions → Build → Run workflow), never automatically on pushes or pull requests. Choose *platform*: `all` (default) builds Windows x64 and macOS arm64 artifacts; `windows` or `macos` builds only that OS. Use GitHub's branch selector to choose which branch to build. These builds are stamped `dev-<short commit>` (shown as "Development build <commit>", and in the package name); that is not a semver, so they never check for or offer updates.
- `.github/workflows/release.yml` is run by hand (Actions → Release → Run workflow) with a semver version like `1.0.0-alpha.1`, `1.0.0-rc.1` or `1.0.0`. Choose *platform*: `all` (default) builds Windows x64 and macOS arm64 packages; `windows` or `macos` builds only that OS. It publishes release `v<version>` with only the selected packages and matching release notes. A `-suffix` marks it a GitHub pre-release: stable installs never get offered it unless they turn on *Pre-release versions* in Settings, pre-release installs update to newer pre-releases and stable versions by semver order (`alpha.1` < `rc.1` < `1.0.0`). *Latest* (`auto` by default) is only set for a stable version higher than every existing stable release, so a hotfix for an older line (e.g. `1.1.1` built from `ref: v1.1.0` after `1.2.0`) stays out of the way; choose `yes`/`no` to override. The in-app updater ignores the Latest flag and always picks the highest eligible version. Optional *ref* (commit SHA, branch or tag; default `main`) releases an earlier commit. It refuses a version whose tag exists (including OS-specific releases; another OS needs a new version), lists issues closed since the previous tag (`Closes #N` in commit messages) in the notes, and comments the release on each. The version only comes from this input, never from source.

Installed apps check the GitHub releases API at start and daily. Each OS only considers releases that carry its own package (`Speak-<version>-windows-x64.exe` on Windows, `Speak-<version>-macos-arm64.zip` / `-macos-x64.zip` on macOS); a release without it is not an update for that OS. Depending on the Updates setting they download the new package's `.exe` beside the running one (verified against GitHub's sha256 digest) and swap it in on quit or via "Restart to update", or just show the button. Source runs and non-Windows builds open the release page instead.

## Licensing

The build runs `tools/make_notices.py`, which writes `build/THIRD_PARTY_NOTICES.txt` (Python, every runtime pip dependency's licence files, PySide6/Qt LGPL-3, PortAudio, PyInstaller bootloader, NeMo-Speech.cpp and llama.cpp licences, model attributions, LGPL-3/GPL-3 texts from `licenses/`) and bundles it; The About page's *Open-source notices* link opens it, or this section when no bundled notices are available. No root `LICENSE` file is required. Add new dependencies to `requirements.txt` and they're picked up; anything vendored or bundled another way needs a section in the script.

Qt/PySide6 and pynput are LGPL-3: they stay separate libraries inside the exe, and since Speak's source and build script are public anyone can rebuild with a modified copy. Keep it that way (no static linking, no closed forks of the bundle).

`tools/hooks/hook-sounddevice.py` overrides the contrib hook so only the plain PortAudio library is bundled, not the ASIO builds (Steinberg ASIO SDK, GPL-3/proprietary) that sounddevice never loads by default.

Models aren't bundled (downloaded on first use): Nemotron 3.5 ASR is OpenMDW-1.1, Qwen models are Apache-2.0.

Donation links (`COFFEE_URL`, `SPONSOR_URL` in `speak/config.py`, `.github/FUNDING.yml`) show on the About page (GitHub Sponsors primary, Buy Me a Coffee secondary), the README and the repo's Sponsor button.

## Privacy

Microphone audio is held in memory only and sent to the app-owned local runtime on loopback. History stores transcript text only, and only when enabled. Network use: model downloads (Hugging Face) and the update check/download (GitHub releases; can be turned off).
