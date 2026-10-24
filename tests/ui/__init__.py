import os
from pathlib import Path
import unittest

from PySide6.QtWidgets import QApplication


class QtTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def capture(self, widget, name):
        directory = os.environ.get("SPEAK_UI_SNAPSHOT_DIR")
        if not directory:
            return
        path = Path(directory) / f"{self.id().replace('.', '_')}_{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.assertTrue(widget.grab().save(str(path)), f"Could not save UI screenshot: {path}")