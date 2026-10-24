import unittest
from unittest.mock import patch

from speak import cleanup


class CleanupTest(unittest.TestCase):
    """Dictation edits obey literal/smart rules and reject unsafe model output."""

    def test_rules_apply_spoken_commands_and_smart_only_fillers(self):
        raw = "um the the answer is 42 comma"

        self.assertEqual("The answer is 42 comma", cleanup.apply_rules(raw, "smart"))
        self.assertEqual("Um the the answer is 42 comma", cleanup.apply_rules(raw, "literal"))

    def test_validation_rejects_empty_text_and_invented_numbers(self):
        self.assertEqual("empty output", cleanup.validate("hello there", "", "smart"))
        self.assertIn("invented numbers",
                      cleanup.validate("hello there friend person", "hello 42 there friend person", "smart"))
        self.assertIsNone(cleanup.validate("hello comma world", "Hello, world", "literal"))

    def test_finalize_keeps_rule_based_text_when_model_fails(self):
        with patch.object(cleanup, "clean", side_effect=RuntimeError("server unavailable")):
            text, note = cleanup.finalize("hello world", "fast", "literal", port=1234)

        self.assertEqual("Hello world", text)
        self.assertIn("server unavailable", note)

    def test_finalize_converts_long_pause_to_paragraph(self):
        text, note = cleanup.finalize(f"first sentence. {cleanup.PAUSE} next sentence", "fast")

        self.assertEqual("First sentence.\n\nnext sentence", text)
        self.assertEqual("", note)


if __name__ == "__main__":
    unittest.main()
