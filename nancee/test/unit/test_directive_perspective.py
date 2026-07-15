from __future__ import annotations

import unittest

from directive_perspective import (
    repair_directive_perspective,
)


class DirectivePerspectiveTests(unittest.TestCase):
    def assert_repair(
        self,
        user_text,
        model_text,
        expected,
    ):
        repaired, changed = (
            repair_directive_perspective(
                user_text,
                model_text,
            )
        )

        self.assertTrue(changed)
        self.assertEqual(
            expected,
            repaired,
        )

    def test_repairs_have_i_question(self):
        self.assert_repair(
            (
                "Ask me if I finished wiring "
                "the power board."
            ),
            (
                "Have I completed wiring "
                "the power board yet?"
            ),
            (
                "Have you completed wiring "
                "the power board yet?"
            ),
        )

    def test_restores_the_instead_of_my(self):
        self.assert_repair(
            (
                "Ask me if I finished wiring "
                "the power board."
            ),
            (
                "Did you finish wiring "
                "my power board?"
            ),
            (
                "Did you finish wiring "
                "the power board?"
            ),
        )

    def test_source_my_becomes_your(self):
        self.assert_repair(
            (
                "Ask me if I finished wiring "
                "my power board."
            ),
            (
                "Did you finish wiring "
                "my power board?"
            ),
            (
                "Did you finish wiring "
                "your power board?"
            ),
        )

    def test_user_you_becomes_nancee_i(self):
        self.assert_repair(
            "Ask me if you are ready to continue.",
            "Are you ready to continue?",
            "Am I ready to continue?",
        )

    def test_user_your_becomes_nancee_my(self):
        self.assert_repair(
            (
                "Ask me if your microphone "
                "is working."
            ),
            (
                "Is your microphone working?"
            ),
            (
                "Is my microphone working?"
            ),
        )

    def test_correct_question_is_unchanged(self):
        original = (
            "Did you finish wiring "
            "the power board?"
        )

        repaired, changed = (
            repair_directive_perspective(
                (
                    "Ask me if I finished wiring "
                    "the power board."
                ),
                original,
            )
        )

        self.assertFalse(changed)
        self.assertEqual(
            original,
            repaired,
        )

    def test_non_ask_directive_is_unchanged(self):
        original = "I know a good joke."

        repaired, changed = (
            repair_directive_perspective(
                "Tell me a joke.",
                original,
            )
        )

        self.assertFalse(changed)
        self.assertEqual(
            original,
            repaired,
        )

    def test_multiple_sentence_output_is_not_blindly_rewritten(self):
        original = (
            "I don't remember that. "
            "Did you finish it?"
        )

        repaired, changed = (
            repair_directive_perspective(
                (
                    "Ask me if I finished "
                    "the power board."
                ),
                original,
            )
        )

        self.assertFalse(changed)
        self.assertEqual(
            original,
            repaired,
        )


if __name__ == "__main__":
    unittest.main()
