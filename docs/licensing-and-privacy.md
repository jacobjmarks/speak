# Licensing and privacy

## Licensing

The build runs `tools/make_notices.py`, which writes `build/THIRD_PARTY_NOTICES.txt` (Python, every runtime pip dependency's licence files, PySide6/Qt LGPL-3, PortAudio, PyInstaller bootloader, NeMo-Speech.cpp and llama.cpp licences, model attributions, LGPL-3/GPL-3 texts from `licenses/`) and bundles it; The About page's *Open-source notices* link opens it, or this section when no bundled notices are available. No root `LICENSE` file is required. Add new dependencies to `requirements.txt` and they're picked up; anything vendored or bundled another way needs a section in the script.

Qt/PySide6 and pynput are LGPL-3: they stay separate libraries inside the exe, and since Speak's source and build script are public anyone can rebuild with a modified copy. Keep it that way (no static linking, no closed forks of the bundle).

`tools/hooks/hook-sounddevice.py` overrides the contrib hook so only the plain PortAudio library is bundled, not the ASIO builds (Steinberg ASIO SDK, GPL-3/proprietary) that sounddevice never loads by default.

Models aren't bundled (downloaded on first use): Nemotron 3.5 ASR is OpenMDW-1.1, Qwen models are Apache-2.0.

Donation links (`COFFEE_URL`, `SPONSOR_URL` in `speak/config.py`, `.github/FUNDING.yml`) show on the About page (GitHub Sponsors primary, Buy Me a Coffee secondary), the README and the repo's Sponsor button.

## Privacy

Microphone audio is held in memory only and sent to the app-owned local runtime on loopback. History stores transcript text only, and only when enabled. Network use: model downloads (Hugging Face) and the update check/download (GitHub releases; can be turned off).
Optional system audio dimming is off by default. On Windows and macOS it lowers output volume by the chosen percentage only while the microphone is listening, then restores the previous level if the user has not changed it meanwhile. It requires no additional macOS permission.
