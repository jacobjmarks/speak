"""System output volume control for Windows and macOS."""
import subprocess
import sys
import uuid

SUPPORTED = sys.platform in ("win32", "darwin")


def _windows_volume(volume: float | None = None) -> float:
    import ctypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16), ("Data3", ctypes.c_uint16),
                    ("Data4", ctypes.c_ubyte * 8)]

    def guid(value: str):
        result = GUID()
        ctypes.memmove(ctypes.byref(result), uuid.UUID(value).bytes_le, 16)
        return result

    def check(result: int):
        if result < 0:
            raise OSError(f"Windows audio API failed (0x{result & 0xffffffff:08X})")

    def method(pointer, index: int, result_type, *arg_types):
        table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *arg_types)(table[index])

    ole32 = ctypes.WinDLL("ole32")
    ole32.CoInitialize.argtypes = [ctypes.c_void_p]
    ole32.CoInitialize.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    ole32.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, ctypes.c_uint32,
                                       ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    ole32.CoCreateInstance.restype = ctypes.c_long

    initialized = ole32.CoInitialize(None)
    if initialized < 0 and initialized != -2147417850:  # RPC_E_CHANGED_MODE: already initialized by the caller
        check(initialized)
    enumerator = ctypes.c_void_p()
    device = ctypes.c_void_p()
    endpoint = ctypes.c_void_p()
    try:
        check(ole32.CoCreateInstance(ctypes.byref(guid("BCDE0395-E52F-467C-8E3D-C4579291692E")), None, 23,
                                     ctypes.byref(guid("A95664D2-9614-4F35-A746-DE8DB63617E6")),
                                     ctypes.byref(enumerator)))
        check(method(enumerator, 4, ctypes.c_long, ctypes.c_int, ctypes.c_int,
                     ctypes.POINTER(ctypes.c_void_p))(enumerator, 0, 1, ctypes.byref(device)))
        check(method(device, 3, ctypes.c_long, ctypes.POINTER(GUID), ctypes.c_uint32, ctypes.c_void_p,
                     ctypes.POINTER(ctypes.c_void_p))(
                         device, ctypes.byref(guid("5CDF2C82-841E-4546-9722-0CF74078229A")), 23, None,
                         ctypes.byref(endpoint)))
        if volume is None:
            value = ctypes.c_float()
            check(method(endpoint, 9, ctypes.c_long, ctypes.POINTER(ctypes.c_float))(
                endpoint, ctypes.byref(value)))
            return value.value
        check(method(endpoint, 7, ctypes.c_long, ctypes.c_float, ctypes.c_void_p)(
            endpoint, ctypes.c_float(volume), None))
        return volume
    finally:
        for pointer in (endpoint, device, enumerator):
            if pointer:
                method(pointer, 2, ctypes.c_ulong)(pointer)
        if initialized >= 0:
            ole32.CoUninitialize()


def get_volume() -> float:
    if sys.platform == "darwin":
        result = subprocess.run(
            ["osascript", "-e", "get output volume of (get volume settings)"],
            check=True, capture_output=True, text=True, timeout=3)
        return int(result.stdout.strip()) / 100
    if sys.platform == "win32":
        return _windows_volume()
    raise OSError("System audio dimming is not supported on this platform")


def set_volume(volume: float) -> None:
    volume = min(1.0, max(0.0, volume))
    if sys.platform == "darwin":
        subprocess.run(
            ["osascript", "-e", f"set volume output volume {round(volume * 100)}"],
            check=True, capture_output=True, text=True, timeout=3)
    elif sys.platform == "win32":
        _windows_volume(volume)
    else:
        raise OSError("System audio dimming is not supported on this platform")


def dim(reduction_percent: int) -> tuple[float, float]:
    """Reduce current output volume and return its original and expected dimmed levels."""
    original = get_volume()
    dimmed = original * (1 - reduction_percent / 100)
    set_volume(dimmed)
    if sys.platform == "darwin":
        dimmed = round(dimmed * 100) / 100
    return original, dimmed


def restore(original: float, dimmed: float) -> bool:
    """Restore only if output volume is still at Speak's dimmed level."""
    if abs(get_volume() - dimmed) > 0.001:
        return False
    set_volume(original)
    return True
