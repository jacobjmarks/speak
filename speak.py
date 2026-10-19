import json
import math
import os
import queue
import socket
import sqlite3
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import winreg
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
import tkinter as tk
import websocket

APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Speak"
SETTINGS_FILE = APP_DIR / "settings.json"
HISTORY_FILE = APP_DIR / "history.sqlite3"
DEFAULTS = {
    "hotkey": "ctrl+shift+space",
    "history_enabled": False,
    "auto_paste": True,
    "overlay_enabled": True,
    "model": "nemotron-3.5",
    "language": "auto",
    "cleanup_enabled": True,
    "cleanup_model": "qwen25-q4km",
    "theme": "System",
}
MODEL_CHOICES = {"Nemotron 3.5 ASR (multilingual)": "nemotron-3.5"}
CLEANUP_MODELS = {
    "Qwen 2.5 0.5B (Q4_K_M, 491 MB)": {
        "id": "qwen25-q4km",
        "repo": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "file": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
    },
    "Qwen 2.5 0.5B (Q8_0, 676 MB)": {
        "id": "qwen25-q8",
        "repo": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "file": "qwen2.5-0.5b-instruct-q8_0.gguf",
    },
}


class SpeakApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Speak")
        self.root.geometry("700x510")
        self.root.minsize(540, 400)
        APP_DIR.mkdir(parents=True, exist_ok=True)
        self.settings = self.load_settings()
        if self.settings["model"] not in MODEL_CHOICES.values():
            self.settings["model"] = DEFAULTS["model"]
        if self.settings["cleanup_model"] not in {model["id"] for model in CLEANUP_MODELS.values()}:
            self.settings["cleanup_model"] = DEFAULTS["cleanup_model"]
        self.status = tk.StringVar(value="Ready")
        self.latest = ""
        self.server_lock = threading.Lock()
        self.websocket_lock = threading.Lock()
        self.audio_stream = None
        self.audio_queue = queue.Queue()
        self.sample_rate = 16000
        self.listening = False
        self.preparing = False
        self.audio_level = 0.0
        self.hotkey_handle = None
        self.overlay = None
        self.overlay_canvas = None
        self.overlay_bars = []
        self.overlay_animation = None
        self.overlay_progress = None
        self.tray_icon = None
        self.runtime_process = None
        self.runtime_log = None
        self.runtime_port = None
        self.runtime_model = None
        self.cleanup_process = None
        self.cleanup_log = None
        self.cleanup_port = None
        self.cleanup_model_id = None
        self.setup_overlay_text = None
        self.active_theme = None
        self.asr_socket = None
        self.sender_thread = None
        self.receiver_thread = None
        self.final_event = None
        self.final_text = ""
        self.partial_text = ""

        self.build_ui()
        self.apply_theme()
        self.root.after(2000, self.poll_system_theme)
        self.register_hotkey()
        self.start_tray()
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

    def load_settings(self):
        try:
            stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            return {**DEFAULTS, **stored}
        except (OSError, json.JSONDecodeError):
            return DEFAULTS.copy()

    def save_settings(self):
        SETTINGS_FILE.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")

    def build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        ttk.Label(self.root, text="Speak", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 4)
        )
        tabs = ttk.Notebook(self.root)
        tabs.grid(row=1, column=0, sticky="nsew", padx=10, pady=6)
        self.dictation_tab = ttk.Frame(tabs, padding=10)
        self.history_tab = ttk.Frame(tabs, padding=10)
        self.settings_tab = ttk.Frame(tabs, padding=10)
        tabs.add(self.dictation_tab, text="Dictation")
        tabs.add(self.history_tab, text="History")
        tabs.add(self.settings_tab, text="Settings")

        self.dictation_tab.columnconfigure(0, weight=1)
        self.dictation_tab.rowconfigure(3, weight=1)
        self.transcript_state = ttk.Label(self.dictation_tab, text="Ready")
        self.transcript_state.grid(row=0, column=0, sticky="w")
        self.setup_progress = ttk.Progressbar(self.dictation_tab, mode="indeterminate")
        actions = ttk.Frame(self.dictation_tab)
        actions.grid(row=2, column=0, sticky="ew", pady=7)
        self.listen_button = ttk.Button(actions, text="Start listening", command=self.toggle_listening)
        self.listen_button.pack(side="left")
        ttk.Button(actions, text="Copy transcript", command=self.copy_latest).pack(side="left", padx=6)
        self.transcript_box = tk.Text(self.dictation_tab, wrap="word", height=12)
        self.transcript_box.grid(row=3, column=0, sticky="nsew")
        ttk.Label(
            self.dictation_tab,
            text="Toggle listening with the hotkey. Transcript stays here if paste is unavailable.",
        ).grid(row=4, column=0, sticky="w", pady=(7, 0))

        self.history_tab.columnconfigure(0, weight=1)
        self.history_tab.rowconfigure(0, weight=1)
        self.history_tree = ttk.Treeview(self.history_tab, columns=("time", "text"), show="headings")
        self.history_tree.heading("time", text="Time")
        self.history_tree.heading("text", text="Transcript")
        self.history_tree.column("time", width=150, stretch=False)
        self.history_tree.column("text", width=420)
        self.history_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(self.history_tab, orient="vertical", command=self.history_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        self.history_count = ttk.Label(self.history_tab, text="History is off")
        self.history_count.grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Button(self.history_tab, text="Clear history", command=self.clear_history).grid(
            row=2, column=0, sticky="w", pady=(6, 0)
        )
        self.hotkey_var = tk.StringVar(value=self.settings["hotkey"])
        self.history_var = tk.BooleanVar(value=self.settings["history_enabled"])
        self.paste_var = tk.BooleanVar(value=self.settings["auto_paste"])
        self.overlay_var = tk.BooleanVar(value=self.settings["overlay_enabled"])
        self.cleanup_var = tk.BooleanVar(value=self.settings["cleanup_enabled"])
        self.theme_var = tk.StringVar(value=self.settings["theme"])
        model_label = next(
            (label for label, model in MODEL_CHOICES.items() if model == self.settings["model"]),
            next(iter(MODEL_CHOICES)),
        )
        self.model_var = tk.StringVar(value=model_label)
        self.language_var = tk.StringVar(value=self.settings["language"])
        self.settings_tab.columnconfigure(1, weight=1)
        ttk.Label(self.settings_tab, text="Toggle hotkey").grid(row=0, column=0, sticky="w", pady=5)
        hotkey_row = ttk.Frame(self.settings_tab)
        hotkey_row.grid(row=0, column=1, sticky="ew", pady=5)
        ttk.Entry(hotkey_row, textvariable=self.hotkey_var, state="readonly").pack(side="left", fill="x", expand=True)
        self.record_hotkey_button = ttk.Button(hotkey_row, text="Record", command=self.capture_hotkey)
        self.record_hotkey_button.pack(side="left", padx=(6, 0))
        ttk.Label(self.settings_tab, text="Speech model").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Combobox(
            self.settings_tab, textvariable=self.model_var, values=tuple(MODEL_CHOICES), state="readonly"
        ).grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Label(self.settings_tab, text="Language (auto or locale, e.g. en-US)").grid(
            row=2, column=0, sticky="w", pady=5
        )
        ttk.Entry(self.settings_tab, textvariable=self.language_var).grid(row=2, column=1, sticky="ew", pady=5)
        ttk.Checkbutton(
            self.settings_tab,
            text="Clean up the complete transcript after speaking",
            variable=self.cleanup_var,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Label(self.settings_tab, text="Cleanup model").grid(row=4, column=0, sticky="w", pady=5)
        cleanup_model_label = next(
            (label for label, model in CLEANUP_MODELS.items() if model["id"] == self.settings["cleanup_model"]),
            next(iter(CLEANUP_MODELS)),
        )
        self.cleanup_model_var = tk.StringVar(value=cleanup_model_label)
        self.cleanup_model_dropdown = ttk.Combobox(
            self.settings_tab,
            textvariable=self.cleanup_model_var,
            values=tuple(CLEANUP_MODELS),
            state="readonly",
        )
        self.cleanup_model_dropdown.grid(row=4, column=1, sticky="ew", pady=5)
        self.cleanup_model_dropdown.configure(state="readonly" if self.cleanup_var.get() else "disabled")
        self.cleanup_var.trace_add(
            "write",
            lambda *_: self.cleanup_model_dropdown.configure(
                state="readonly" if self.cleanup_var.get() else "disabled"
            ),
        )

        ttk.Label(self.settings_tab, text="Theme").grid(row=5, column=0, sticky="w", pady=5)
        self.theme_dropdown = ttk.Combobox(
            self.settings_tab, textvariable=self.theme_var, values=("System", "Light", "Dark"), state="readonly"
        )
        self.theme_dropdown.grid(row=5, column=1, sticky="ew", pady=5)
        self.theme_dropdown.bind("<<ComboboxSelected>>", lambda event: self.apply_theme())
        ttk.Checkbutton(self.settings_tab, text="Track transcript history", variable=self.history_var).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=4
        )
        ttk.Checkbutton(self.settings_tab, text="Paste into the focused app", variable=self.paste_var).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=4
        )
        ttk.Checkbutton(self.settings_tab, text="Show microphone overlay", variable=self.overlay_var).grid(
            row=8, column=0, columnspan=2, sticky="w", pady=4
        )
        ttk.Label(
            self.settings_tab,
            text="Live text is provisional until the final cleanup pass completes.",
            wraplength=400,
        ).grid(row=9, column=1, sticky="w", pady=4)
        ttk.Button(self.settings_tab, text="Save settings", command=self.apply_settings).grid(
            row=10, column=1, sticky="e", pady=10
        )
        self.refresh_history()

    def register_hotkey(self):
        try:
            import keyboard

            if self.hotkey_handle is not None:
                keyboard.remove_hotkey(self.hotkey_handle)
            self.hotkey_handle = keyboard.add_hotkey(
                self.settings["hotkey"], lambda: self.root.after(0, self.toggle_listening)
            )
        except Exception as exc:
            self.status.set(f"Hotkey unavailable: {exc}")

    def start_tray(self):
        try:
            import pystray
            from PIL import Image, ImageDraw

            image = Image.new("RGB", (64, 64), "#245b56")
            ImageDraw.Draw(image).ellipse((12, 12, 52, 52), fill="#f4e7c8")
            menu = pystray.Menu(
                pystray.MenuItem("Show Speak", lambda icon, item: self.root.after(0, self.show_window)),
                pystray.MenuItem("Quit", lambda icon, item: self.root.after(0, self.quit)),
            )
            self.tray_icon = pystray.Icon("Speak", image, "Speak dictation", menu)
            self.tray_icon.run_detached()
        except Exception:
            self.tray_icon = None

    def capture_hotkey(self):
        self.record_hotkey_button.configure(state="disabled", text="Press keys...")
        self.status.set("Press the new shortcut, or Escape to cancel")
        try:
            import keyboard

            if self.hotkey_handle is not None:
                keyboard.remove_hotkey(self.hotkey_handle)
                self.hotkey_handle = None
        except Exception as exc:
            self.record_hotkey_button.configure(state="normal", text="Record")
            self.status.set(f"Hotkey capture unavailable: {exc}")
            return

        def read_hotkey():
            try:
                import keyboard

                hotkey = keyboard.read_hotkey(suppress=True)
                self.root.after(0, lambda: self.finish_hotkey_capture(hotkey))
            except Exception as exc:
                self.root.after(0, lambda error=str(exc): self.finish_hotkey_capture(error=error))

        threading.Thread(target=read_hotkey, daemon=True).start()

    def finish_hotkey_capture(self, hotkey=None, error=None):
        self.record_hotkey_button.configure(state="normal", text="Record")
        if error:
            self.status.set(f"Hotkey capture failed: {error}")
        elif hotkey and hotkey.lower() not in ("esc", "escape"):
            self.hotkey_var.set(hotkey)
            self.settings["hotkey"] = hotkey
            self.save_settings()
            self.status.set(f"Hotkey set to {hotkey}")
        else:
            self.status.set("Hotkey capture cancelled")
        self.register_hotkey()

    def apply_settings(self):
        model = MODEL_CHOICES[self.model_var.get()]
        cleanup_model = CLEANUP_MODELS[self.cleanup_model_var.get()]["id"]
        language = self.language_var.get().strip() or "auto"
        self.settings.update(
            hotkey=self.hotkey_var.get().strip(),
            model=model,
            language=language,
            cleanup_enabled=self.cleanup_var.get(),
            cleanup_model=cleanup_model,
            theme=self.theme_var.get(),
            history_enabled=self.history_var.get(),
            auto_paste=self.paste_var.get(),
            overlay_enabled=self.overlay_var.get(),
        )
        self.save_settings()
        self.register_hotkey()
        self.refresh_history()
        self.apply_theme()
        self.cleanup_model_dropdown.configure(state="readonly" if self.settings["cleanup_enabled"] else "disabled")
        if self.cleanup_model_id != self.settings["cleanup_model"]:
            self.stop_cleanup_runtime()
        self.status.set("Settings saved")

    def system_prefers_light_theme(self):
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return bool(value)
        except OSError:
            return True

    def apply_theme(self):
        mode = self.theme_var.get()
        if mode == "System":
            theme_name = "vista" if self.system_prefers_light_theme() else "clam"
        elif mode == "Light":
            theme_name = "vista"
        else:
            theme_name = "clam"
        style = ttk.Style(self.root)
        if theme_name not in style.theme_names():
            theme_name = "default"
        if style.theme_use() != theme_name:
            style.theme_use(theme_name)
        self.active_theme = theme_name

    def poll_system_theme(self):
        if self.theme_var.get() == "System":
            self.apply_theme()
        self.root.after(2000, self.poll_system_theme)

    def set_transcript(self, text):
        self.transcript_box.delete("1.0", "end")
        if text:
            self.transcript_box.insert("1.0", text)

    def toggle_listening(self):
        if self.preparing:
            return
        if self.listening:
            self.stop_listening()
        else:
            self.start_listening()

    def start_listening(self):
        self.preparing = True
        self.transcript_state.configure(text="Preparing models")
        self.listen_button.configure(state="disabled")
        self.status.set("Preparing local models. First use downloads model weights...")
        self.setup_progress.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.setup_progress.start(12)
        self.show_overlay(preparing=True, message="Preparing speech model...")
        threading.Thread(target=self.prepare_listening, daemon=True).start()

    def prepare_listening(self):
        try:
            import sounddevice as sd

            device = sd.query_devices(kind="input")
            self.sample_rate = int(device["default_samplerate"])
            self.audio_frames = 0
            self.ensure_runtime(self.settings["model"])
            if self.settings["cleanup_enabled"]:
                self.ensure_cleanup_runtime(self.settings["cleanup_model"])
            self.open_asr_socket()
            self.root.after(0, self.begin_capture)
        except Exception as exc:
            self.close_asr_socket()
            self.root.after(0, lambda error=str(exc): self.listening_failed(error))

    def begin_capture(self):
        self.setup_progress.stop()
        self.setup_progress.grid_remove()
        self.hide_overlay()
        self.preparing = False
        self.listen_button.configure(state="normal")
        try:
            import sounddevice as sd

            self.audio_queue = queue.Queue()
            self.sender_thread = threading.Thread(target=self.send_audio, daemon=True)
            self.sender_thread.start()
            self.audio_stream = sd.RawInputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                callback=self.audio_callback,
            )
            self.audio_stream.start()
            self.listening = True
            self.listen_button.configure(text="Stop listening")
            self.transcript_state.configure(text="Listening")
            self.status.set("Listening")
            self.show_overlay()
        except Exception as exc:
            self.listening_failed(f"Could not start microphone: {exc}")

    def audio_callback(self, input_data, frames, timing, status):
        samples = struct.iter_unpack("<h", input_data)
        total = 0
        count = 0
        for (sample,) in samples:
            total += sample * sample
            count += 1
        if count:
            self.audio_level = min(1.0, math.sqrt(total / count) / 3000)
        chunk = bytes(input_data)
        self.audio_frames += frames
        if self.asr_socket is not None:
            self.audio_queue.put(chunk)

    def stop_listening(self):
        self.listening = False
        self.listen_button.configure(text="Start listening")
        self.transcript_state.configure(text="Finalizing")
        self.hide_overlay()
        stream, self.audio_stream = self.audio_stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        if self.audio_frames == 0:
            self.status.set("No audio captured")
            self.close_asr_socket()
            return
        self.status.set("Finalizing transcript...")
        self.audio_queue.put(None)
        threading.Thread(target=self.finish_transcription, daemon=True).start()

    def listening_failed(self, error):
        self.setup_progress.stop()
        self.setup_progress.grid_remove()
        self.preparing = False
        self.listen_button.configure(state="normal", text="Start listening")
        self.transcript_state.configure(text="Ready")
        self.status.set(error)
        self.close_asr_socket()

    def open_asr_socket(self):
        address = f"ws://127.0.0.1:{self.runtime_port}/v1/audio/transcriptions/realtime"
        ws = websocket.create_connection(address, timeout=30, enable_multithread=True)
        try:
            created = json.loads(ws.recv())
            if created.get("type") != "session.created":
                raise RuntimeError(f"Unexpected ASR session response: {created}")
            ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "sample_rate": self.sample_rate,
                    "language": self.settings["language"],
                    "automatic_punctuation": self.settings["cleanup_enabled"],
                },
            }))
            updated = json.loads(ws.recv())
            if updated.get("type") == "error":
                raise RuntimeError(updated.get("error", {}).get("message", "ASR session rejected settings"))
            if updated.get("type") != "session.updated":
                raise RuntimeError(f"Unexpected ASR settings response: {updated}")
        except Exception:
            ws.close()
            raise
        ws.settimeout(None)
        with self.websocket_lock:
            self.asr_socket = ws
            self.final_text = ""
            self.partial_text = ""
            self.final_event = threading.Event()
        self.receiver_thread = threading.Thread(target=self.receive_asr_events, args=(ws,), daemon=True)
        self.receiver_thread.start()

    def send_audio(self):
        try:
            while True:
                chunk = self.audio_queue.get()
                if chunk is None:
                    break
                with self.websocket_lock:
                    ws = self.asr_socket
                if ws is None:
                    break
                ws.send_binary(chunk)
        except Exception as exc:
            self.root.after(0, lambda error=str(exc): self.status.set(f"Audio stream failed: {error}"))

    def receive_asr_events(self, ws):
        try:
            while True:
                event = json.loads(ws.recv())
                event_type = event.get("type", "")
                if event_type == "conversation.item.input_audio_transcription.delta":
                    self.partial_text += event.get("delta", "")
                    self.root.after(0, self.update_live_transcript)
                elif event_type == "conversation.item.input_audio_transcription.completed":
                    text = event.get("transcript", event.get("text", self.partial_text)).strip()
                    if text:
                        self.final_text = f"{self.final_text} {text}".strip()
                    self.partial_text = ""
                    self.root.after(0, self.update_live_transcript)
                    if not self.listening:
                        self.final_event.set()
                elif event_type == "error":
                    error = event.get("error", {}).get("message", "Unknown ASR error")
                    self.root.after(0, lambda message=error: self.status.set(f"ASR error: {message}"))
                elif event_type == "session.end":
                    self.final_event.set()
                    break
        except websocket.WebSocketConnectionClosedException:
            pass
        except Exception as exc:
            if self.listening:
                self.root.after(0, lambda error=str(exc): self.status.set(f"ASR stream failed: {error}"))
        finally:
            if self.final_event is not None:
                self.final_event.set()

    def update_live_transcript(self):
        visible = f"{self.final_text} {self.partial_text}".strip()
        self.set_transcript(visible)
        self.latest = visible

    def finish_transcription(self):
        sender = self.sender_thread
        if sender is not None:
            sender.join(timeout=3)
        with self.websocket_lock:
            ws = self.asr_socket
            final_event = self.final_event
        if ws is not None:
            try:
                ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                if final_event is not None:
                    final_event.wait(timeout=15)
            except Exception:
                pass
        text = f"{self.final_text} {self.partial_text}".strip()
        self.close_asr_socket()
        cleanup_error = None
        if text and self.settings["cleanup_enabled"]:
            self.root.after(0, self.show_cleanup_progress)
            try:
                text = self.cleanup_transcript(text)
            except Exception as exc:
                cleanup_error = str(exc)
        self.root.after(0, lambda: self.transcription_complete(text, cleanup_error))

    def show_cleanup_progress(self):
        self.setup_progress.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.setup_progress.start(12)
        self.status.set("Cleaning up complete transcript locally...")

    def close_asr_socket(self):
        with self.websocket_lock:
            ws, self.asr_socket = self.asr_socket, None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def runtime_root(self):
        if getattr(sys, "frozen", False):
            base = Path(sys._MEIPASS)
        else:
            base = Path(__file__).resolve().parent
        root = base / "vendor" / "nemo-speech"
        if not (root / "bin" / "nemo-speech.exe").exists():
            nested = next(root.glob("nemo-speech-*-windows-x86_64-cpu"), None) if root.exists() else None
            if nested is not None:
                root = nested
        return root

    def stop_runtime(self):
        if self.runtime_process is not None and self.runtime_process.poll() is None:
            self.runtime_process.terminate()
            try:
                self.runtime_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.runtime_process.kill()
        self.runtime_process = None
        self.runtime_model = None
        if self.runtime_log is not None:
            self.runtime_log.close()
            self.runtime_log = None

    def ensure_runtime(self, model):
        with self.server_lock:
            if self.runtime_process is not None and self.runtime_process.poll() is not None:
                self.stop_runtime()
            if self.runtime_process is not None and self.runtime_model == model:
                return
            if self.runtime_process is not None:
                self.stop_runtime()

            executable = self.runtime_root() / "bin" / "nemo-speech.exe"
            if not executable.exists():
                raise RuntimeError("Bundled NeMo-Speech.cpp runtime is missing. Run build.ps1 first.")
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = os.environ.copy()
            env["NEMO_SPEECH_MODEL_DIR"] = str(APP_DIR / "models")
            env["PATH"] = str(executable.parent) + os.pathsep + env.get("PATH", "")
            self.runtime_log = (APP_DIR / "runtime.log").open("ab")
            self.runtime_process = subprocess.Popen(
                [
                    str(executable),
                    "serve",
                    "--asr-model",
                    model,
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-ui",
                ],
                cwd=executable.parents[1],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=self.runtime_log,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.runtime_port = port
            self.runtime_model = model
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                if self.runtime_process.poll() is not None:
                    raise RuntimeError("Local ASR runtime exited. See " + str(APP_DIR / "runtime.log"))
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/ready", timeout=2) as response:
                        if response.status == 200:
                            return
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(0.5)
            self.stop_runtime()
            raise TimeoutError("ASR model did not become ready within five minutes.")

    def update_setup_progress(self, message, percent=None):
        def update():
            self.status.set(message)
            if self.setup_overlay_text is not None:
                self.setup_overlay_text.set(message)
            for progress in (self.setup_progress, self.overlay_progress):
                if progress is None:
                    continue
                if percent is None:
                    progress.configure(mode="indeterminate")
                    progress.start(12)
                else:
                    progress.stop()
                    progress.configure(mode="determinate", maximum=100)
                    progress["value"] = percent

        self.root.after(0, update)

    def ensure_cleanup_runtime(self, model_id):
        model_info = next(model for model in CLEANUP_MODELS.values() if model["id"] == model_id)
        model_dir = APP_DIR / "models" / "cleanup"
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / model_info["file"]
        if not model_path.exists() or model_path.stat().st_size < 100_000_000:
            partial_path = model_path.with_suffix(model_path.suffix + ".part")
            url = (
                f"https://huggingface.co/{model_info['repo']}/resolve/main/"
                f"{model_info['file']}?download=true"
            )
            self.update_setup_progress(f"Downloading cleanup model: {model_info['file']}", 0)
            try:
                with urllib.request.urlopen(url, timeout=60) as response, partial_path.open("wb") as output:
                    total = int(response.headers.get("Content-Length", 0))
                    downloaded = 0
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            percent = min(99, int(downloaded * 100 / total))
                            self.update_setup_progress(
                                f"Downloading cleanup model: {percent}%", percent
                            )
                if total and downloaded != total:
                    raise IOError(f"Incomplete model download ({downloaded} of {total} bytes).")
                if downloaded < 100_000_000:
                    raise IOError("Downloaded cleanup model is unexpectedly small.")
                os.replace(partial_path, model_path)
            except Exception:
                partial_path.unlink(missing_ok=True)
                raise

        with self.server_lock:
            if self.cleanup_process is not None and self.cleanup_process.poll() is not None:
                self.stop_cleanup_runtime()
            if self.cleanup_process is not None and self.cleanup_model_id == model_id:
                return
            if self.cleanup_process is not None:
                self.stop_cleanup_runtime()

            executable = self.cleanup_runtime_root() / "llama-server.exe"
            if not executable.exists():
                raise RuntimeError("Bundled llama.cpp cleanup runtime is missing. Run build.ps1 first.")
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = os.environ.copy()
            env["PATH"] = str(executable.parent) + os.pathsep + env.get("PATH", "")
            self.cleanup_log = (APP_DIR / "cleanup-runtime.log").open("ab")
            self.cleanup_process = subprocess.Popen(
                [
                    str(executable),
                    "--model",
                    str(model_path),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--ctx-size",
                    "8192",
                    "--threads",
                    str(max(2, min(8, (os.cpu_count() or 4) - 1))),
                    "--n-gpu-layers",
                    "0",
                    "--jinja",
                    "--reasoning",
                    "off",
                    "--no-ui",
                ],
                cwd=executable.parent,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=self.cleanup_log,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.cleanup_port = port
            self.cleanup_model_id = model_id
            self.update_setup_progress("Loading local cleanup model into memory...")
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                if self.cleanup_process.poll() is not None:
                    raise RuntimeError("Cleanup runtime exited. See " + str(APP_DIR / "cleanup-runtime.log"))
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                        if response.status == 200:
                            return
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(0.5)
            self.stop_cleanup_runtime()
            raise TimeoutError("Cleanup model did not become ready within five minutes.")

    def cleanup_runtime_root(self):
        base = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        return base / "vendor" / "llama-cpp"

    def stop_cleanup_runtime(self):
        if self.cleanup_process is not None and self.cleanup_process.poll() is None:
            self.cleanup_process.terminate()
            try:
                self.cleanup_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.cleanup_process.kill()
        self.cleanup_process = None
        self.cleanup_model_id = None
        if self.cleanup_log is not None:
            self.cleanup_log.close()
            self.cleanup_log = None

    def cleanup_transcript(self, transcript):
        if not transcript.strip():
            return transcript
        self.update_setup_progress("Cleaning up the complete transcript locally...")
        prompt = (
            "Correct punctuation, capitalization, and clear speech-recognition errors in the transcript below. "
            "Preserve the speaker's wording, meaning, tone, names, and language. Do not summarize, rewrite, "
            "answer, or add anything. Return only the corrected transcript.\n\n" + transcript
        )
        payload = json.dumps({
            "model": "local-cleanup",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a conservative speech transcript editor. Follow the user's transcript exactly; make only necessary corrections.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": min(4096, max(256, len(transcript) // 2 + 128)),
            "stream": False,
            "reasoning_effort": "none",
            "chat_template_kwargs": {"enable_thinking": False},
        }).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.cleanup_port}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
        cleaned = result["choices"][0]["message"]["content"].strip()
        return cleaned or transcript

    def transcription_complete(self, text, cleanup_error=None):
        self.setup_progress.stop()
        self.setup_progress.grid_remove()
        if not text:
            self.transcript_state.configure(text="No speech recognized")
            self.status.set("No speech recognized")
            return
        self.latest = text
        self.set_transcript(text)
        self.transcript_state.configure(text="Final transcript")
        self.status.set(
            "Cleanup failed; kept raw transcript" if cleanup_error else
            "Transcript cleaned" if self.settings["cleanup_enabled"] else "Transcript ready"
        )
        self.transcript_state.configure(text="Cleanup failed" if cleanup_error else "Ready")
        if self.settings["history_enabled"]:
            created = datetime.now().astimezone().isoformat(timespec="seconds")
            with sqlite3.connect(HISTORY_FILE) as db:
                db.execute("CREATE TABLE IF NOT EXISTS transcripts (created TEXT, text TEXT)")
                db.execute("INSERT INTO transcripts VALUES (?, ?)", (created, text))
            self.refresh_history()
        if self.settings["auto_paste"]:
            threading.Thread(target=self.paste_latest, args=(text,), daemon=True).start()

    def paste_latest(self, text):
        try:
            import keyboard
            import pyperclip

            previous_clipboard = pyperclip.paste()
            pyperclip.copy(text)
            keyboard.send("ctrl+v")
            time.sleep(0.8)
            if pyperclip.paste() == text:
                pyperclip.copy(previous_clipboard)
            self.root.after(0, lambda: self.status.set("Transcript pasted; copy remains available"))
        except Exception:
            self.root.after(0, lambda: self.status.set("Paste unavailable; transcript remains in Speak"))

    def copy_latest(self):
        if not self.latest:
            self.status.set("No transcript to copy")
            return
        try:
            import pyperclip

            pyperclip.copy(self.latest)
            self.status.set("Transcript copied")
        except Exception as exc:
            self.status.set(f"Clipboard unavailable: {exc}")

    def refresh_history(self):
        for row in self.history_tree.get_children():
            self.history_tree.delete(row)
        if not self.settings["history_enabled"] or not HISTORY_FILE.exists():
            self.history_count.configure(text="History is off" if not self.settings["history_enabled"] else "No saved transcripts")
            return
        with sqlite3.connect(HISTORY_FILE) as db:
            rows = db.execute("SELECT created, text FROM transcripts ORDER BY rowid DESC LIMIT 500").fetchall()
        for created, text in rows:
            self.history_tree.insert("", "end", values=(created, text))
        self.history_count.configure(text=f"{len(rows)} saved transcript{'s' if len(rows) != 1 else ''}")

    def copy_history_selection(self):
        selected = self.history_tree.selection()
        if not selected:
            self.status.set("Select a transcript to copy")
            return
        self.latest = self.history_tree.item(selected[0], "values")[1]
        self.copy_latest()

    def clear_history(self):
        if HISTORY_FILE.exists() and messagebox.askyesno("Clear history", "Delete all saved transcripts?"):
            with sqlite3.connect(HISTORY_FILE) as db:
                db.execute("DELETE FROM transcripts")
            self.refresh_history()

    def show_overlay(self, preparing=False, message=""):
        if not self.settings["overlay_enabled"]:
            return
        self.overlay = tk.Toplevel(self.root)
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.configure(bg="SystemButtonFace")
        if preparing:
            self.setup_overlay_text = tk.StringVar(value=message)
            tk.Label(
                self.overlay,
                textvariable=self.setup_overlay_text,
                fg="SystemButtonText",
                bg="SystemButtonFace",
                font=("Segoe UI", 9),
                padx=10,
                pady=7,
            ).pack()
            self.overlay_progress = ttk.Progressbar(self.overlay, mode="indeterminate", length=200)
            self.overlay_progress.pack(padx=10, pady=(0, 7))
            self.overlay_progress.start(12)
            self.overlay.geometry(f"+{self.root.winfo_pointerx() + 14}+{self.root.winfo_pointery() + 14}")
            return
        self.overlay_canvas = tk.Canvas(self.overlay, width=92, height=20, bg="SystemButtonFace", highlightthickness=0)
        self.overlay_canvas.pack(padx=8, pady=5)
        self.overlay_bars = []
        for index in range(21):
            x = 4 + index * 4
            self.overlay_bars.append(
                self.overlay_canvas.create_line(x, 10, x, 10, fill="SystemHighlight", width=2, capstyle="round")
            )
        self.overlay.geometry(f"+{self.root.winfo_pointerx() + 14}+{self.root.winfo_pointery() + 14}")
        self.animate_overlay()

    def animate_overlay(self):
        if self.overlay_canvas is None:
            return
        level = self.audio_level
        middle = (len(self.overlay_bars) - 1) / 2
        for index, bar in enumerate(self.overlay_bars):
            taper = math.exp(-((index - middle) / 4.5) ** 2)
            pulse = 0.72 + 0.28 * abs(math.sin(time.monotonic() * 8 - index * 0.18))
            half_height = 1 + int(8 * level * taper * pulse)
            x = 4 + index * 4
            self.overlay_canvas.coords(bar, x, 10 - half_height, x, 10 + half_height)
        self.overlay_animation = self.root.after(50, self.animate_overlay)

    def hide_overlay(self):
        if self.overlay_progress is not None:
            self.overlay_progress.stop()
            self.overlay_progress = None
        if self.overlay_animation is not None:
            self.root.after_cancel(self.overlay_animation)
            self.overlay_animation = None
        self.overlay_canvas = None
        self.overlay_bars = []
        self.setup_overlay_text = None
        if self.overlay is not None:
            self.overlay.destroy()
            self.overlay = None

    def hide_window(self):
        self.root.withdraw()

    def show_window(self):
        self.root.deiconify()
        self.root.lift()

    def quit(self):
        self.listening = False
        self.hide_overlay()
        try:
            import keyboard

            if self.hotkey_handle is not None:
                keyboard.remove_hotkey(self.hotkey_handle)
        except Exception:
            pass
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception:
                pass
        self.stop_runtime()
        self.stop_cleanup_runtime()
        self.close_asr_socket()
        if self.tray_icon is not None:
            self.tray_icon.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    SpeakApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
