from datetime import date, datetime, timedelta
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from tests.ui import QtTestCase
from speak.ui.pages.history import HistoryEntry, HistoryPage, day_label


class HistoryInteractionTest(QtTestCase):
    """History groups entries by day; clearing asks first, inline, and then exposes the empty state."""

    def test_clear_all_asks_first_and_only_deletes_once_confirmed(self):
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
            self.assertTrue(page.confirm.isVisible())
            self.capture(page, "history-confirm-clear")
            QTest.mouseClick(page.cancel_button, Qt.LeftButton)
            self.assertTrue(page.clear_button.isVisible())
            clear.assert_not_called()

            QTest.mouseClick(page.clear_button, Qt.LeftButton)
            QTest.mouseClick(page.confirm_button, Qt.LeftButton)
            self.app.processEvents()

            self.capture(page, "history-after-clear")
        clear.assert_called_once()
        self.assertFalse(page.confirm.isVisible())
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

    def test_entries_are_grouped_under_their_day(self):
        now = datetime.now().astimezone().replace(hour=9, minute=5)
        rows = [(now.isoformat(), "This morning"), (now.isoformat(), "Also this morning"),
                ((now - timedelta(days=1)).isoformat(), "Yesterday's note"),
                ((now - timedelta(days=9)).isoformat(), "Older note")]
        page = HistoryPage()
        page.show()
        self.addCleanup(page.close)
        with patch("speak.history.recent", return_value=rows):
            page.refresh(enabled=True)
        self.capture(page, "history-grouped")

        labels = [w.text() for w in page.entries.findChildren(type(page.empty_label)) if w.objectName() == "section"]
        self.assertEqual(["Today", "Yesterday", day_label((now - timedelta(days=9)).date(), date.today())], labels)
        self.assertEqual(4, len(page.findChildren(HistoryEntry)))
        self.assertEqual("09:05", page.findChild(HistoryEntry).when.text())

    def test_day_labels_name_older_days_and_add_the_year_only_when_it_differs(self):
        today = date(2026, 11, 26)
        self.assertEqual("Today", day_label(today, today))
        self.assertEqual("Yesterday", day_label(date(2026, 11, 25), today))
        self.assertEqual("Monday 23 November", day_label(date(2026, 11, 23), today))
        self.assertEqual("Wednesday 31 December 2025", day_label(date(2025, 12, 31), today))
