from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPauseAnimation, QPoint, QPropertyAnimation, QSequentialAnimationGroup, Qt, QTimer
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget
from ... import config, tidy

HEARD_LEVEL = 0.04          # mic level (0..1) that counts as "heard you"
AMBER = "#d9a441"
SAY = "um so the meeting is tuesday no wait wednesday"
# What each tidy level really produces for SAY (see cleanup.finalize); the AI example depends on the model.
EXAMPLE_OFF = "Um so the meeting is tuesday no wait wednesday"
EXAMPLE_QUICK = "So the meeting is tuesday no wait wednesday"
EXAMPLE_LITERAL = "So the meeting is Tuesday, no wait, Wednesday."
EXAMPLE_SMART = "The meeting is Wednesday."
STAGE_TEXT = "Hi team, the meeting is on Wednesday at three. Please send me the notes before then."
STAGE_FROZEN_WORDS = 9
COLUMN_WIDTH = 820
ANIMATE = True              # tests switch this off so screens are complete the moment they appear

SHORTCUT_HINTS = {"auto": "Hold while you speak, or tap to start and stop",
                  "hold": "Hold while you speak. Let go to finish",
                  "toggle": "Tap to start. Tap again to stop"}
UPDATE_HINTS = {"auto": "Checks daily and installs when you restart Speak",
                "notify": "Checks daily and tells you. Nothing installs by itself",
                "off": "Never checks. You can check by hand in Settings"}
MODEL_CHOICES = {"auto": ("Automatic", "Best fit"),
                 "small": ("Small", f"Uses ~{round(tidy._memory_required_mb(config.SMALL_MODEL) / 1000)} GB"),
                 "large": ("Large", f"Uses ~{round(tidy._memory_required_mb(config.LARGE_MODEL) / 1000)} GB")}


def _seconds(value: float) -> str:
    return "under 0.1 s" if value < 0.1 else f"{value:.1f} s"


def _passthrough(widget: QWidget):
    """Let clicks on a card's contents reach the card."""
    for child in widget.findChildren(QWidget):
        child.setAttribute(Qt.WA_TransparentForMouseEvents)


def _ai_changes(choice: str) -> dict:
    """Settings behind the AI model chips: Automatic and Large are tidy levels, Small pins the small model."""
    if choice == "small":
        return {"tidy": "auto", "cleanup_model": config.SMALL_MODEL}
    return {"tidy": "best" if choice == "large" else "auto", "cleanup_model": "auto"}


def _model_choice(settings: dict) -> str:
    if settings["tidy"] == "best" or settings.get("cleanup_model") == config.LARGE_MODEL:
        return "large"
    return "small" if settings.get("cleanup_model") == config.SMALL_MODEL else "auto"


def _level(settings: dict) -> str:
    return "ai" if settings["tidy"] in ("auto", "best") else settings["tidy"]


class Revealer:
    """Fades and raises widgets in one after another. Effects are removed afterwards so nothing keeps repainting
    through an offscreen buffer."""

    def __init__(self):
        self._group = None
        self._ends = {}

    def stop(self):
        group, self._group = self._group, None
        if group is not None:
            group.stop()
        ends, self._ends = self._ends, {}
        for widget, pos in ends.items():
            try:
                widget.setGraphicsEffect(None)
                if pos is not None:
                    widget.move(pos)
            except RuntimeError:
                pass

    def play(self, widgets, root: QWidget, delay: int = 70, duration: int = 520, rise: int = 24):
        self.stop()
        if not ANIMATE:
            return
        widgets = [w for w in widgets if w is not None]
        for widget in widgets:
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(0.0)
            widget.setGraphicsEffect(effect)
            self._ends[widget] = None
        token = self._ends
        QTimer.singleShot(0, lambda: self._start(token, widgets, root, delay, duration, rise))

    def _start(self, token, widgets, root, delay, duration, rise):
        if token is not self._ends:
            return
        if root.layout() is not None:
            root.layout().activate()
        group = QParallelAnimationGroup()
        for i, widget in enumerate(widgets):
            end = widget.pos()
            self._ends[widget] = end
            widget.move(end + QPoint(0, rise))
            step = QParallelAnimationGroup()
            fade = QPropertyAnimation(widget.graphicsEffect(), b"opacity")
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.setDuration(duration)
            fade.setEasingCurve(QEasingCurve.OutCubic)
            lift = QPropertyAnimation(widget, b"pos")
            lift.setStartValue(end + QPoint(0, rise))
            lift.setEndValue(end)
            lift.setDuration(duration)
            lift.setEasingCurve(QEasingCurve.OutExpo)
            step.addAnimation(fade)
            step.addAnimation(lift)
            sequence = QSequentialAnimationGroup()
            sequence.addAnimation(QPauseAnimation(i * delay))
            sequence.addAnimation(step)
            group.addAnimation(sequence)
        group.finished.connect(self.stop)
        self._group = group
        group.start()
