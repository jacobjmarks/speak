import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from speak import history


class HistoryTest(unittest.TestCase):
    """Transcript history is isolated, newest-first, limited, and clearable."""

    def test_opt_in_store_returns_newest_first_and_clears(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(history, "HISTORY_FILE", Path(directory) / "history.sqlite3"):
            self.assertEqual([], history.recent())
            history.add("first")
            history.add("second")

            self.assertEqual(["second", "first"], [text for _, text in history.recent()])
            self.assertEqual(["second"], [text for _, text in history.recent(1)])
            history.clear()
            self.assertEqual([], history.recent())


if __name__ == "__main__":
    unittest.main()
