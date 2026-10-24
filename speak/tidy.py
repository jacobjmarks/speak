"""Decides how to tidy a transcript on *this* computer: which model, on which device, and why.

Levels (settings["tidy"]):
  off       spoken commands only ("new paragraph"), verbatim otherwise. No model.
  fast      rules only: spoken commands, drop ums/stutters, pauses after sentences -> paragraphs. Instant.
  auto      Large on a suitable GPU, else Small (uses the GPU too when Small fits).
            (Was "balanced"; renamed because on a capable GPU it is Best.)
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

from pathlib import Path

from . import platform_utils
from .config import CLEANUP_MODELS, LARGE_MODEL, MODELS_DIR, SMALL_MODEL


@dataclass(frozen=True)
class Gpu:
    device: str  # llama.cpp device id, e.g. "Vulkan0" or "MTL0"
    name: str
    free_mb: int
    integrated: bool = False  # shares system RAM instead of having dedicated memory


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
_gpus: list = []
_probed = threading.Event()


def _integrated_devices(llama_server) -> set:
    """Vulkan devices that llama.cpp flags as unified-memory (uma: 1). llama-server --list-devices omits this; the
    bundled llama-bench prints it. Missing or unparsable -> empty set (no device is treated as integrated)."""
    try:
        bench = Path(llama_server).with_name("llama-bench" + Path(llama_server).suffix)
        out = subprocess.run([str(bench), "--list-devices"], capture_output=True, text=True, timeout=20,
                             **platform_utils.hidden_process_kwargs())
        return {f"Vulkan{i}" for i, uma in re.findall(r"ggml_vulkan: (\d+) = .*?\| uma: (\d)", out.stdout + out.stderr)
                if uma == "1"}
    except Exception:
        return set()


def probe(llama_server) -> None:
    """Ask llama.cpp which accelerators it can use. Slow-ish (~0.5 s); call once from a worker thread."""
    global _gpu, _gpus
    try:
        out = subprocess.run([str(llama_server), "--list-devices"], capture_output=True, text=True, timeout=20,
                             **platform_utils.hidden_process_kwargs())
        integrated = _integrated_devices(llama_server)
        found = []
        best = None
        for device, name, free in re.findall(r"^\s*(\S+): (.+?) \(\d+ MiB, (\d+) MiB free\)", out.stdout + out.stderr,
                                             re.M):
            gpu = Gpu(device, name.strip(), int(free), device in integrated)
            found.append(gpu)
            if best is None or (not gpu.integrated, gpu.free_mb) > (not best.integrated, best.free_mb):
                best = gpu
        _gpu, _gpus = best, found
    except Exception:
        _gpu, _gpus = None, []
    finally:
        _probed.set()


def gpus() -> list:
    return list(_gpus)


def gpu() -> Optional[Gpu]:
    return _gpu


def probed() -> bool:
    return _probed.is_set()


def _memory_required_mb(model_id: str) -> int:
    model = CLEANUP_MODELS[model_id]
    return model["size_mb"] + model["runtime_headroom_mb"]


def plan(settings: dict) -> Plan:
    level = settings["tidy"]
    if level == "off":
        return Plan(level, None, "literal", None, "Exactly what you said, plus spoken commands like “new paragraph”.")
    if level == "fast":
        return Plan(level, None, "literal", None, "Instant. Removes ums and repeats, adds paragraphs. No download.")

    preference = settings.get("cleanup_device", "auto")
    if preference not in ("auto", "cpu", "gpu"):
        g = next((x for x in _gpus if x.device == preference), None)
        preference = "gpu"  # a specific card is always a forced choice
    else:
        g = _gpu if preference != "cpu" else None
    if g and g.integrated and preference == "auto":
        g = None  # forcing the GPU in Advanced still allows it
    gpu_for_large = g if g and g.free_mb >= _memory_required_mb(LARGE_MODEL) else None
    pinned = settings.get("cleanup_model")
    if pinned in CLEANUP_MODELS:
        model = pinned
    elif level == "auto":
        model = LARGE_MODEL if gpu_for_large else SMALL_MODEL
    elif preference == "gpu":
        model = LARGE_MODEL if gpu_for_large else SMALL_MODEL
    else:
        model = LARGE_MODEL if gpu_for_large or platform_utils.available_memory_mb() >= \
            _memory_required_mb(LARGE_MODEL) else SMALL_MODEL

    gpu_for_model = g if g and g.free_mb >= _memory_required_mb(model) else None
    use_gpu = preference == "gpu" or (preference == "auto" and gpu_for_model is not None)
    device = gpu_for_model.device if use_gpu and gpu_for_model else None
    downloaded = (MODELS_DIR / "cleanup" / CLEANUP_MODELS[model]["file"]).exists()
    size = "" if downloaded else f" {CLEANUP_MODELS[model]['size_mb'] / 1000:.1f} GB download on first use."
    where = "graphics card" if device else "processor"
    if model == LARGE_MODEL:
        speed = "about half a second" if device else "a few seconds"
        mode = "smart" if settings.get("corrections", True) else "literal"
        what = ("Punctuation, paragraphs, changes of mind." if mode == "smart" else
                "Punctuation and paragraphs, every word kept.")
        name = "Large AI"
    else:
        speed = "under a second"
        what = "Punctuation and capitals only."
        mode = "literal"
        name = "Small AI"
    notes = []
    if pinned in CLEANUP_MODELS:
        notes.append("Model chosen in Advanced.")
    elif device:
        notes.append("Same as Best here." if level == "auto" else "Same as Automatic here.")
    elif level == "best" and model != LARGE_MODEL:
        notes.append("Not enough free memory for the large model.")
    if preference == "gpu" and g is None:
        notes.append("GPU was forced, but that graphics card was not found. Using your processor.")
    elif preference == "gpu" and gpu_for_model is None:
        notes.append("GPU was forced, but it doesn't have enough free memory for this model. Using your processor.")
    elif preference == "cpu":
        notes.append("Processor forced in Advanced.")
    note = (" " + " ".join(notes)) if notes else ""
    return Plan(level, model, mode, device, f"{name} on your {where}, {speed}. {what}{size}{note}")
