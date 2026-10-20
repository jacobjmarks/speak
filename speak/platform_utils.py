"""OS-specific helpers. Keep every platform branch in this module."""
import os
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


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


def hidden_process_kwargs() -> dict:
    if IS_WINDOWS:
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}


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


def launch_at_login_enabled() -> bool:
    if IS_WINDOWS:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
                winreg.QueryValueEx(key, "Speak")
            return True
        except OSError:
            return False
    return _autostart_file().exists()


def set_launch_at_login(enabled: bool) -> None:
    command = _launch_command() + ["--background"]
    if IS_WINDOWS:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, "Speak", 0, winreg.REG_SZ, subprocess.list2cmdline(command))
            else:
                try:
                    winreg.DeleteValue(key, "Speak")
                except OSError:
                    pass
        return
    path = _autostart_file()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if IS_MAC:
        args = "".join(f"<string>{arg}</string>" for arg in command)
        path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict>'
            f"<key>Label</key><string>com.speak.app</string><key>ProgramArguments</key><array>{args}</array>"
            "<key>RunAtLoad</key><true/></dict></plist>\n",
            encoding="utf-8",
        )
    else:
        path.write_text(f"[Desktop Entry]\nType=Application\nName=Speak\nExec={' '.join(command)}\n", encoding="utf-8")


def open_path(path: Path) -> None:
    if IS_WINDOWS:
        os.startfile(path)  # noqa: S606
    elif IS_MAC:
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
