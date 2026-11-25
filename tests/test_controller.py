import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from speak import cleanup, tidy
from speak.controller import TIDY_UNAVAILABLE, Dictation, State


def dictation_for_processing():
    dictation = Dictation.__new__(Dictation)
    dictation._lock = threading.RLock()
    dictation._cancel_event = threading.Event()
    dictation._cancelled = False
    dictation._cancel_error = False
    dictation._cleanup_retry_at = 0.0
    dictation._schedule_unload = lambda: None
    dictation.state = State.PROCESSING
    dictation.listener = Mock()
    dictation.settings = {"history_enabled": False, "auto_paste": True, "press_enter": True, "press_enter_before": False}
    dictation._target = 123
    return dictation


class DictationFlowTest(unittest.TestCase):
    """Dictation completion, silence, and cancellation report the right result and side effects."""

    def test_cancel_before_processing_discards_transcript(self):
        dictation = dictation_for_processing()
        dictation.mic = Mock(frames=10)
        session = dictation.session = Mock()
        dictation.cancel()
        with patch("speak.controller.output.paste") as paste, patch.object(cleanup, "finalize") as finalize:
            dictation._process()

        session.close.assert_called_once()
        session.finish.assert_not_called()
        finalize.assert_not_called()
        paste.assert_not_called()
        dictation.listener.on_cancelled.assert_called_once()
        dictation.listener.on_result.assert_not_called()
        self.assertEqual(dictation.state, State.IDLE)

    def test_successful_processing_cleans_records_and_pastes_the_transcript(self):
        dictation = dictation_for_processing()
        dictation.mic = Mock(frames=10)
        session = dictation.session = Mock()
        session.finish.return_value = "um the the answer is 42 exclamation mark"
        dictation.settings.update(history_enabled=True, press_enter=True)
        plan = SimpleNamespace(model_id=None, level="fast", llm_mode="literal")
        events = []

        def paste(text, should_enter, should_enter_before):
            events.append(("paste", text, should_enter()))

        with patch.object(tidy, "plan", return_value=plan), \
                patch("speak.controller.history.add", side_effect=lambda text: events.append(("history", text))), \
                patch("speak.controller.output.paste", side_effect=paste), \
                patch("speak.controller.platform_utils.foreground_window", return_value=dictation._target):
            dictation._process()

        expected = "The answer is 42!"
        self.assertEqual([("history", expected), ("paste", expected, True)], events)
        session.finish.assert_called_once()
        dictation.listener.on_result.assert_called_once_with(expected, "")
        dictation.listener.on_error.assert_not_called()
        dictation.listener.on_cancelled.assert_not_called()
        self.assertEqual(dictation.state, State.IDLE)

    def test_silence_reports_a_microphone_error_without_finishing_or_pasting(self):
        dictation = dictation_for_processing()
        dictation.mic = Mock(frames=0)
        session = dictation.session = Mock()

        with patch("speak.controller.output.paste") as paste:
            dictation._process()

        session.close.assert_called_once()
        session.finish.assert_not_called()
        dictation.listener.on_error.assert_called_once_with(
            "Speak didn't hear anything. Check that your microphone is working."
        )
        paste.assert_not_called()
        dictation.listener.on_result.assert_not_called()
        self.assertEqual(dictation.state, State.IDLE)

    def test_cancel_during_paste_prevents_enter_and_success_result(self):
        dictation = dictation_for_processing()
        dictation.mic = Mock(frames=1)
        dictation.session = Mock()
        dictation.session.finish.return_value = "recognized words"
        plan = SimpleNamespace(model_id=None, level="off", llm_mode="off")
        enter_checks = []

        def paste(text, should_enter, should_enter_before):
            self.assertEqual(text, "recognized words")
            dictation._cancel_event.set()
            enter_checks.append(should_enter())

        with patch.object(tidy, "plan", return_value=plan), \
                patch.object(cleanup, "finalize", return_value=("recognized words", "")), \
                patch("speak.controller.output.paste", side_effect=paste):
            dictation._process()

        self.assertEqual(enter_checks, [False])
        dictation.listener.on_cancelled.assert_called_once()
        dictation.listener.on_result.assert_not_called()
        self.assertEqual(dictation.state, State.IDLE)

    def test_enter_before_paste_requires_the_target_app_to_still_be_in_front(self):
        dictation = dictation_for_processing()
        dictation.settings.update(press_enter=False, press_enter_before=True)
        plan = SimpleNamespace(model_id=None, level="off", llm_mode="off")
        checks = []

        def paste(text, should_enter, should_enter_before):
            checks.append(should_enter_before())

        for foreground in (dictation._target, 999):
            dictation.mic = Mock(frames=1)
            dictation.session = Mock()
            dictation.session.finish.return_value = "recognized words"
            with patch.object(tidy, "plan", return_value=plan), \
                    patch.object(cleanup, "finalize", return_value=("recognized words", "")), \
                    patch("speak.controller.output.paste", side_effect=paste), \
                    patch("speak.controller.platform_utils.foreground_window", return_value=foreground):
                dictation._process()

        self.assertEqual([True, False], checks)

    def test_history_failure_does_not_stop_the_paste(self):
        dictation = dictation_for_processing()
        dictation.mic = Mock(frames=1)
        dictation.session = Mock()
        dictation.session.finish.return_value = "recognized words"
        dictation.settings["history_enabled"] = True
        plan = SimpleNamespace(model_id=None, level="off", llm_mode="off")

        with patch.object(tidy, "plan", return_value=plan), \
                patch.object(cleanup, "finalize", return_value=("recognized words", "")), \
                patch("speak.controller.history.add", side_effect=sqlite3.OperationalError("database is locked")), \
                patch("speak.controller.output.paste") as paste:
            dictation._process()

        paste.assert_called_once()
        dictation.listener.on_result.assert_called_once_with("recognized words", "")
        dictation.listener.on_error.assert_not_called()

    def test_tidy_up_server_failure_is_logged_and_pastes_rule_based_text(self):
        dictation = dictation_for_processing()
        dictation.mic = Mock(frames=1)
        dictation.session = Mock()
        dictation.session.finish.return_value = "um hello there"
        plan = SimpleNamespace(model_id="qwen25-q4km", level="auto", llm_mode="literal", device=None)

        with patch.object(tidy, "plan", return_value=plan), \
                patch.object(dictation, "_ensure_cleanup", side_effect=RuntimeError("server exited")), \
                patch("speak.controller.output.paste"), \
                self.assertLogs("speak.controller", "WARNING"):
            dictation._process()

        dictation.listener.on_result.assert_called_once_with("Hello there", TIDY_UNAVAILABLE)

    def test_paste_does_not_hold_the_dictation_lock(self):
        dictation = dictation_for_processing()
        dictation.mic = Mock(frames=1)
        dictation.session = Mock()
        dictation.session.finish.return_value = "recognized words"
        plan = SimpleNamespace(model_id=None, level="off", llm_mode="off")
        pasting, release = threading.Event(), threading.Event()

        def paste(text, should_enter, should_enter_before):
            pasting.set()
            release.wait(5)

        with patch.object(tidy, "plan", return_value=plan), \
                patch.object(cleanup, "finalize", return_value=("recognized words", "")), \
                patch("speak.controller.output.paste", side_effect=paste):
            worker = threading.Thread(target=dictation._process)
            worker.start()
            self.assertTrue(pasting.wait(5))
            lock_free = dictation._lock.acquire(timeout=1)
            if lock_free:
                dictation._lock.release()
            release.set()
            worker.join(5)

        self.assertTrue(lock_free)
        dictation.listener.on_result.assert_called_once_with("recognized words", "")


