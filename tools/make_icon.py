"""Write the app icon (speak.ui.window.app_icon) as a multi-size .ico for the executable.

Usage: python tools/make_icon.py <out.ico>
"""
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from speak.ui.window import app_icon  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)


def main(out: Path) -> None:
    app = QApplication([])  # noqa: F841 (pixmaps need an application)
    icon = app_icon()
    images = []
    for size in SIZES:
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        icon.pixmap(size, size).toImage().save(buffer, "PNG")
        images.append((size, bytes(buffer.data())))
    # ICO: header, one directory entry per image, then PNG-encoded images (Vista+)
    data = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for size, png in images:
        data += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
    data += b"".join(png for _, png in images)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
