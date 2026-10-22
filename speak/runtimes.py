"""Lifecycle of the bundled local inference servers (NeMo-Speech ASR, llama.cpp cleanup)."""
import os
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from .config import ASR_LOG, CLEANUP_LOG, CLEANUP_MODELS, MODELS_DIR
from .platform_utils import bundle_root, exe_name, hidden_process_kwargs, tie_to_app

# progress(message, percent_or_None)
Progress = Callable[[str, Optional[int]], None]


MODEL_HOST = "https://huggingface.co"
DOWNLOAD_HINT = "Check your internet connection and try again."


class ModelDownloadError(RuntimeError):
    """A model could not be downloaded; the message is meant for the user."""


def _asr_model_cached() -> bool:
    return any("cleanup" not in p.parts for p in MODELS_DIR.rglob("*.gguf"))


def check_model_host() -> None:
    """Fail fast, with a readable message, when the model host is unreachable (downloads otherwise retry for minutes)."""
    try:
        request = urllib.request.Request(MODEL_HOST, method="HEAD")
        with urllib.request.urlopen(request, timeout=10):
            pass
    except Exception as exc:
        raise ModelDownloadError(f"Speak couldn't reach the internet to download its speech model. {DOWNLOAD_HINT}") from exc


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ManagedServer:
    """A local HTTP server subprocess that Speak owns, keyed by the model it serves."""

    def __init__(self, name: str, log_path: Path, ready_path: str):
        self.name = name
        self.log_path = log_path
        self.ready_path = ready_path
        self.process = None
        self.log = None
        self.port = None
        self.key = None
        self.lock = threading.Lock()

    def running(self, key) -> bool:
        return self.process is not None and self.process.poll() is None and self.key == key

    def start(self, key, executable: Path, args: list, cwd: Path, env: dict, timeout: float = 300,
              on_wait: Optional[Callable[[str], None]] = None) -> bool:
        """Start the server for `key` unless already running. Returns True if a new process was started.

        `on_wait` gets the server's output so far on every readiness poll.
        """
        with self.lock:
            if self.running(key):
                return False
            self._stop_locked()
            if not executable.exists():
                raise RuntimeError(f"Bundled {self.name} runtime is missing ({executable}). Run the build script first.")
            port = free_port()
            full_env = {**os.environ, **env}
            full_env["PATH"] = str(executable.parent) + os.pathsep + full_env.get("PATH", "")
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log = self.log_path.open("ab")
            log_start = self.log.tell()
            self.process = subprocess.Popen(
                [str(executable), *args, "--host", "127.0.0.1", "--port", str(port)],
                cwd=cwd,
                env=full_env,
                stdin=subprocess.DEVNULL,
                stdout=self.log,
                stderr=subprocess.STDOUT,
                **hidden_process_kwargs(),
            )
            tie_to_app(self.process)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise self._exit_error(log_start)
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}{self.ready_path}", timeout=2) as response:
                        if response.status == 200:
                            self.port, self.key = port, key  # only now visible to running()
                            return True
                except (OSError, urllib.error.URLError):
                    pass
                if on_wait is not None:
                    on_wait(self._output_since(log_start))
                time.sleep(0.5)
            self._stop_locked()
            raise TimeoutError(f"{self.name} did not become ready within {int(timeout)} seconds.")

    def _output_since(self, log_start: int) -> str:
        try:
            with self.log_path.open("rb") as log:
                log.seek(log_start)
                return log.read().decode("utf-8", "replace")
        except OSError:
            return ""

    def _exit_error(self, log_start: int) -> RuntimeError:
        output = self._output_since(log_start)
        lowered = output.lower()
        if "downloading" in lowered and ("curl failed" in lowered or "download failed" in lowered):
            return ModelDownloadError(f"Speak couldn't download its speech model. {DOWNLOAD_HINT}")
        return RuntimeError(f"{self.name} runtime exited. See {self.log_path}")

    def stop(self):
        with self.lock:
            self._stop_locked()

    def _stop_locked(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
        self.key = None
        if self.log is not None:
            self.log.close()
            self.log = None


def asr_root() -> Path:
    root = bundle_root() / "vendor" / "nemo-speech"
    if not (root / "bin" / exe_name("nemo-speech")).exists() and root.exists():
        nested = next(root.glob("nemo-speech-*"), None)
        if nested is not None:
            root = nested
    return root


def llama_root() -> Path:
    root = bundle_root() / "vendor" / "llama-cpp"
    if not (root / exe_name("llama-server")).exists() and (root / "bin").exists():
        root = root / "bin"
    return root


class AsrServer(ManagedServer):
    def __init__(self):
        super().__init__("NeMo-Speech ASR", ASR_LOG, "/ready")

    def ensure(self, model: str, progress: Progress):
        if self.running(model):
            return
        progress("Getting ready", None)
        if not _asr_model_cached():
            check_model_host()
        root = asr_root()
        executable = root / "bin" / exe_name("nemo-speech")

        def on_wait(output: str):
            total = re.findall(r"\(asr, ([\d.]+) MiB\)", output)
            partial = next((p for p in MODELS_DIR.rglob("*.partial") if "cleanup" not in p.parts), None)
            if total and partial is not None:
                done = partial.stat().st_size / 2**20
                progress("Downloading", min(99, int(done * 100 / float(total[-1]))))

        self.start(
            model,
            executable,
            # Max lookahead: words judged with ~0.25 s of what follows. Better accuracy on clean speech,
            # same finish time; live text updates every 320 ms instead of 160 ms.
            ["serve", "--asr-model", model, "--no-ui", "--asr.streaming.rnnt_right_context=-1"],
            cwd=root,
            env={"NEMO_SPEECH_MODEL_DIR": str(MODELS_DIR)},
            on_wait=on_wait,
        )


class CleanupServer(ManagedServer):
    def __init__(self):
        super().__init__("llama.cpp cleanup", CLEANUP_LOG, "/health")

    def ensure(self, plan, progress: Progress) -> bool:
        """Start (or restart) the server for `plan` (a tidy.Plan). Returns True if it was (re)started."""
        if self.running(plan.key):
            return False
        model_path = download_cleanup_model(plan.model_id, progress)
        progress("Getting ready", None)
        executable = llama_root() / exe_name("llama-server")
        threads = max(2, min(8, (os.cpu_count() or 4) - 1))
        device = ["--device", plan.device, "--n-gpu-layers", "99"] if plan.device else \
            ["--device", "none", "--n-gpu-layers", "0"]
        return self.start(
            plan.key,
            executable,
            [
                "--model", str(model_path),
                "--ctx-size", "4096",
                "--parallel", "1",
                "--threads", str(threads),
                *device,
                "--jinja",
                "--reasoning", "off",
                "--no-ui",
            ],
            cwd=executable.parent,
            env={},
        )

def download_cleanup_model(model_id: str, progress: Progress) -> Path:
    info = CLEANUP_MODELS[model_id]
    model_dir = MODELS_DIR / "cleanup"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / info["file"]
    if model_path.exists() and model_path.stat().st_size >= 100_000_000:
        return model_path
    partial = model_path.with_suffix(model_path.suffix + ".part")
    url = f"https://huggingface.co/{info['repo']}/resolve/main/{info['file']}?download=true"
    progress("Downloading", 0)
    try:
        with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as output:
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                downloaded += len(chunk)
                if total:
                    progress("Downloading", min(99, downloaded * 100 // total))
        if total and downloaded != total:
            raise IOError(f"Incomplete model download ({downloaded} of {total} bytes).")
        if downloaded < 100_000_000:
            raise IOError("Downloaded cleanup model is unexpectedly small.")
        os.replace(partial, model_path)
    except Exception as exc:
        partial.unlink(missing_ok=True)
        raise ModelDownloadError(f"Speak couldn't download its tidy-up model. {DOWNLOAD_HINT}") from exc
    return model_path
