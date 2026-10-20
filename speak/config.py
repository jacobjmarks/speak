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
    "hotkey": "ctrl+shift+space",
    "close_action": "ask",
    "history_enabled": False,
    "auto_paste": True,
    "overlay_enabled": True,
    "live_preview": True,
    "model": "nemotron-3.5",
    "language": "auto",
    "cleanup_enabled": True,
    "cleanup_mode": "smart",
    "cleanup_model": "auto",
    "theme": "System",
}

ASR_MODELS = {"nemotron-3.5": "Nemotron 3.5 ASR (multilingual)"}

CLEANUP_MODELS = {
    "qwen3-4b-2507": {
        "label": "Qwen3 4B Instruct 2507 (smartest, 2.5 GB)",
        "repo": "bartowski/Qwen_Qwen3-4B-Instruct-2507-GGUF",
        "file": "Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
    },
    "qwen3-1.7b": {
        "label": "Qwen3 1.7B (best, 1.3 GB)",
        "repo": "bartowski/Qwen_Qwen3-1.7B-GGUF",
        "file": "Qwen_Qwen3-1.7B-Q4_K_M.gguf",
    },
    "qwen25-1.5b": {
        "label": "Qwen 2.5 1.5B (1.1 GB)",
        "repo": "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        "file": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
    },
    "qwen25-q4km": {
        "label": "Qwen 2.5 0.5B (fastest, 491 MB)",
        "repo": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "file": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
    },
    "qwen25-q8": {
        "label": "Qwen 2.5 0.5B Q8 (676 MB)",
        "repo": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "file": "qwen2.5-0.5b-instruct-q8_0.gguf",
    },
}

CLEANUP_MODES = {"literal": "Light: punctuation only (fast)", "smart": "Smart: also fixes self-corrections & fillers"}
# "auto" picks the model per mode; benchmarks in docs/wayfinder/research/dictation-quality.md.
AUTO_CLEANUP_MODEL = {"literal": "qwen25-q4km", "smart": "qwen3-4b-2507"}
CLOSE_ACTIONS = {"ask": "Ask me", "tray": "Keep running in the tray", "exit": "Quit Speak"}
THEMES = ("System", "Light", "Dark")


def cleanup_model_id(settings: dict) -> str:
    if settings["cleanup_model"] in CLEANUP_MODELS:
        return settings["cleanup_model"]
    return AUTO_CLEANUP_MODEL[settings["cleanup_mode"]]


def load_settings() -> dict:
    try:
        stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        stored = {}
    settings = {**DEFAULTS, **stored}
    if stored and "cleanup_mode" not in stored:
        settings["cleanup_model"] = "auto"  # pre-0.3 settings pinned a model the old UI always saved
    if settings["model"] not in ASR_MODELS:
        settings["model"] = DEFAULTS["model"]
    if settings["cleanup_model"] not in CLEANUP_MODELS:
        settings["cleanup_model"] = "auto"
    if settings["cleanup_mode"] not in CLEANUP_MODES:
        settings["cleanup_mode"] = DEFAULTS["cleanup_mode"]
    if settings["close_action"] not in CLOSE_ACTIONS:
        settings["close_action"] = DEFAULTS["close_action"]
    return settings


def save_settings(settings: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
