from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from tests.ui import QtTestCase
from speak.ui.controls import SettingRow, SettingsSection


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


class SettingsSectionLayoutTest(QtTestCase):
    """A section draws dividers only between visible rows, shows More options only when it has visible technical
    rows, and hides itself when nothing in it is visible."""

    def test_hiding_rows_moves_dividers_and_hides_empty_parts(self):
        holder = QWidget()
        layout = QVBoxLayout(holder)
        section = SettingsSection("Things")
        layout.addWidget(section)
        first, second = SettingRow("First", "", QPushButton()), SettingRow("Second", "", QPushButton())
        extra = SettingRow("Extra", "", QPushButton())
        for row, advanced in ((first, False), (second, False), (extra, True)):
            section.add(row, advanced)
        holder.show()
        self.addCleanup(holder.close)
        self.assertEqual([False, True], [bool(first.property("divider")), bool(second.property("divider"))])
        self.assertTrue(section.more.isVisible())
        self.assertFalse(extra.isVisible())

        first.hide()
        extra.hide()

        self.assertFalse(bool(second.property("divider")))
        self.assertFalse(section.more.isVisible())

        second.hide()

        self.assertFalse(section.isVisible())
