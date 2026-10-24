"""The onboarding building blocks: painted widgets render distinctly per state, in both palettes, and the selection
widgets behave like exclusive option groups."""
from unittest.mock import patch

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QEnterEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget

from speak.ui import theme as ui_theme
from speak.ui.onboarding import common
from speak.ui.onboarding.widgets import (CheckBurst, Chip, ChoiceCard, MicPulse, ModeGlyph, OptionGroup, Segmented,
                                         StepDots, ThemeSwatch)
from tests.ui import QtTestCase
from tests.ui.onboarding_support import distinct_colours, jump_to

PALETTES = {"light": ui_theme.LIGHT, "dark": ui_theme.DARK}


def image(widget):
    return widget.grab().toImage()


def focus(widget):
    widget.window().activateWindow()
    widget.setFocus(Qt.TabFocusReason)
    QTest.qWait(30)
    assert widget.hasFocus()


def hover(widget):
    QApplication.sendEvent(widget, QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))


class PaintedWidgetTest(QtTestCase):
    """Each painted widget draws something visible, and its visual state (selected, hovered, disabled, kind, step)
    changes what is drawn, in the light and the dark palette."""

    def setUp(self):
        patcher = patch.object(common, "ANIMATE", False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def shown(self, widget, palette, size=None):
        widget.palette_ = palette
        if size:
            widget.resize(*size)
        widget.show()
        self.addCleanup(widget.close)
        return widget

    def all_different(self, images):
        for a in range(len(images)):
            for b in range(a + 1, len(images)):
                self.assertNotEqual(images[a], images[b], (a, b))

    def each_palette(self, make, check):
        for name, palette in PALETTES.items():
            with self.subTest(palette=name):
                check(name, make(palette))

    def test_choice_card_looks_different_when_hovered_selected_or_focused(self):
        def check(name, card):
            plain = image(card)
            hover(card)
            hovered = image(card)
            card.leaveEvent(None)
            card.setChecked(True)
            selected = image(card)
            focus(card)
            focused = image(card)
            self.capture(card, f"choice_card_{name}")
            self.assertNotEqual(plain, hovered)
            self.assertNotEqual(hovered, selected)
            self.assertNotEqual(selected, focused)
            self.assertEqual(plain, self.after_leave(card))

        self.each_palette(lambda pal: self.shown(ChoiceCard("Smart", "Sub", example="Example"), pal, (260, 160)),
                          check)

    def after_leave(self, card):
        card.clearFocus()
        card.setChecked(False)
        card.leaveEvent(None)
        return image(card)

    def test_choice_card_with_a_preview_puts_the_tick_beside_the_title(self):
        def check(name, card):
            card.setChecked(True)
            self.capture(card, f"choice_card_visual_{name}")
            self.assertTrue(card._badge_low)
            self.assertGreater(distinct_colours(card), 5)

        self.each_palette(lambda pal: self.shown(ChoiceCard("Dark", visual=ThemeSwatch("Dark"), compact=True), pal,
                                                 (220, 200)), check)

    def test_clicking_the_text_on_a_card_selects_the_card(self):
        card = self.shown(ChoiceCard("Quick", "Removes ums", example="Example"), ui_theme.LIGHT, (260, 160))
        clicks = []
        card.clicked.connect(lambda: clicks.append(1))

        QTest.mouseClick(card, Qt.LeftButton, pos=card.subtitle_label.geometry().center())
        card.setChecked(False)
        QTest.mouseClick(card, Qt.LeftButton, pos=card.title_label.geometry().center())

        self.assertEqual([1, 1], clicks)
        self.assertTrue(card.isChecked())

    def test_card_texts_can_be_replaced_and_a_title_only_card_ignores_them(self):
        full = ChoiceCard("Smart", "one", example="two")
        bare = ChoiceCard("Plain")

        full.set_texts("three", "four")
        bare.set_texts("ignored", "ignored")

        self.assertEqual(("three", "four"), (full.subtitle_label.text(), full.example_label.text()))
        self.assertIsNone(bare.subtitle_label)
        self.assertIsNone(bare.example_label)

    def test_chip_shows_selected_disabled_and_two_line_states(self):
        def check(name, chips):
            plain, two_line = chips
            before = image(plain)
            plain.setChecked(True)
            selected = image(plain)
            plain.setEnabled(False)
            disabled = image(plain)
            plain.setEnabled(True)
            focus(plain)
            focused = image(plain)
            two_line.setChecked(True)
            self.capture(two_line, f"chip_two_line_{name}")
            self.all_different([before, selected, disabled, focused])
            self.assertGreater(distinct_colours(two_line), 3)
            self.assertGreaterEqual(two_line.sizeHint().width(), plain.sizeHint().width())
            self.assertEqual(two_line.sizeHint(), two_line.minimumSizeHint())

        def make(palette):
            host = QWidget()
            row = QHBoxLayout(host)
            chips = Chip("Small"), Chip("Large", "Uses ~4 GB")
            for chip in chips:
                chip.palette_ = palette
                row.addWidget(chip)
            self.shown(host, palette)
            return chips

        self.each_palette(make, check)

    def test_segmented_selects_one_chip_and_programmatic_unknown_key_clears_it(self):
        group = Segmented({"a": "A", "b": ("B", "sub")}, "a")
        picked = []
        group.picked.connect(picked.append)
        group.show()
        self.addCleanup(group.close)
        self.assertTrue(group.chips["a"].isChecked())

        group.chips["b"].click()
        self.assertEqual((False, True), (group.chips["a"].isChecked(), group.chips["b"].isChecked()))
        group.set_value("a")
        self.assertEqual((True, False), (group.chips["a"].isChecked(), group.chips["b"].isChecked()))
        group.set_value("")

        self.assertEqual(["b"], picked)
        self.assertFalse(any(c.isChecked() for c in group.chips.values()))

    def test_option_group_ignores_unknown_keys(self):
        owner = QWidget()
        group = OptionGroup(owner)
        card = ChoiceCard("x")
        group.add("x", card)

        group.set_value("nope")
        self.assertFalse(card.isChecked())
        group.set_value("x")
        self.assertTrue(card.isChecked())

    def test_each_shortcut_mode_has_its_own_glyph(self):
        def check(name, glyphs):
            images = [image(g) for g in glyphs]
            self.capture(glyphs[0].parentWidget(), f"mode_glyphs_{name}")
            for a in range(3):
                for b in range(a + 1, 3):
                    self.assertNotEqual(images[a], images[b])

        def make(palette):
            host = QWidget()
            column = QVBoxLayout(host)
            glyphs = [ModeGlyph(kind) for kind in ("hold", "toggle", "auto")]
            for glyph in glyphs:
                glyph.palette_ = palette
                column.addWidget(glyph)
            host.resize(240, 200)
            self.shown(host, palette)
            return glyphs

        self.each_palette(make, check)

    def test_each_theme_swatch_shows_its_own_miniature_window(self):
        host = QWidget()
        row = QHBoxLayout(host)
        swatches = [ThemeSwatch(kind) for kind in ("System", "Light", "Dark")]
        for swatch in swatches:
            row.addWidget(swatch)
        host.resize(520, 140)
        host.show()
        self.addCleanup(host.close)

        images = [image(s) for s in swatches]

        self.capture(host, "theme_swatches")
        for a in range(3):
            self.assertGreater(distinct_colours(swatches[a]), 5)
            for b in range(a + 1, 3):
                self.assertNotEqual(images[a], images[b])

    def test_step_dots_stretch_the_current_dot_into_a_pill(self):
        def check(name, dots):
            dots.set_current(0)
            first = image(dots)
            dots.set_current(3)
            last = image(dots)
            self.capture(dots, f"step_dots_{name}")
            self.assertEqual(3.0, dots._value)
            self.assertNotEqual(first, last)

        self.each_palette(lambda pal: self.shown(StepDots(7), pal), check)

    def test_mic_pulse_ripples_with_the_voice_and_becomes_a_check_when_heard(self):
        def check(name, pulse):
            idle = image(pulse)
            pulse.set_active(True)
            self.assertTrue(pulse._timer.isActive())
            for _ in range(6):
                image(pulse)
            listening = image(pulse)
            pulse.set_heard(True)
            jump_to(pulse, 5)
            pulse._heard_at = 4.0
            heard = image(pulse)
            self.capture(pulse, f"mic_pulse_heard_{name}")
            self.assertNotEqual(idle, heard)
            self.assertNotEqual(listening, heard)
            pulse.set_heard(True)   # already heard: keeps its start
            self.assertEqual(4.0, pulse._heard_at)
            pulse.set_active(False)
            self.assertFalse(pulse._timer.isActive())    # leaving the step stops the repaint timer
            pulse.set_heard(False)
            self.assertFalse(pulse._timer.isActive())
            self.assertIsNone(pulse._heard_at)

        self.each_palette(lambda pal: self.shown(MicPulse(lambda: 0.4), pal), check)

    def test_mic_pulse_without_a_level_source_reading_stays_calm(self):
        pulse = self.shown(MicPulse(lambda: None), ui_theme.LIGHT)
        pulse.set_active(True)

        self.assertGreater(distinct_colours(pulse), 1)
        self.assertEqual(0.0, pulse._smooth)

    def test_check_burst_springs_in_draws_the_tick_then_stops_animating(self):
        def check(name, burst):
            resting = image(burst)       # before play(): the finished mark, as in a static screen
            burst.play()
            self.assertTrue(burst._timer.isActive())
            jump_to(burst, 0.0)
            burst._started = 0.0
            early = image(burst)
            jump_to(burst, 0.3)
            middle = image(burst)
            jump_to(burst, 1.5)
            end = image(burst)
            self.capture(burst, f"check_burst_{name}")
            self.assertNotEqual(early, middle)
            self.assertEqual(resting, end)
            self.assertFalse(burst._timer.isActive())

        self.each_palette(lambda pal: self.shown(CheckBurst(), pal), check)

