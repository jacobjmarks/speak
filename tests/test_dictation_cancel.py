import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from speak import cleanup, tidy
from speak.controller import Dictation, State


def dictation_for_processing():
    dictation = Dictation.__new__(Dictation)
    dictation._lock = threading.RLock()
    dictation._cancel_event = threading.Event()
    dictation._cancelled = False
    dictation._cancel_error = False
    dictation._schedule_unload = lambda: None
    dictation.state = State.PROCESSING
    dictation.listener = Mock()
    dictation.settings = {"history_enabled": False, "auto_paste": True, "press_enter": True}
    dictation._target = 123
    dictation.latest = ""
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

        def paste(text, should_enter):
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
        self.assertEqual(expected, dictation.latest)
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

        def paste(text, should_enter):
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


if __name__ == "__main__":
    unittest.main()
