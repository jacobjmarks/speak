"""OS-specific helpers. Keep every platform branch in this module."""
import functools
import os
import plistlib
import re
import shlex
import ssl
import subprocess
import sys
from pathlib import Path
from typing import Optional

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
TRAY_NAME = "menu bar" if IS_MAC else "system tray"  # what the OS calls the status-icon area


def app_data_dir() -> Path:
    if IS_WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Speak"
    if IS_MAC:
        return Path.home() / "Library" / "Application Support" / "Speak"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "speak"


def exe_name(name: str) -> str:
    return f"{name}.exe" if IS_WINDOWS else name


def bundle_root() -> Path:
    """Directory containing `vendor/` (PyInstaller temp dir when frozen, else the repo root)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def sample_audio_file() -> Path:
    """Bundled recording used by first-run setup to time dictation."""
    return bundle_root() / "assets" / "onboarding-sample.wav"


def notices_file() -> Path:
    """Bundled third-party notices; in source runs, the copy build.ps1 generates under build/."""
    root = bundle_root()
    return root / "THIRD_PARTY_NOTICES.txt" if getattr(sys, "frozen", False) else root / "build" / "THIRD_PARTY_NOTICES.txt"


def hidden_process_kwargs() -> dict:
    if IS_WINDOWS:
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}


@functools.cache
def https_context() -> ssl.SSLContext:
    """TLS context that verifies against the OS trust store (Keychain, Windows store, Linux CA paths).

    Python's default context can't read the macOS Keychain, so every HTTPS request failed in the packaged Mac app;
    a bundled CA list (certifi) would instead miss roots added by the user or their organisation.
    """
    import truststore  # lazy: a load failure then only affects HTTPS requests, not startup
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


_job = None


def tie_to_app(process: subprocess.Popen) -> None:
    """Make a child process die with Speak, even if Speak crashes or is killed (Windows job object).

    Elsewhere, ManagedServer.stop() on normal exit is relied on. Best effort.
    """
    global _job
    if not IS_WINDOWS:
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        if _job is None:
            class Basic(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                            ("SchedulingClass", wintypes.DWORD)]

            class Extended(ctypes.Structure):
                _fields_ = [("Basic", Basic), ("IoInfo", ctypes.c_ulonglong * 6),
                            ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                            ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

            kernel32.CreateJobObjectW.restype = wintypes.HANDLE
            job = kernel32.CreateJobObjectW(None, None)
            info = Extended()
            info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel32.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(info), ctypes.sizeof(info)):
                return
            _job = job  # handle intentionally kept open for the app's lifetime
        kernel32.AssignProcessToJobObject(wintypes.HANDLE(_job), wintypes.HANDLE(process._handle))
    except Exception:
        pass


_NOT_TEXT = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}  # desktop, taskbar


def foreground_window():
    """Opaque id of the focused top-level window, or None if unknown, unsupported, or not a typing target
    (desktop, taskbar, Speak itself). Windows only for now."""
    if not IS_WINDOWS:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        name = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, name, 64)
        if pid.value == os.getpid() or name.value in _NOT_TEXT:
            return None
        return hwnd
    except Exception:
        return None


def keep_visible_when_inactive(window_id: int) -> None:
    """macOS: let a floating window stay up while another app is frontmost, on every Space and over full-screen apps."""
    if not IS_MAC:
        return
    try:
        import objc

        window = objc.objc_object(c_void_p=window_id).window()
        window.setHidesOnDeactivate_(False)
        window.setHasShadow_(False)  # the overlay paints its own soft shadow; the native one shows as a hard frame
        window.setCollectionBehavior_((1 << 0) | (1 << 8))  # canJoinAllSpaces | fullScreenAuxiliary
    except Exception:
        pass


def hide_title_text(window_id: int) -> None:
    """macOS: keep the window's title (Dock, Window menu) but don't draw it in the title bar."""
    if not IS_MAC:
        return
    try:
        import objc

        objc.objc_object(c_void_p=window_id).window().setTitleVisibility_(1)  # NSWindowTitleHidden
    except Exception:
        pass


def system_app_icon_png(px: int) -> bytes | None:
    """macOS app bundle: our icon as the system draws it (Dock, Finder), `px` square PNG. None elsewhere."""
    if not (IS_MAC and getattr(sys, "frozen", False)):
        return None
    try:
        from AppKit import NSBitmapImageRep, NSCompositingOperationCopy, NSGraphicsContext, NSWorkspace

        image = NSWorkspace.sharedWorkspace().iconForFile_(str(Path(sys.executable).resolve().parents[2]))
        rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(  # noqa: E501
            None, px, px, 8, 4, True, False, "NSDeviceRGBColorSpace", 0, 0)
        NSGraphicsContext.saveGraphicsState()
        try:
            NSGraphicsContext.setCurrentContext_(NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep))
            image.drawInRect_fromRect_operation_fraction_(((0, 0), (px, px)), ((0, 0), (0, 0)),
                                                          NSCompositingOperationCopy, 1.0)
        finally:
            NSGraphicsContext.restoreGraphicsState()
        return bytes(rep.representationUsingType_properties_(4, None))  # 4: PNG
    except Exception:
        return None


def paste_shortcut() -> str:
    return "cmd+v" if IS_MAC else "ctrl+v"


def available_memory_mb() -> int:
    """Free physical memory in MiB (best effort; 0 if unknown)."""
    try:
        if IS_WINDOWS:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(MemoryStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return status.ullAvailPhys // 2**20
        if IS_MAC:
            total = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout)
            return total // 2 // 2**20  # macOS has no cheap "available"; assume half is usable
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_AVPHYS_PAGES") // 2**20
    except Exception:
        return 0


def _launch_command() -> list:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(Path(__file__).resolve().parent.parent / "main.py")]


def _autostart_file() -> Path:
    if IS_MAC:
        return Path.home() / "Library" / "LaunchAgents" / "com.speak.app.plist"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / "speak.desktop"


_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
# Task Manager's Startup tab records "disabled" here; the Run value itself stays
_APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"


def _desktop_arg(arg: str) -> str:
    """Quote one argument for a freedesktop `Exec=` line."""
    if not re.search(r"[\s\"'\\$`]", arg):
        return arg
    return '"' + re.sub(r'(["`$\\])', r"\\\1", arg) + '"'


def _login_target() -> Optional[Path]:
    """The exe/script the login entry launches, or None if there is no (readable) entry."""
    try:
        if IS_WINDOWS:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                command = winreg.QueryValueEx(key, "Speak")[0]
            return Path(command[1:].split('"', 1)[0] if command.startswith('"') else command.split()[0])
        if IS_MAC:
            return Path(plistlib.loads(_autostart_file().read_bytes())["ProgramArguments"][0])
        for line in _autostart_file().read_text(encoding="utf-8").splitlines():
            if line.startswith("Exec="):
                return Path(shlex.split(line[5:])[0])
    except (OSError, ValueError, KeyError, IndexError, plistlib.InvalidFileException):
        pass
    return None


def _write_login_entry(command: list) -> None:
    if IS_WINDOWS:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "Speak", 0, winreg.REG_SZ, subprocess.list2cmdline(command))
        return
    path = _autostart_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    if IS_MAC:
        path.write_bytes(plistlib.dumps({"Label": "com.speak.app", "ProgramArguments": command, "RunAtLoad": True}))
    else:
        exec_line = " ".join(_desktop_arg(arg) for arg in command)
        path.write_text(f"[Desktop Entry]\nType=Application\nName=Speak\nExec={exec_line}\n", encoding="utf-8")


def launch_at_login_enabled() -> bool:
    """True if Speak will really start at login (on Windows, not switched off in Task Manager's Startup tab)."""
    if IS_WINDOWS:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                winreg.QueryValueEx(key, "Speak")
        except OSError:
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _APPROVED_KEY) as key:
                state = winreg.QueryValueEx(key, "Speak")[0]
            return not (isinstance(state, bytes) and state and state[0] & 1)
        except OSError:
            return True
    return _autostart_file().exists()


