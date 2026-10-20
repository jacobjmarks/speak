"""Microphone capture with an RMS level meter."""
import math
import struct
from typing import Callable


class Microphone:
    def __init__(self, on_chunk: Callable[[bytes], None]):
        import sounddevice as sd

        self.on_chunk = on_chunk
        self.level = 0.0
        self.frames = 0
        self.sample_rate = int(sd.query_devices(kind="input")["default_samplerate"])
        self.stream = None

    def start(self):
        import sounddevice as sd

        self.stream = sd.RawInputStream(
            samplerate=self.sample_rate, channels=1, dtype="int16", callback=self._callback
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
