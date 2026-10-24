---
name: speak-marketing-images
description: "Create, update, or review Speak's README and documentation images, product screenshots, or hero graphic. Use when changing docs/images, capturing real UI states, or making new promotional images."
---

# Maintain Speak's documentation images

## Regenerate the README set

From the repo root:

```powershell
.\.venv\Scripts\python.exe -m tools.marketing_images
```

The script writes seven PNGs into `docs/images/`: light and dark Dictate/Settings screenshots, light and dark overlay screenshots, and the README hero. Pass a different output directory to preview changes without overwriting tracked images:

```powershell
.\.venv\Scripts\python.exe -m tools.marketing_images "$env:TEMP\speak-images"
```

Open the generated PNGs with the `view` tool. Check framing, text, theme, spacing, and that screenshots still illustrate the current interface. Compare the preview with `docs/images/` before replacing the published assets.

## How the originals were made

- Screenshots are real PySide6 widgets from `SpeakApp`, not browser mockups. The script forces a successful example result into Dictate, switches to Settings, and captures the floating `Overlay` separately.
- The hero is a 1280 × 440 `QPixmap` painted with `QPainter`: gradient background, the app's `app_icon()`, tagline, feature line, and scaled dark overlay.
- A fixed sample transcript makes screenshots repeatable. Update `EXAMPLE` or `LIVE_TEXT` in the tool when the copy should change; keep sample content short enough not to clip.
- The script writes settings, history, and logs under a temporary app-data directory; disables hotkey registration, permissions checks, model warm-up, and update checks. It needs no microphone, model download, or real user settings.
- Capture timing uses short Qt timer delays so pages render before `grab()`. If UI transitions change, adjust the capture steps in `tools/marketing_images.py`, then render and inspect every output.

## Add another image

Prefer rendering the actual page or widget so screenshots remain faithful to the app. Add a named capture in `tools/marketing_images.py`; for a new view, navigate with `window.show_page(index)`, set state with the page's public methods, then save via `window.grab()` or `overlay.grab()`. For a composed illustration, use `QPainter` and existing app assets such as `app_icon()` and `ui/theme.py` palettes.

Keep README links and alt text in sync with any renamed or added `docs/images/*` file. After changing UI code, use `speak-ui-screenshots` for exhaustive state review; these marketing captures are curated product examples, not a substitute for that regression check.