class RuntimeStartupTest(unittest.TestCase):
    """Listening only waits for the speech runtime; an already-downloaded tidy-up model loads in the background."""

    def setUp(self):
        models = tempfile.TemporaryDirectory()
        self.addCleanup(models.cleanup)
        self.models = Path(models.name)
        (self.models / "cleanup").mkdir()
        patches = [
            patch("speak.controller.MODELS_DIR", self.models),
            patch("speak.controller.CLEANUP_MODELS", {"tidy": {"file": "tidy.gguf"}}),
            patch.object(tidy, "probe"),
            patch.object(tidy, "_probed"),
            patch("speak.controller.Microphone"),
            patch("speak.controller.AsrSession"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.plan = SimpleNamespace(model_id="tidy")
        plan_patch = patch.object(tidy, "plan", return_value=self.plan)
        plan_patch.start()
        self.addCleanup(plan_patch.stop)
        self.dictation = Dictation({"model": "asr", "mic_device": "", "language": "en", "audio_dim_enabled": False,
                                    "unload_after": "never"}, Mock())
        self.dictation.asr_server = Mock(port=1)

    def cache_tidy_model(self):
        (self.models / "cleanup" / "tidy.gguf").touch()

    def test_listening_starts_while_a_downloaded_tidy_model_is_still_loading(self):
        self.cache_tidy_model()
        loading, listening, release = threading.Event(), threading.Event(), threading.Event()
        self.dictation.listener.on_state.side_effect = lambda state: listening.set() if state == State.LISTENING else None

        def ensure_cleanup(plan, progress):
            loading.set()
            release.wait(5)

        with patch.object(self.dictation, "_ensure_cleanup", side_effect=ensure_cleanup) as ensure:
            worker = threading.Thread(target=self.dictation._prepare)
            worker.start()
            reached_listening = listening.wait(2)  # while the tidy-up load is still blocked
            release.set()
            worker.join(5)

        self.assertTrue(reached_listening)
        self.assertTrue(loading.wait(5))
        self.assertEqual(ensure.call_count, 1)
        self.assertIs(ensure.call_args.args[0], self.plan)
        self.dictation.mic.start.assert_called_once()

    def test_missing_tidy_model_downloads_before_listening_with_progress(self):
        progress = Mock()
        with patch.object(self.dictation, "_ensure_cleanup") as ensure:
            self.dictation._ensure_runtimes(progress)

        self.dictation.asr_server.ensure.assert_called_once_with("asr", progress)
        ensure.assert_called_once_with(self.plan, progress)

    def test_tidy_up_off_starts_only_the_speech_runtime(self):
        self.plan.model_id = None
        with patch.object(self.dictation, "_ensure_cleanup") as ensure:
            self.dictation._ensure_runtimes(Mock())

        self.dictation.asr_server.ensure.assert_called_once()
        ensure.assert_not_called()

    def test_failed_background_load_is_logged_not_raised(self):
        with patch.object(self.dictation, "_ensure_cleanup", side_effect=RuntimeError("server exited")), \
                self.assertLogs("speak.controller", "INFO") as logs:
            self.dictation._preload_cleanup(self.plan)

        self.assertIn("preload failed", logs.output[0])

    def test_speech_runtime_failure_aborts_before_any_tidy_up_start(self):
        self.cache_tidy_model()
        self.dictation.asr_server.ensure.side_effect = RuntimeError("asr exited")
        with patch.object(self.dictation, "_ensure_cleanup") as ensure, self.assertLogs("speak.controller", "ERROR"):
            self.dictation._prepare()

        ensure.assert_not_called()
        self.assertEqual(self.dictation.state, State.IDLE)
        self.dictation.listener.on_error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
