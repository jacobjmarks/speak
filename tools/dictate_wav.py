"""Dev tool: run a 16-bit mono WAV through the real ASR + cleanup pipeline without the UI.

    python -m tools.dictate_wav path/to/file.wav [--mode smart,literal] [--model qwen25-q4km]
"""
import argparse
import time
import wave

from speak import cleanup
from speak.asr import AsrSession
from speak.config import cleanup_model_id, load_settings
from speak.runtimes import AsrServer, CleanupServer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("wav")
    parser.add_argument("--mode", default=None, help="cleanup mode(s), comma separated")
    parser.add_argument("--model", default=None, help="cleanup model id(s), comma separated")
    args = parser.parse_args()
    settings = load_settings()
    progress = lambda message, percent: print(f"  .. {message} {percent if percent is not None else ''}")

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

        for model in (args.model or cleanup_model_id(settings)).split(","):
            llm.ensure(model, progress)
            for mode in (args.mode or ",".join(cleanup.SYSTEM_PROMPTS)).split(","):
                started = time.monotonic()
                result, note = cleanup.finalize(raw, mode, llm.port)
                print(f"--- {model} {mode} ({time.monotonic() - started:.1f}s) {note}:\n{result}")
    finally:
        asr.stop()
        llm.stop()


if __name__ == "__main__":
    main()
