from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from tests.ui import QtTestCase
from speak.ui.pages.history import HistoryEntry, HistoryPage


class HistoryInteractionTest(QtTestCase):
    """History actions clear saved entries and expose the empty state."""

    def test_clear_button_removes_rows_and_shows_empty_state(self):
        page = HistoryPage()
        page.show()
        self.addCleanup(page.close)
        with patch("speak.history.recent", side_effect=[
            [("2026-01-01T10:00:00+00:00", "A saved dictation")], []
        ]), patch("speak.history.clear") as clear:
            page.refresh(enabled=True)
            self.assertTrue(page.clear_button.isVisible())
            self.capture(page, "history-before-clear")

            QTest.mouseClick(page.clear_button, Qt.LeftButton)
            self.app.processEvents()

            self.capture(page, "history-after-clear")
        clear.assert_called_once()
        self.assertFalse(page.clear_button.isVisible())
        self.assertEqual("Nothing yet", page.empty_label.text())

    def test_selecting_a_saved_entry_copies_its_transcript(self):
        page = HistoryPage()
        page.show()
        self.addCleanup(page.close)
        with patch("speak.history.recent",
                   return_value=[("2026-01-01T10:00:00+00:00", "A saved dictation")]):
            page.refresh(enabled=True)
        entry = page.findChild(HistoryEntry)
        self.capture(page, "saved-history-entry")

        with patch("speak.output.copy") as copy:
            QTest.mouseClick(entry, Qt.LeftButton)

        copy.assert_called_once_with("A saved dictation")
