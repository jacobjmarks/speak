"""Shared fixtures for the onboarding tests: a page whose OS/hardware boundaries are mocked, and small helpers."""
import time
from unittest.mock import patch

from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton

from speak import config, tidy
from speak.benchmark import Result
from speak.ui import onboarding, theme as ui_theme
from speak.ui.onboarding import OnboardingPage
from tests.ui import QtTestCase

STEP_NAMES = ("welcome", "theme", "mic", "keys", "tidy", "look", "updates", "done")
GPU = tidy.Gpu("Vulkan0", "Test GPU 8GB", 8000)


def button(page, text):
    return next(b for b in page.findChildren(QPushButton) if b.text() == text)


def result(latency=0.5, raw="raw", text="Clean.", plan=None):
    plan = plan or tidy.Plan("fast", None, "literal", None, "plan")
    return Result(10.0, 3.0, latency - 0.2, 0.2, raw, text, plan)


def fake_plan(settings):
    """A computer with a good graphics card: Automatic and Large both mean Large AI there."""
    level = settings["tidy"]
    if level in ("off", "fast"):
        return tidy.Plan(level, None, "literal", None, "")
    small = settings.get("cleanup_model") == config.SMALL_MODEL
    model = config.SMALL_MODEL if small else config.LARGE_MODEL
    mode = "smart" if model == config.LARGE_MODEL and settings["corrections"] else "literal"
    return tidy.Plan(level, model, mode, "Vulkan0", "")


def low_memory_plan(settings):
    """A computer without room for Large: AI always falls back to Small, on the processor."""
    level = settings["tidy"]
    if level in ("off", "fast"):
        return tidy.Plan(level, None, "literal", None, "")
    return tidy.Plan(level, config.SMALL_MODEL, "literal", None, "")


def cpu_plan(settings):
    """No usable graphics card: Large AI runs on the processor."""
    level = settings["tidy"]
    if level in ("off", "fast"):
        return tidy.Plan(level, None, "literal", None, "")
    small = settings.get("cleanup_model") == config.SMALL_MODEL
    return tidy.Plan(level, config.SMALL_MODEL if small else config.LARGE_MODEL, "smart", None, "")


def distinct_colours(widget, step: int = 3) -> int:
    image = widget.grab().toImage()
    assert isinstance(image, QImage) and not image.isNull()
    return len({image.pixel(x, y) for x in range(0, image.width(), step) for y in range(0, image.height(), step)})


def wait_for(condition, timeout_ms: int = 3000) -> bool:
    """Spin the event loop until `condition()` holds; returns whether it did."""
    deadline = time.monotonic() + timeout_ms / 1000
    while not condition():
        if time.monotonic() > deadline:
            return False
        QTest.qWait(10)
    return True


def jump_to(animated, seconds: float):
    """Move an animated widget's clock so its `phase` reads `seconds`."""
    animated._t0 = time.monotonic() - seconds


class OnboardingCase(QtTestCase):
    """Base: builds an `OnboardingPage` in `theme` with `animate` on or off; subclass with theme = "Dark"."""

    theme = "Light"
    animate = False
    plan = staticmethod(fake_plan)
    gpus = ()
    dim_supported = True

    def make(self, settings=None, size=(1000, 760)):
        patches = [patch.object(onboarding.common, "ANIMATE", self.animate),
                   patch("speak.ui.onboarding.steps.mic.audio.Microphone"),
                   patch("speak.ui.pages.audio.input_devices", return_value=["Desk mic", "Headset"]),
                   patch("speak.ui.onboarding.steps.tidy.tidy.plan", side_effect=self.plan),
                   patch("speak.ui.onboarding.page.tidy.gpus", return_value=list(self.gpus)),
                   patch("speak.ui.onboarding.steps.keys.system_audio.SUPPORTED", self.dim_supported)]
        mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        mocks[1].return_value.level = 0.5
        self.mic = mocks[1]
        page = OnboardingPage({**config.DEFAULTS, **(settings or {})})
        pal = ui_theme.resolve(self.theme)
        page.setStyleSheet(ui_theme.stylesheet(pal) + f"QWidget#page {{ background: {pal.bg}; }}")
        page.set_palette(pal)
        page.resize(*size)
        page.show()
        self.addCleanup(page.close)
        return page

    def tour(self, page, index):
        """Go to a step and, when animating, wait until its screen has fully faded in."""
        page.go(index)
        if self.animate:
            wait_for(lambda: page.steps.currentIndex() == index and self.revealed(page, index), 5000)
        return page

    @staticmethod
    def revealed(page, index) -> bool:
        return all(w.graphicsEffect() is None for w in page._reveals[index])