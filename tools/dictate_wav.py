"""Dev tool: run a 16-bit mono WAV through the real ASR + tidy pipeline without the UI.

    python -m tools.dictate_wav path/to/file.wav [--tidy fast,auto,best] [--cpu]

Prints the plan per level (model, device) and warm timings (the model is warmed before timing).
"""
import argparse
import dataclasses
import time
import wave

from speak import cleanup, tidy
from speak.asr import AsrSession
from speak.config import load_settings
from speak.platform_utils import exe_name
from speak.runtimes import AsrServer, CleanupServer, llama_root


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("wav")
    parser.add_argument("--tidy", default="off,fast,auto,best", help="tidy level(s), comma separated")
    parser.add_argument("--cpu", action="store_true", help="ignore the GPU")
    args = parser.parse_args()
    settings = load_settings()
    progress = lambda message, percent: print(f"  .. {message} {percent if percent is not None else ''}")
    tidy.probe(llama_root() / exe_name("llama-server"))
    if args.cpu:
        tidy._gpu = None
    print(f"GPU: {tidy.gpu()}")

    asr, llm = AsrServer(), CleanupServer()
    try:
        asr.ensure(settings["model"], progress)
        with wave.open(args.wav, "rb") as wav:
            assert wav.getsampwidth() == 2 and wav.getnchannels() == 1, "need 16-bit mono"
            rate, audio = wav.getframerate(), wav.readframes(wav.getnframes())
        session = AsrSession(asr.port, rate, settings["language"], True, lambda *_: None, print)
        step = rate // 10 * 2
        for offset in range(0, len(audio), step):
            session.send_audio(audio[offset:offset + step])
            time.sleep(0.02)
        raw = session.finish()
        print(f"RAW: {raw}")

        for level in args.tidy.split(","):
            plan = tidy.plan({**settings, "tidy": level})
            port = None
            if plan.model_id:
                if llm.ensure(plan, progress):
                    cleanup.warm(llm.port, plan.llm_mode)
                port = llm.port
            started = time.monotonic()
            result, note = cleanup.finalize(raw, plan.level, plan.llm_mode, port)
            details = {k: v for k, v in dataclasses.asdict(plan).items() if k != "summary"}
            print(f"--- {details} ({time.monotonic() - started:.2f}s) {note}\n    {plan.summary}\n{result}")
    finally:
        asr.stop()
        llm.stop()


if __name__ == "__main__":
    main()
