"""Decides how to tidy a transcript on *this* computer: which model, on which device, and why.

Levels (settings["tidy"]):
  off       spoken commands only ("new paragraph"), verbatim otherwise. No model.
  fast      rules only: spoken commands, drop ums/stutters, pauses after sentences -> paragraphs. Instant.
  auto      smartest model that stays under ~1 s here: Large on a capable GPU, else Small on CPU.
            (Was "balanced"; renamed because on a GPU it is Best, and on CPU it's the Small model.)
  best      always Large (self-corrections, paragraphs): GPU if possible, else CPU (a few seconds).
            On a capable GPU, auto and best are identical; the summary says so.
settings["corrections"] False runs Large in literal mode (no words dropped). Prompting for a correction *reach*
("only the last sentence") was tried with Qwen3 4B and ignored, so it's on/off only.
Warm timings that informed this (Ryzen 9800X3D / RTX 3080): Large GPU ~0.45 s, Large CPU ~4 s, Small CPU ~0.6 s.
"""
import re
import subprocess
import threading
from dataclasses import dataclass
from typing import Optional

from . import platform_utils
from .config import CLEANUP_MODELS, LARGE_MODEL, MODELS_DIR, SMALL_MODEL

GPU_MIN_FREE_MB = 4000   # Large model (~2.5 GB) + KV cache + headroom
CPU_LARGE_MIN_RAM_MB = 4500
INTEGRATED = re.compile(r"\b(UHD|Iris|HD Graphics|Radeon\(TM\) Graphics|Radeon Graphics|Vega \d+ Graphics)\b", re.I)


@dataclass(frozen=True)
class Gpu:
    device: str  # llama.cpp device id, e.g. "Vulkan0" or "MTL0"
    name: str
    free_mb: int


@dataclass(frozen=True)
class Plan:
    level: str
    model_id: Optional[str]   # None = no model
    llm_mode: str             # "smart" (rewrites corrections) or "literal" (punctuation only)
    device: Optional[str]     # llama.cpp --device, None = CPU
    summary: str              # one line for the settings page

    @property
    def key(self):
        return (self.model_id, self.device)


_gpu: Optional[Gpu] = None
_probed = threading.Event()


def probe(llama_server) -> None:
    """Ask llama.cpp which accelerators it can use. Slow-ish (~0.5 s); call once from a worker thread."""
    global _gpu
    try:
        out = subprocess.run([str(llama_server), "--list-devices"], capture_output=True, text=True, timeout=20,
                             **platform_utils.hidden_process_kwargs())
        best = None
        for device, name, free in re.findall(r"^\s*(\S+): (.+?) \(\d+ MiB, (\d+) MiB free\)", out.stdout + out.stderr,
                                             re.M):
            if INTEGRATED.search(name) and not platform_utils.IS_MAC:
                continue  # shared-memory iGPUs report system RAM and are rarely faster than the CPU
            gpu = Gpu(device, name.strip(), int(free))
            if best is None or gpu.free_mb > best.free_mb:
                best = gpu
        _gpu = best
    except Exception:
        _gpu = None
    finally:
        _probed.set()


def gpu() -> Optional[Gpu]:
    return _gpu


def probed() -> bool:
    return _probed.is_set()


def plan(settings: dict) -> Plan:
    level = settings["tidy"]
    if level == "off":
        return Plan(level, None, "literal", None, "Exactly what you said, plus spoken commands like “new paragraph”.")
    if level == "fast":
        return Plan(level, None, "literal", None, "Instant. Removes ums and repeats, adds paragraphs. No download.")

    g = _gpu if _gpu and _gpu.free_mb >= GPU_MIN_FREE_MB else None
    pinned = settings.get("cleanup_model")
    if pinned in CLEANUP_MODELS:
        model = pinned
    elif level == "auto":
        model = LARGE_MODEL if g else SMALL_MODEL
    else:
        model = LARGE_MODEL if g or platform_utils.available_memory_mb() >= CPU_LARGE_MIN_RAM_MB else SMALL_MODEL

    device = g.device if g else None
    downloaded = (MODELS_DIR / "cleanup" / CLEANUP_MODELS[model]["file"]).exists()
    size = "" if downloaded else f" {CLEANUP_MODELS[model]['size_mb'] / 1000:.1f} GB download on first use."
    where = "graphics card" if g else "processor"
    if model == LARGE_MODEL:
        speed = "about half a second" if g else "a few seconds"
        mode = "smart" if settings.get("corrections", True) else "literal"
        what = ("Punctuation, paragraphs, changes of mind." if mode == "smart" else
                "Punctuation and paragraphs, every word kept.")
        name = "Large AI"
    else:
        speed = "under a second"
        what = "Punctuation and capitals only."
        mode = "literal"
        name = "Small AI"
    if pinned in CLEANUP_MODELS:
        note = " Model chosen in Advanced."
    elif g:
        note = " Same as Best here." if level == "auto" else " Same as Automatic here."
    elif level == "best" and model != LARGE_MODEL:
        note = " Not enough free memory for the large model."
    else:
        note = ""
    return Plan(level, model, mode, device, f"{name} on your {where}, {speed}. {what}{size}{note}")
