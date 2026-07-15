import unittest

from sherpa.recall_policy import (
    looks_like_perspective_correction,
    repair_recall_perspective,
)


class RecallPolicyTests(unittest.TestCase):
    def test_detects_user_or_nancee_correction(self):
        self.assertTrue(
            looks_like_perspective_correction(
                "Uh, Nancy, you bought hot sauce or I bought hot sauce."
            )
        )

    def test_normal_question_is_not_a_correction(self):
        self.assertFalse(
            looks_like_perspective_correction("Where did I buy hot sauce?")
        )

    def test_repairs_leading_user_action(self):
        fixed, changed = repair_recall_perspective(
            "Today I bought hot sauce."
        )
        self.assertTrue(changed)
        self.assertEqual(fixed, "Today you bought hot sauce.")

    def test_repairs_me_who_action(self):
        fixed, changed = repair_recall_perspective(
            "Actually, it was me who purchased the hot sauce."
        )
        self.assertTrue(changed)
        self.assertEqual(
            fixed,
            "Actually, it was you who purchased the hot sauce.",
        )

    def test_preserves_valid_nancee_first_person(self):
        original = "I remember you said you bought hot sauce."
        fixed, changed = repair_recall_perspective(original)
        self.assertFalse(changed)
        self.assertEqual(fixed, original)


if __name__ == "__main__":
    unittest.main()
