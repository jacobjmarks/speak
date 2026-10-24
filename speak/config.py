"""Paths, defaults, model catalogs, and settings persistence."""
import json

from .platform_utils import TRAY_NAME, app_data_dir

APP_DIR = app_data_dir()
SETTINGS_FILE = APP_DIR / "settings.json"
HISTORY_FILE = APP_DIR / "history.sqlite3"
MODELS_DIR = APP_DIR / "models"
ASR_LOG = APP_DIR / "runtime.log"
CLEANUP_LOG = APP_DIR / "cleanup-runtime.log"

REPO_URL = "https://github.com/jacobjmarks/speak"
COFFEE_URL = "https://buymeacoffee.com/jacobjmarks"
SPONSOR_URL = "https://github.com/sponsors/jacobjmarks"

AUDIO_DIM_STEP = 5


def snap_audio_dim_percent(percent: int) -> int:
    return ((percent + AUDIO_DIM_STEP // 2) // AUDIO_DIM_STEP) * AUDIO_DIM_STEP


# close_action: "ask" until the user answers the first-close prompt, then "tray" or "exit".
DEFAULTS = {
    "hotkey": "right alt",
    "shortcut_mode": "auto",
    "close_action": "ask",
    "history_enabled": False,
    "auto_paste": True,
    "press_enter": False,  # experimental: Enter after pasting, only if the same app is still in front
    "audio_dim_enabled": False,
    "audio_dim_percent": 20,
    "advanced_settings": False,
    "onboarding_done": False,  # first-run setup finished or skipped; existing installs count as done
    "mic_device": None,  # device name; None = system default
    "overlay_enabled": True,
    "overlay_position": "cursor",
    "live_preview": "line",
    "model": "nemotron-3.5",
    "language": "auto",
    "tidy": "auto",
    "corrections": True,  # large model drops "no wait, ..." originals; False keeps every word
    "cleanup_model": "auto",
    "cleanup_device": "auto",
    "theme": "System",
    "updates": "notify",
    "prereleases": False,
    "unload_after": "5",  # minutes idle before models leave RAM/VRAM; "never" keeps them
}

ASR_MODELS = {"nemotron-3.5": "Nemotron 3.5 ASR (multilingual)"}

# Benchmarks: docs/wayfinder/research/dictation-quality.md. Only Large handles self-corrections.
CLEANUP_MODELS = {
    "qwen25-q4km": {
        "label": "Small · Qwen 2.5 0.5B (0.5 GB)",
        "repo": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "file": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "size_mb": 491,
        "runtime_headroom_mb": 512,
    },
    "qwen3-4b-2507": {
        "label": "Large · Qwen3 4B Instruct (2.5 GB)",
        "repo": "bartowski/Qwen_Qwen3-4B-Instruct-2507-GGUF",
        "file": "Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
        "size_mb": 2500,
        "runtime_headroom_mb": 1500,
    },
}
SMALL_MODEL, LARGE_MODEL = "qwen25-q4km", "qwen3-4b-2507"

SHORTCUT_MODES = {"auto": "Hold or tap", "hold": "Hold to talk", "toggle": "Tap to start and stop"}
TIDY_LEVELS = {"off": "Off", "fast": "Fast · no AI", "auto": "Automatic · recommended", "best": "Best · always AI"}
# Any other saved value is a llama.cpp device id (e.g. "Vulkan1") picked from the detected graphics cards.
CLEANUP_DEVICES = {
    "auto": "Automatic (recommended)",
    "cpu": "CPU: Processor only",
    "gpu": "GPU: Automatic (best available)",
}
CLOSE_ACTIONS = {"ask": "Ask me", "tray": f"Keep running in the {TRAY_NAME}", "exit": "Quit Speak"}
OVERLAY_POSITIONS = {"cursor": "Below my cursor", "top": "Top of screen", "bottom": "Bottom of screen"}
LIVE_PREVIEWS = {"line": "One sliding line", "full": "Full text", "off": "Off"}
THEMES = ("System", "Light", "Dark")
# Speech model ~1 GB RAM, large tidy model ~3 GB VRAM. Reloading costs ~2-4 s on the next dictation.
UNLOAD_AFTER = {"0": "Right away (slower start)", "5": "After 5 minutes", "30": "After 30 minutes", "never": "Never"}
UPDATE_MODES = {"auto": "Install automatically", "notify": "Just tell me", "off": "Don't check"}


def load_settings() -> dict:
    try:
        stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        stored = {}
    settings = {**DEFAULTS, **stored}
    if stored and "tidy" not in stored:  # pre-tidy settings used cleanup_enabled + cleanup_mode
        settings["tidy"] = "auto" if stored.get("cleanup_enabled", True) else "off"
        settings["cleanup_model"] = "auto"
    if settings["tidy"] == "balanced":
        settings["tidy"] = "auto"
    if isinstance(settings["live_preview"], bool):
        settings["live_preview"] = "line" if settings["live_preview"] else "off"
    if stored and "onboarding_done" not in stored:
        settings["onboarding_done"] = True
    elif not isinstance(settings["onboarding_done"], bool):
        settings["onboarding_done"] = DEFAULTS["onboarding_done"]
    if not isinstance(settings["audio_dim_enabled"], bool):
        settings["audio_dim_enabled"] = DEFAULTS["audio_dim_enabled"]
    if (not isinstance(settings["audio_dim_percent"], int) or isinstance(settings["audio_dim_percent"], bool)
            or not 10 <= settings["audio_dim_percent"] <= 90):
        settings["audio_dim_percent"] = DEFAULTS["audio_dim_percent"]
    else:
        settings["audio_dim_percent"] = snap_audio_dim_percent(settings["audio_dim_percent"])
    if "hold_to_talk" in stored and "shortcut_mode" not in stored:
        settings["shortcut_mode"] = "auto" if stored["hold_to_talk"] else "toggle"
    if "check_updates" in stored and "updates" not in stored:
        settings["updates"] = "auto" if stored["check_updates"] else "off"
    for key in ("cleanup_enabled", "cleanup_mode", "check_updates", "hold_to_talk"):
        settings.pop(key, None)
    if settings["model"] not in ASR_MODELS:
        settings["model"] = DEFAULTS["model"]
    if settings["cleanup_model"] not in CLEANUP_MODELS:
        settings["cleanup_model"] = "auto"
    if not isinstance(settings["cleanup_device"], str) or not settings["cleanup_device"]:
        settings["cleanup_device"] = DEFAULTS["cleanup_device"]
    for key, allowed in (("tidy", TIDY_LEVELS), ("close_action", CLOSE_ACTIONS),
                         ("overlay_position", OVERLAY_POSITIONS), ("live_preview", LIVE_PREVIEWS), ("updates", UPDATE_MODES),
                         ("shortcut_mode", SHORTCUT_MODES), ("unload_after", UNLOAD_AFTER)):
        if settings[key] not in allowed:
            settings[key] = DEFAULTS[key]
    return settings


def save_settings(settings: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")