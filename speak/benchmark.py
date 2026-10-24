"""Setup test: run recorded audio through the real speech + tidy-up pipeline and time it.

`latency_s` is what users feel: the wait between finishing speaking and the text being ready. Audio is streamed
faster than real time (`STREAM_SPEEDUP`), so most recognition is done by the time the last chunk lands, as in live use.
"""
import time
import wave
from dataclasses import dataclass
from typing import Callable, Optional

from . import cleanup, tidy
from .asr import AsrSession

STREAM_SPEEDUP = 4
CHUNK_SECONDS = 0.1
GOOD_SECONDS = 1.0
OK_SECONDS = 2.5


class Cancelled(Exception):
    pass


@dataclass(frozen=True)
class Result:
    audio_s: float
    load_s: float        # starting the speech/tidy-up models (0 when already loaded)
    transcribe_s: float  # last audio sent -> raw text
    tidy_s: float        # raw text -> final text
    raw: str
    text: str
    plan: tidy.Plan

    @property
    def latency_s(self) -> float:
        return self.transcribe_s + self.tidy_s

    @property
    def verdict(self) -> tuple:
        """(rating, plain-language summary); rating is "good", "ok" or "slow"."""
        seconds = f"{self.latency_s:.1f} seconds" if self.latency_s >= 0.1 else "under a second"
        if self.latency_s <= GOOD_SECONDS:
            return "good", f"Fast: text appears in {seconds} after you stop speaking."
        if self.latency_s <= OK_SECONDS:
            return "ok", f"Good: text appears in {seconds} after you stop speaking."
        return "slow", f"Slow: text takes {seconds} after you stop speaking. Try a lighter tidy-up setting."


def read_wav(path) -> tuple:
    """(16-bit mono PCM bytes, sample rate) from a WAV file."""
    with wave.open(str(path), "rb") as wav:
        if wav.getsampwidth() != 2 or wav.getnchannels() != 1:
            raise ValueError("Sample audio must be 16-bit mono.")
        return wav.readframes(wav.getnframes()), wav.getframerate()


def run(settings: dict, pcm: bytes, rate: int, asr_server, cleanup_server,
        progress: Callable[[str, Optional[float]], None], cancelled: Callable[[], bool] = lambda: False) -> Result:
    def check():
        if cancelled():
            raise Cancelled

    started = time.monotonic()
    tidy._probed.wait(15)
    asr_server.ensure(settings["model"], progress)
    plan = tidy.plan(settings)
    if plan.model_id and cleanup_server.ensure(plan, progress):
        cleanup.warm(cleanup_server.port, plan.llm_mode)
    load_s = time.monotonic() - started
    check()

    progress("Listening to the sample", None)
    session = AsrSession(asr_server.port, rate, settings["language"], True, lambda *_: None, lambda *_: None)
    try:
        step = int(rate * CHUNK_SECONDS) * 2
        for offset in range(0, len(pcm), step):
            check()
            session.send_audio(pcm[offset:offset + step])
            time.sleep(CHUNK_SECONDS / STREAM_SPEEDUP)
        asr_started = time.monotonic()
        raw = session.finish()
        transcribe_s = time.monotonic() - asr_started
    except BaseException:
        session.close()
        raise
    check()

    progress("Tidying up", None)
    port = cleanup_server.port if plan.model_id else None
    tidy_started = time.monotonic()
    text, _ = cleanup.finalize(raw, plan.level, plan.llm_mode, port)
    tidy_s = time.monotonic() - tidy_started
    return Result(len(pcm) / 2 / rate, load_s, transcribe_s, tidy_s, raw, text, plan)
