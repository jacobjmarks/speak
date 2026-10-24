from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from tests.ui import QtTestCase
from speak.ui.pages import DictatePage


class DictatePageInteractionTest(QtTestCase):
    """Dictate controls start/stop recording and copy the text shown to the user."""

    def test_microphone_button_requests_dictation_toggle(self):
        page = DictatePage(lambda: 0.0)
        page.show()
        self.addCleanup(page.close)
        requests = []
        page.toggle_requested.connect(lambda: requests.append(True))

        self.capture(page, "dictation-ready")
        QTest.mouseClick(page.mic, Qt.LeftButton)

        self.assertEqual([True], requests)

    def test_copy_button_copies_visible_transcript_and_confirms_to_user(self):
        page = DictatePage(lambda: 0.0)
        page.show()
        self.addCleanup(page.close)
        page.set_result("Your words are ready.")
        self.capture(page, "transcript-ready-to-copy")

        with patch("speak.ui.pages.output.copy") as copy:
            QTest.mouseClick(page.copy_button, Qt.LeftButton)

        self.capture(page, "transcript-copied")
        copy.assert_called_once_with("Your words are ready.")
        self.assertEqual("Copied ✓", page.copy_button.text())
