from __future__ import annotations

import unittest

from generation_completion import trim_prompt_role_leak


class TestInstructionLeakGuard(unittest.TestCase):
    def test_existing_prompt_role_marker_is_removed(self):
        cleaned, trimmed = trim_prompt_role_leak(
            "That is correct.\nUSER MESSAGE: another prompt"
        )

        self.assertTrue(trimmed)
        self.assertEqual(
            cleaned,
            "That is correct.",
        )

    def test_remember_constraint_leak_is_removed(self):
        cleaned, trimmed = trim_prompt_role_leak(
            (
                "Sorry about that.\n\n"
                "Remember:\n"
                "Keep responses concise and directly related "
                "to the user's last message."
            )
        )

        self.assertTrue(trimmed)
        self.assertEqual(
            cleaned,
            "Sorry about that.",
        )

    def test_direct_constraint_leak_is_removed(self):
        cleaned, trimmed = trim_prompt_role_leak(
            (
                "You said power board.\n"
                "Answer only what the user asked, then stop."
            )
        )

        self.assertTrue(trimmed)
        self.assertEqual(
            cleaned,
            "You said power board.",
        )

    def test_partial_streamed_leak_is_removed_early(self):
        cleaned, trimmed = trim_prompt_role_leak(
            (
                "Sorry about that.\n"
                "Remember: Keep responses concise"
            )
        )

        self.assertTrue(trimmed)
        self.assertEqual(
            cleaned,
            "Sorry about that.",
        )

    def test_legitimate_remember_sentence_is_preserved(self):
        original = (
            "Remember: keep the headlights off while parked."
        )

        cleaned, trimmed = trim_prompt_role_leak(
            original
        )

        self.assertFalse(trimmed)
        self.assertEqual(
            cleaned,
            original,
        )

    def test_legitimate_keep_sentence_is_preserved(self):
        original = (
            "Keep the connector dry until the seal cures."
        )

        cleaned, trimmed = trim_prompt_role_leak(
            original
        )

        self.assertFalse(trimmed)
        self.assertEqual(
            cleaned,
            original,
        )


if __name__ == "__main__":
    unittest.main()
