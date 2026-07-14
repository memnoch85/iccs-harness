import unittest

from generation_completion import (
    final_fragment_is_safe,
    trim_incomplete_length_tail,
)


class GenerationCompletionTests(unittest.TestCase):
    def test_length_cutoff_rejects_unfinished_final_fragment(self):
        self.assertFalse(
            final_fragment_is_safe(
                "he succeeded only when",
                {"done_reason": "length"},
            )
        )

    def test_length_cutoff_accepts_complete_final_sentence(self):
        self.assertTrue(
            final_fragment_is_safe(
                "He served Morgoth.",
                {"done_reason": "length"},
            )
        )

    def test_history_drops_only_incomplete_tail(self):
        text, changed = trim_incomplete_length_tail(
            "First sentence. Second thought only when",
            {"done_reason": "length"},
        )

        self.assertEqual(text, "First sentence.")
        self.assertTrue(changed)

    def test_stop_completion_remains_unchanged(self):
        text, changed = trim_incomplete_length_tail(
            "Complete answer.",
            {"done_reason": "stop"},
        )

        self.assertEqual(text, "Complete answer.")
        self.assertFalse(changed)


if __name__ == "__main__":
    unittest.main()
