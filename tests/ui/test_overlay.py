from PySide6.QtGui import QFontMetrics
from unittest.mock import patch

from tests.ui import QtTestCase
from speak.ui.overlay import Overlay


class OverlayLiveTextTest(QtTestCase):
    """The full live preview shows the newest words that fit the card without re-measuring the whole session."""

    def make_overlay(self):
        overlay = Overlay(lambda: 0.0)
        overlay.preview, overlay.mode = "full", "listening"
        self.addCleanup(overlay.close)
        return overlay

    def test_short_text_is_shown_unchanged(self):
        overlay = self.make_overlay()

        overlay.set_text("hello there world")

        self.assertEqual("hello there world", overlay._visible_text())

    def test_long_session_measures_only_a_bounded_tail_and_shows_the_newest_words(self):
        overlay = self.make_overlay()
        measured = []

        class CountingMetrics(QFontMetrics):
            def boundingRect(self, rect, flags, text):
                measured.append(text)
                return super().boundingRect(rect, flags, text)

        with patch("speak.ui.overlay.QFontMetrics", CountingMetrics):
            overlay.set_text(" ".join(f"word{i}" for i in range(3_000)))

        shown = overlay._visible_text()
        self.assertLess(len(measured), 500)  # measuring every word of the session would take ~3,000
        self.assertTrue(shown.startswith("… word"))
        self.assertTrue(shown.endswith("word2999"))
