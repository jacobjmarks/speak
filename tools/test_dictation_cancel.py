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


class DictationCancelTest(unittest.TestCase):
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
