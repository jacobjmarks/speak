# Speak

Windows-first local dictation. Press `Ctrl+Shift+Space` to start or stop listening. Speak transcribes on-device with NVIDIA Nemotron 3.5 ASR, shows provisional partial text while you speak, then optionally cleans up the complete transcript before pasting it into the focused app. History is off by default.

The distributable includes the NeMo-Speech.cpp ASR runtime, llama.cpp text-cleanup runtime, and their dependencies. Model weights download from Hugging Face on first use. No Python install, separate model runner, or background service is required from the user.

## Run from source

Requires Windows, Python 3.11+, and Tkinter for development:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\build.ps1
	.\dist\Speak.exe
```

`build.ps1` downloads and checksum-verifies the pinned NeMo-Speech.cpp and llama.cpp Windows CPU releases, bundles both runtimes into one executable at `dist\Speak.exe`, and downloads model weights on first use into `%LOCALAPPDATA%\Speak\models`.

Use `./build.ps1 -OutputDirectory ./dist-next` to build beside an open app copy without replacing locked files.

## Model selection


The ASR dropdown contains Nemotron 3.5 ASR (`nemotron-3.5`), mapping to `nvidia/nemotron-3.5-asr-streaming-0.6b`. Cleanup offers Qwen 2.5 0.5B Q4_K_M (about 491 MB) or Q8_0 (about 676 MB) and can be disabled. Both runtimes are CPU builds. Theme follows Windows by default, or can be forced Light/Dark.

Each push to `main` builds the one-file executable and publishes it as a GitHub Release.

## How cleanup works

Nemotron streams provisional partial text into the app buffer while recording. On stop, Speak commits the audio stream and waits for the final ASR text, sends that entire transcript to a locally bundled llama.cpp server, then replaces the provisional text with the cleanup result before history storage or paste. The Qwen prompt requests only punctuation, capitalization, and obvious recognition/disfluency corrections, and explicitly forbids summarizing or adding content. Generation uses low temperature and no reasoning mode. Audio and transcript requests stay on loopback; model weights are downloaded once and cached under `%LOCALAPPDATA%\Speak\models`.

If the cleanup model cannot download, start, or return text, Speak keeps the Nemotron transcript and reports that cleanup failed. Turning cleanup off skips the second-model pass and uses Nemotron's native punctuation/capitalization setting.

## Privacy and storage

Microphone audio is held in memory only and sent to the app-owned local runtime. History stores transcript text only, only when explicitly enabled. The runtime downloads model weights from Hugging Face on first use; transcription itself is local.
