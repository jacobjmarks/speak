"""Render the README marketing images from the real Speak UI.

Usage: python -m tools.marketing_images [output_dir]
"""
import json
import sys
import tempfile
import traceback
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from speak import config, hotkey, permissions, updates
from speak.controller import Dictation

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "docs" / "images"
OUT.mkdir(parents=True, exist_ok=True)

_scratch_dir = tempfile.TemporaryDirectory(prefix="speak-marketing-")
_scratch = Path(_scratch_dir.name)
config.APP_DIR = _scratch
config.SETTINGS_FILE = _scratch / "settings.json"
config.HISTORY_FILE = _scratch / "history.sqlite3"
config.MODELS_DIR = _scratch / "models"
config.ASR_LOG = _scratch / "runtime.log"
config.CLEANUP_LOG = _scratch / "cleanup-runtime.log"
hotkey.register = lambda *args, **kwargs: None
permissions.missing = lambda: []
Dictation.warm_up = lambda self: None
updates.cleanup = lambda: None

from speak.ui.app import SpeakApp  # noqa: E402
from speak.ui.overlay import Overlay  # noqa: E402
from speak.ui.window import app_icon  # noqa: E402

SpeakApp._check_updates = lambda *args, **kwargs: None

EXAMPLE = (
    "Hi Sam, the meeting is at four o'clock on Thursday.\n\n"
    "Can you bring the slides?\n\nThanks!"
)
LIVE_TEXT = "hi sam the meeting is at three no wait four o'clock on thursday can you bring the"


def main():
    app = QApplication(sys.argv)
    config.SETTINGS_FILE.write_text(
        json.dumps({**config.DEFAULTS, "theme": "Light", "close_action": "tray", "history_enabled": True}),
        encoding="utf-8",
    )
    speak = SpeakApp(app, background=False)
    window = speak.window
    window.resize(780, 560)

    def schedule(delay, callback):
        def run():
            try:
                callback()
            except Exception:
                traceback.print_exc()
                app.exit(1)

        QTimer.singleShot(delay, run)

    def save_window(name):
        if not window.grab().save(str(OUT / f"{name}.png")):
            raise OSError(f"Could not save {OUT / f'{name}.png'}")

    def save_overlay(theme_name, done):
        overlay = Overlay(lambda: 0.09)
        overlay.palette_ = speak.palette
        overlay.preview, overlay.position = "line", "cursor"
        overlay.set_mode("listening")
        overlay.set_text(LIVE_TEXT)

        def capture():
            if not overlay.grab().save(str(OUT / f"overlay-{theme_name}.png")):
                raise OSError(f"Could not save {OUT / f'overlay-{theme_name}.png'}")
            overlay.hide_now()
            done()

        schedule(1000, capture)

    def save_hero():
        overlay = QPixmap(str(OUT / "overlay-dark.png"))
        image = QPixmap(1280, 440)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        gradient = QLinearGradient(0, 0, 1280, 440)
        gradient.setColorAt(0, QColor("#1d4a46"))
        gradient.setColorAt(1, QColor("#2f7a72"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(QRectF(0, 0, 1280, 440), 28, 28)
        painter.setBrush(QColor(255, 255, 255, 34))
        painter.drawRoundedRect(QRectF(88, 142, 144, 144), 38, 38)
        painter.drawPixmap(96, 150, app_icon().pixmap(128, 128))
        font = QFont(app.font())
        font.setPointSize(54)
        font.setWeight(QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor("#f4e7c8"))
        painter.drawText(QRectF(256, 130, 600, 100), Qt.AlignLeft | Qt.AlignVCenter, "Speak")
        font.setPointSize(20)
        font.setWeight(QFont.Normal)
        painter.setFont(font)
        painter.setPen(QColor("#e6f0ee"))
        painter.drawText(QRectF(260, 228, 640, 50), Qt.AlignLeft | Qt.AlignVCenter, "Talk anywhere. It types.")
        font.setPointSize(12)
        painter.setFont(font)
        painter.setPen(QColor("#b9d3cf"))
        painter.drawText(QRectF(262, 280, 640, 30), Qt.AlignLeft | Qt.AlignVCenter, "Private  ·  Offline  ·  Fast")
        painter.drawPixmap(
            int(1280 - overlay.width() * 1.25 - 80),
            int(220 - overlay.height() * 1.25 / 2),
            overlay.scaled(
                int(overlay.width() * 1.25), int(overlay.height() * 1.25),
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            ),
        )
        painter.end()
        if not image.save(str(OUT / "hero.png")):
            raise OSError(f"Could not save {OUT / 'hero.png'}")

    def render_dark():
        speak._update({"theme": "Dark"})
        window.show_page(0)
        window.dictate.set_result(EXAMPLE)
        window.dictate.set_mode("done")

        def capture_dictate():
            save_window("dictate-dark")
            window.show_page(2)
            schedule(500, capture_settings)

        def capture_settings():
            save_window("settings-dark")
            save_overlay("dark", capture_hero)

        def capture_hero():
            save_hero()
            speak.quit()

        schedule(500, capture_dictate)

    def render_light():
        window.show_page(0)
        window.dictate.set_result(EXAMPLE)
        window.dictate.set_mode("done")

        def capture_dictate():
            save_window("dictate-light")
            window.show_page(2)
            schedule(500, capture_settings)

        def capture_settings():
            save_window("settings-light")
            save_overlay("light", render_dark)

        schedule(500, capture_dictate)

    schedule(500, render_light)
    result = app.exec()
    if result:
        raise SystemExit(result)
    images = sorted(OUT.glob("*.png"))
    print(f"Wrote {len(images)} PNGs to {OUT}")


if __name__ == "__main__":
    main()
