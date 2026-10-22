"""Write the app icon (speak.ui.window.render_icon) for the executable: .ico for Windows, .icns for macOS.

Usage: python tools/make_icon.py <out.ico|out.icns>
"""
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from speak.ui.window import app_icon, render_icon  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)
MAC_INSET = 0.1  # macOS icons keep a transparent margin around the rounded square


def write_icns(out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "speak.iconset"
        iconset.mkdir()
        for base in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                suffix = "" if scale == 1 else "@2x"
                render_icon(base * scale, inset=MAC_INSET).save(str(iconset / f"icon_{base}x{base}{suffix}.png"))
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True)


def main(out: Path) -> None:
    app = QApplication([])  # noqa: F841 (pixmaps need an application)
    if out.suffix == ".icns":
        write_icns(out)
        return
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
