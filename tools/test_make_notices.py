import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools import make_notices


class MakeNoticesTest(unittest.TestCase):
    def test_generates_third_party_notices_without_root_license(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                "vendor/nemo-speech/share/licenses/nemo-speech/third_party/llama.cpp/LICENSE": "llama licence",
                "licenses/LGPL-3.0.txt": "LGPL licence",
                "licenses/GPL-3.0.txt": "GPL licence",
            }
            for name, text in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            output = root / "build" / "THIRD_PARTY_NOTICES.txt"
            with (
                patch.object(make_notices, "ROOT", root),
                patch.object(make_notices, "python_license", return_value="Python licence"),
                patch.object(make_notices, "runtime_distributions", return_value={}),
                patch.object(make_notices.metadata, "distribution",
                             return_value=SimpleNamespace(version="test", files=[])),
            ):
                make_notices.main(output)
            text = output.read_text(encoding="utf-8")
            self.assertFalse((root / "LICENSE").exists())
            self.assertNotIn("Speak is free software under the MIT", text)
            for licence in ("Python licence", "llama licence", "LGPL licence", "GPL licence"):
                self.assertIn(licence, text)


if __name__ == "__main__":
    unittest.main()
