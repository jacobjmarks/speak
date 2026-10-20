"""Paths, defaults, model catalogs, and settings persistence."""
import json

from .platform_utils import app_data_dir

APP_DIR = app_data_dir()
SETTINGS_FILE = APP_DIR / "settings.json"
HISTORY_FILE = APP_DIR / "history.sqlite3"
MODELS_DIR = APP_DIR / "models"
ASR_LOG = APP_DIR / "runtime.log"
CLEANUP_LOG = APP_DIR / "cleanup-runtime.log"

# close_action: "ask" until the user answers the first-close prompt, then "tray" or "exit".
DEFAULTS = {
    "hotkey": "right alt",
    "close_action": "ask",
    "history_enabled": False,
    "auto_paste": True,
    "mic_device": None,  # device name; None = system default
    "overlay_enabled": True,
    "overlay_position": "cursor",
    "live_preview": "line",
    "model": "nemotron-3.5",
    "language": "auto",
    "tidy": "balanced",
    "cleanup_model": "auto",
    "theme": "System",
    "check_updates": True,
}

ASR_MODELS = {"nemotron-3.5": "Nemotron 3.5 ASR (multilingual)"}

# Benchmarks: docs/wayfinder/research/dictation-quality.md. Only Large handles self-corrections.
CLEANUP_MODELS = {
    "qwen25-q4km": {
        "label": "Small · Qwen 2.5 0.5B (0.5 GB)",
        "repo": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "file": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "size_mb": 491,
    },
    "qwen3-4b-2507": {
        "label": "Large · Qwen3 4B Instruct (2.5 GB)",
        "repo": "bartowski/Qwen_Qwen3-4B-Instruct-2507-GGUF",
        "file": "Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
        "size_mb": 2500,
    },
}
SMALL_MODEL, LARGE_MODEL = "qwen25-q4km", "qwen3-4b-2507"

TIDY_LEVELS = {"off": "Off", "fast": "Fast", "balanced": "Balanced", "best": "Best"}
CLOSE_ACTIONS = {"ask": "Ask me", "tray": "Keep running in the tray", "exit": "Quit Speak"}
OVERLAY_POSITIONS = {"cursor": "Near my cursor", "top": "Top of screen", "bottom": "Bottom of screen"}
LIVE_PREVIEWS = {"line": "One sliding line", "full": "Full text", "off": "Off"}
THEMES = ("System", "Light", "Dark")


def load_settings() -> dict:
    try:
        stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        stored = {}
    settings = {**DEFAULTS, **stored}
    if stored and "tidy" not in stored:  # pre-tidy settings used cleanup_enabled + cleanup_mode
        settings["tidy"] = "balanced" if stored.get("cleanup_enabled", True) else "off"
        settings["cleanup_model"] = "auto"
    if isinstance(settings["live_preview"], bool):
        settings["live_preview"] = "line" if settings["live_preview"] else "off"
    for key in ("cleanup_enabled", "cleanup_mode"):
        settings.pop(key, None)
    if settings["model"] not in ASR_MODELS:
        settings["model"] = DEFAULTS["model"]
    if settings["cleanup_model"] not in CLEANUP_MODELS:
        settings["cleanup_model"] = "auto"
    for key, allowed in (("tidy", TIDY_LEVELS), ("close_action", CLOSE_ACTIONS),
                         ("overlay_position", OVERLAY_POSITIONS), ("live_preview", LIVE_PREVIEWS)):
        if settings[key] not in allowed:
            settings[key] = DEFAULTS[key]
    return settings


def save_settings(settings: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")