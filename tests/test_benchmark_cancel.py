import threading
import unittest
from unittest.mock import Mock, patch

from speak import benchmark
from speak.controller import Dictation, State


def idle_dictation():
    dictation = Dictation.__new__(Dictation)
    dictation._lock = threading.RLock()
    dictation._benchmark_cancel = threading.Event()
    dictation._benchmark_lock = threading.Lock()
    dictation._cancel_unload = lambda: None
    dictation._schedule_unload = Mock()
    dictation.state = State.IDLE
    dictation.settings = {}
    dictation.asr_server = Mock()
    dictation.cleanup_server = Mock()
    return dictation


class BenchmarkCancelTest(unittest.TestCase):
    """Cancelling a speed test stops it and unloads the models it loaded."""

    def test_cancelled_run_unloads_both_servers(self):
        dictation = idle_dictation()

        def run(*args):
            dictation.cancel_benchmark()
            raise benchmark.Cancelled()

        with patch("speak.controller.benchmark.run", side_effect=run):
            with self.assertRaises(benchmark.Cancelled):
                dictation.run_benchmark(b"", 16000, lambda *a: None)

        dictation.asr_server.stop.assert_called_once()
        dictation.cleanup_server.stop.assert_called_once()

    def test_finished_run_keeps_models_loaded_for_the_idle_timer(self):
        dictation = idle_dictation()
        with patch("speak.controller.benchmark.run", return_value="ok"):
            self.assertEqual(dictation.run_benchmark(b"", 16000, lambda *a: None), "ok")

        dictation.asr_server.stop.assert_not_called()
        dictation._schedule_unload.assert_called_once()

    def test_newer_run_supersedes_a_cancelled_one_without_unloading(self):
        dictation = idle_dictation()
        started, release = threading.Event(), threading.Event()
        results = []

        def run(settings, pcm, rate, asr, cleanup, progress, cancelled):
            if not results:
                results.append("first")
                started.set()
                release.wait(2)
                if cancelled():
                    raise benchmark.Cancelled()
            return "second"

        outcome = []

        def first():
            try:
                dictation.run_benchmark(b"", 16000, lambda *a: None)
            except benchmark.Cancelled:
                outcome.append("cancelled")

        with patch("speak.controller.benchmark.run", side_effect=run):
            thread = threading.Thread(target=first)
            thread.start()
            started.wait(2)
            second = threading.Thread(target=lambda: outcome.append(
                dictation.run_benchmark(b"", 16000, lambda *a: None)))
            second.start()
            release.set()
            thread.join(2)
            second.join(2)

        self.assertEqual(sorted(outcome), ["cancelled", "second"])
        dictation.asr_server.stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
