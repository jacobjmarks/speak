"""Microphone capture with an RMS level meter, and input-device listing.

Devices are stored in settings by *name* (indices change when devices are plugged in). On Windows the DirectSound
host API is used for listing/opening: MME truncates names to 31 characters and WASAPI rejects non-native rates.
"""
import math
import struct
import sys
from typing import Callable, Optional

_SKIP = ("Microsoft Sound Mapper", "Primary Sound Capture Driver")


def _host_api() -> int:
    import sounddevice as sd

    if sys.platform == "win32":
        for index, api in enumerate(sd.query_hostapis()):
            if api["name"] == "Windows DirectSound":
                return index
    return sd.query_devices(kind="input")["hostapi"]


def input_devices(rescan: bool = False) -> list:
    """Names of usable input devices. `rescan` re-reads the OS list (only call while no stream is open)."""
    import sounddevice as sd

    if rescan:
        sd._terminate()
        sd._initialize()
    api = _host_api()
    return [d["name"] for d in sd.query_devices()
            if d["hostapi"] == api and d["max_input_channels"] > 0 and not d["name"].startswith(_SKIP)]


def _resolve(name: Optional[str]):
    """Device index for `name`, or None (system default) if unset or no longer connected."""
    if not name:
        return None
    import sounddevice as sd

    api = _host_api()
    for index, d in enumerate(sd.query_devices()):
        if d["hostapi"] == api and d["max_input_channels"] > 0 and d["name"] == name:
            return index
    return None


class Microphone:
    def __init__(self, on_chunk: Callable[[bytes], None], device_name: Optional[str] = None):
        import sounddevice as sd

        self.on_chunk = on_chunk
        self.level = 0.0
        self.frames = 0
        self.device = _resolve(device_name)
        info = sd.query_devices(self.device, kind="input") if self.device is not None else sd.query_devices(kind="input")
        self.sample_rate = int(info["default_samplerate"])
        self.stream = None

    def start(self):
        import sounddevice as sd

        self.stream = sd.RawInputStream(
            samplerate=self.sample_rate, channels=1, dtype="int16", callback=self._callback, device=self.device
        )
        self.stream.start()

    def stop(self):
        stream, self.stream = self.stream, None
        self.level = 0.0
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    def _callback(self, data, frames, timing, status):
        count = len(data) // 2
        if count:
            total = sum(s * s for (s,) in struct.iter_unpack("<h", data))
            self.level = min(1.0, math.sqrt(total / count) / 3000)
        self.frames += frames
        self.on_chunk(bytes(data))
