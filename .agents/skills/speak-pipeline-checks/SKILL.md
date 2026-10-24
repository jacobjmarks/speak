---
name: speak-pipeline-checks
description: Headless end-to-end checks of Speak's speech pipeline (real ASR server + tidy/cleanup LLM) on WAV files, benchmarking tidy models/devices, and idle-unload/VRAM checks. Use when touching asr.py, cleanup.py, tidy.py, runtimes.py, config model catalogs, or controller warm-up/unload.
---

# Headless pipeline checks

## 1. Get a test WAV (16-bit mono, 16 kHz)

Windows built-in TTS gives repeatable audio with no mic:

```powershell
Add-Type -AssemblyName System.Speech
$dir = "$env:TEMP\asrtest"; New-Item -ItemType Directory -Force $dir | Out-Null
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SetOutputToWaveFile("$dir\short.wav", $fmt)
$s.Speak("So I was thinking we could meet at the cafe around four, um, actually five."); $s.Dispose()
```

Use text with the things the cleanup must handle: fillers ("um"), self-corrections ("no actually"), spoken punctuation ("comma", "new line"), numbers, long runs (cleanup latency scales with length). For pauses, insert silence into the WAV with Python's `wave` module.

## 2. Run the real pipeline

```powershell
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe -m tools.dictate_wav "$env:TEMP\asrtest\short.wav" --tidy fast,auto,best
.\.venv\Scripts\python.exe -m tools.dictate_wav "$env:TEMP\asrtest\short.wav" --tidy auto --cpu   # force CPU
```

It starts the bundled servers, streams the WAV, prints RAW ASR text, then for each tidy level the plan (model, device, LLM mode), warm timing, and the cleaned text. Read the actual strings: check that meaning is preserved, fillers are gone, and nothing was invented. If `cleanup.validate()` rejects an output, the raw text falls through.

Notes:
- First run per model downloads it. Use `initial_wait` 240-300 and filter progress lines (`Where-Object { $_ -notmatch "\.\. " }`).
- See the script's argparse for current flags (e.g. `--model <id from config.CLEANUP_MODELS>`, `--mode smart`).
- Benchmark rules: warm the model first (the tool does), run each variant on the same WAVs, record load time, speed, and memory. Record findings in `tidy.py`'s docstring (where benchmarks live) or `docs/`.
- GPU use: `nvidia-smi --query-gpu=memory.used --format=csv,noheader` before/after; the llama.cpp log (`config.CLEANUP_LOG`, under `%LOCALAPPDATA%\Speak`) shows the device and offloaded layers.

## 3. Check idle unload / warm-up in-process

```powershell
$env:PYTHONPATH=(Get-Location).Path
@'
import time, subprocess
from speak.config import load_settings
from speak.controller import Dictation, Listener
def vram(): return subprocess.run(["nvidia-smi","--query-gpu=memory.used","--format=csv,noheader"],capture_output=True,text=True).stdout.strip()
d = Dictation({**load_settings(), "unload_after": "0.05"}, Listener())   # ~3 s idle
print("before", vram()); d.warm_up()
for _ in range(60):
    time.sleep(0.5)
    if d.cleanup_server.process: break
time.sleep(2); print("loaded", vram(), d.asr_server.process is not None)
time.sleep(6); print("after idle", vram(), d.asr_server.process, d.cleanup_server.process)
d.shutdown()
'@ | .\.venv\Scripts\python.exe -
```

Expect servers present when loaded, `None` and lower VRAM after idle. Always call `d.shutdown()`, then confirm no stray `llama-server`/`nemo-speech`.

## 4. Pure-logic checks (no servers)

`cleanup`'s regex rules and `validate()`, `tidy.plan()`, `updates.parse/pick`, and `config.load_settings` migrations are plain functions: call them in a throwaway script or add a `tools/test_*.py` `unittest` (see `tools/test_tidy.py`: patch hardware probes with `unittest.mock`). Add a test whenever you fix a bug in these.
