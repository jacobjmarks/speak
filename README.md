# Speak

Local dictation. Press `Ctrl+Shift+Space` (configurable) to start or stop listening. Speak transcribes on-device with NVIDIA Nemotron 3.5 ASR. A small floating pill near your cursor shows a live waveform and your words as you speak, then turns into a spinner while Speak tidies the text and pastes it into the focused app. History is off by default.

Settings show only user-level choices: shortcut, tidy-up level, paste, close behaviour, start with computer, history, appearance. Model, language and indicator options live under **Advanced**. The first time you close the window Speak asks whether to keep running in the tray or quit.

The distributable includes the NeMo-Speech.cpp ASR runtime, llama.cpp text-cleanup runtime, and their dependencies. Model weights download from Hugging Face on first use. No Python install, separate model runner, or background service is required from the user.

## Run from source

Requires Python 3.11+ (UI is PySide6). Windows is the supported build today; macOS/Linux support is in progress:

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


ASR is Nemotron 3.5 (`nvidia/nemotron-3.5-asr-streaming-0.6b`). **Tidy up my words** has three levels: *Smart* (default; punctuation, paragraphs, removes fillers and applies spoken self-corrections such as "Tuesday, no, Wednesday"; uses Qwen3 4B Instruct 2507, about 2.5 GB), *Light* (punctuation only; Qwen 2.5 0.5B, about 491 MB) and *Off*. Advanced settings can pin a specific cleanup model. Both runtimes are CPU builds. Theme follows the OS by default, or can be forced Light/Dark.

Each push to `main` builds the one-file executable and publishes it as a GitHub Release.

## How cleanup works

Nemotron streams provisional partial text into the app buffer while recording. On stop, Speak commits the audio stream and waits for the final ASR text, marks long pauses (from word timestamps) as paragraph hints, applies spoken commands ("new paragraph", "full stop", "question mark"), then sends the transcript to a locally bundled llama.cpp server. The prompt and few-shot examples ask for punctuation, paragraphs and (Smart) self-correction only, and forbid summarizing or adding content. Output is validated (length/similarity bounds, no invented numbers); if it fails, the rule-processed text is used instead. Audio and transcript requests stay on loopback; model weights are downloaded once and cached under `%LOCALAPPDATA%\Speak\models`.

If the cleanup model cannot download, start, or return text, Speak keeps the Nemotron transcript and reports that cleanup failed. Turning cleanup off skips the second-model pass and uses Nemotron's native punctuation/capitalization setting.

## Privacy and storage

Microphone audio is held in memory only and sent to the app-owned local runtime. History stores transcript text only, only when explicitly enabled. The runtime downloads model weights from Hugging Face on first use; transcription itself is local.