def set_launch_at_login(enabled: bool) -> None:
    if IS_WINDOWS:
        import winreg

        if not enabled:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, "Speak")
            except OSError:
                pass
            return
        _write_login_entry(_launch_command() + ["--background"])
        try:  # clear a "disabled" mark from Task Manager, or Windows would ignore the new entry
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _APPROVED_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, "Speak")
        except OSError:
            pass
    elif enabled:
        _write_login_entry(_launch_command() + ["--background"])
    else:
        _autostart_file().unlink(missing_ok=True)


def refresh_launch_at_login() -> None:
    """Packaged app: if the login entry points at an exe that is gone (moved or renamed), point it at this one.

    Runs on each start, so relocating the exe heals the entry the next time it is launched by hand. It never
    touches an entry whose target still exists (another copy owns it) or an entry the user switched off.
    """
    target = _login_target()
    if getattr(sys, "frozen", False) and target and not target.exists():
        _write_login_entry(_launch_command() + ["--background"])


def repoint_launch_at_login(old: Path, new: Path) -> None:
    """If the login entry launches `old`, launch `new` instead (an update installed under a new name)."""
    target = _login_target()
    if target and os.path.normcase(target) == os.path.normcase(old):
        _write_login_entry([str(new), "--background"])


def relaunch() -> None:
    """Start a fresh copy of Speak (macOS permission changes only apply to a new process); the caller then quits."""
    args = ["--restarted"]
    if getattr(sys, "frozen", False) and IS_MAC:
        bundle = Path(sys.executable).resolve().parents[2]
        subprocess.Popen(["open", "-n", str(bundle), "--args", *args])
    else:
        subprocess.Popen([*_launch_command(), *args], start_new_session=True)


def open_path(path: Path) -> None:
    if IS_WINDOWS:
        os.startfile(path)  # noqa: S606
    elif IS_MAC:
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
