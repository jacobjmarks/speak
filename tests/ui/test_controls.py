from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QLabel, QPushButton

from tests.ui import QtTestCase
from speak.ui.controls import SettingRow


class SettingRowConstructionTest(QtTestCase):
    """A visible hint remains parented instead of flashing as a top-level window."""

    def test_nonempty_hint_is_never_shown_without_its_row_parent(self):
        orphan_shows = []

        class ShowSpy(QObject):
            def eventFilter(self, watched, event):
                if (event.type() == QEvent.Show and isinstance(watched, QLabel)
                        and watched.text() == "Hint" and watched.parentWidget() is None):
                    orphan_shows.append(watched)
                return False

        spy = ShowSpy(self.app)
        self.app.installEventFilter(spy)
        try:
            row = SettingRow("Title", "Hint", QPushButton("Control"))
        finally:
            self.app.removeEventFilter(spy)

        self.assertEqual([], orphan_shows)
        self.assertIs(row.hint.parentWidget(), row)
