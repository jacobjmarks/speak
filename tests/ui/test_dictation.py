import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtTest import QTest

from tests.ui import QtTestCase
from speak.ui import theme as ui_theme
from speak.ui.app import Bridge, SpeakApp
from speak.ui.overlay import Overlay
from speak.ui.pages import LIVE_TAIL_CHARS, DictatePage


class DictatePageInteractionTest(QtTestCase):
    """Dictate controls start/stop recording and copy the text shown to the user."""

    def test_microphone_button_requests_dictation_toggle(self):
        page = DictatePage(lambda: 0.0)
        page.setStyleSheet(ui_theme.stylesheet(ui_theme.DARK))
        page.show()
        self.addCleanup(page.close)
        requests = []
        page.toggle_requested.connect(lambda: requests.append(True))

        self.capture(page, "dictation-ready")
        QTest.mouseClick(page.mic, Qt.LeftButton)

        self.assertEqual([True], requests)

    def test_copy_button_copies_visible_transcript_and_confirms_to_user(self):
        page = DictatePage(lambda: 0.0)
        page.setStyleSheet(ui_theme.stylesheet(ui_theme.DARK))
        page.show()
        self.addCleanup(page.close)
        page.set_result("Your words are ready.")
        self.capture(page, "transcript-ready-to-copy")

        with patch("speak.ui.pages.output.copy") as copy:
            QTest.mouseClick(page.copy_button, Qt.LeftButton)

        self.capture(page, "transcript-copied")
        copy.assert_called_once_with("Your words are ready.")
        self.assertEqual("Copied ✓", page.copy_button.text())


class DictatePageLiveTextTest(QtTestCase):
    """The live view shows only the newest text; copying and the error fallback keep the whole transcript."""

    def make_page(self):
        page = DictatePage(lambda: 0.0)
        self.addCleanup(page.close)
        return page

    def test_live_view_is_capped_to_the_newest_text_and_the_transcript_is_kept(self):
        page = self.make_page()
        transcript = " ".join(f"w{i}" for i in range(3000))

        page.set_live(transcript)

        shown = page.text.toPlainText()
        self.assertLessEqual(len(shown), LIVE_TAIL_CHARS)
        self.assertTrue(shown.endswith("w2999"))
        self.assertEqual(transcript, page.transcript())

    def test_copy_during_listening_copies_the_whole_transcript(self):
        page = self.make_page()
        transcript = " ".join(f"w{i}" for i in range(3000))
        page.set_live(transcript)

        with patch("speak.ui.pages.output.copy") as copy:
            page.copy_button.click()

        copy.assert_called_once_with(transcript)

    def test_error_keeps_the_whole_transcript_for_copying(self):
        page = self.make_page()
        transcript = " ".join(f"w{i}" for i in range(3000))
        page.set_live(transcript)
        app = SimpleNamespace(window=Mock(dictate=page), overlay=Mock(**{"isVisible.return_value": False}),
                              tray=None, palette=ui_theme.LIGHT)

        SpeakApp._on_error(app, "Speak lost the microphone. Please try again.")

        self.assertEqual(transcript, page.transcript())


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


class LiveTextDeliveryTest(QtTestCase):
    """Live text from ASR threads reaches the UI as the newest transcript, not one UI update per ASR update."""

    def test_a_burst_from_a_worker_thread_is_delivered_once_as_its_latest_text(self):
        bridge = Bridge()
        delivered = []
        bridge.live.connect(delivered.append)

        def burst(prefix):
            for i in range(500):
                bridge.on_live_text(f"{prefix}{i}")

        for prefix in ("a", "b"):
            worker = threading.Thread(target=burst, args=(prefix,))
            worker.start()
            worker.join()
            self.app.processEvents()

        self.assertEqual(["a499", "b499"], delivered)
