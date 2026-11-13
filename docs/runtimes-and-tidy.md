# Runtimes and tidy-up

How Speak's bundled runtimes, tidy-up levels and process lifecycle behave. Settings and module ownership are in [AGENTS.md](../AGENTS.md).

## Tidy levels

| Level | What happens | Typical speed |
|---|---|---|
| Off | Spoken commands only ("new paragraph") | instant |
| Fast | Rules: drop fillers/stutters, pauses after sentences → paragraphs | instant |
| Automatic | Large model (Qwen3 4B) when GPU memory fits, otherwise Small (Qwen 2.5 0.5B) | ~0.5 s |
| Best | Large model on GPU, or CPU if there's RAM | 0.5 s GPU, a few s CPU |

The Large model handles self-corrections ("three, no wait, four"); Small only punctuates (literal mode). The *Fix changes of mind* setting (`corrections`) runs Large in literal mode when off. A correction *reach* ("only the last sentence") was tried via prompting; Qwen3 4B ignored it, so it's on/off only.

Single instance: `QLockFile` (`speak.lock` in the data folder; a dead owner's lock is taken over) plus a `QLocalServer` so a second launch shows the running window and exits. Two instances would each hear the shortcut and paste twice. An update relaunch passes `--restarted` and waits up to 15 s for the old lock.

Both runtimes unload after `unload_after` idle minutes (default 5; Advanced → *Free up memory when idle*): speech ~1 GB RAM, large tidy ~3 GB VRAM. Reload costs ~2-4 s on the next dictation. Launch preloads them unless started at login (background) or set to unload right away.

ASR runs with `--asr.streaming.rnnt_right_context=-1` (max lookahead, ~0.25 s): better words and punctuation on clean speech, same finish time, live text every 320 ms. A full offline re-pass (`POST /v1/audio/transcriptions`) was tested: ~1.6 s per 20 s of audio and worse on noisy audio, so not used. Context-dependent word fixes ("pair" → "pear") are left to the tidy model.

Model output is validated (length/similarity bounds, no invented numbers, no dropped words in literal mode); on failure the rule-processed text is used.

The llama.cpp server runs with `--parallel 1`, a pinned `--device`, and a warm-up request so the first dictation hits a warm prompt cache. Device selection budgets model file size plus runtime headroom (512 MB for Small, 1.5 GB for Large). Device choice is memory-budget based. The probe also runs the bundled `llama-bench --list-devices`, which prints llama.cpp's own `uma` (shared-memory) flag per Vulkan device; shared-memory GPUs are skipped in Automatic (still forceable in Advanced) and dedicated GPUs rank first. If `llama-bench` is missing or prints nothing, no GPU is treated as integrated. A first-run setup page (`ui/onboarding/`) tests latency and lets users tune these.

Advanced settings can pin the Small or Large model, and choose the tidy-up device: Automatic (recommended), CPU only, GPU Automatic (best available), or a specific detected GPU. GPU entries show the device name only; available memory fluctuates and is not shown. A specific device is stored as its llama.cpp id (e.g. `Vulkan1`); the list fills in after the probe. If the selected GPU is unavailable or lacks memory, cleanup falls back to CPU and the tidy summary explains why.

Benchmarks and model comparisons: `speak/tidy.py` docstring (device/model benchmarks) and [MODEL-VALUE-INVESTIGATION.md](MODEL-VALUE-INVESTIGATION.md).
