import unittest

from sherpa.recall_policy import repair_recall_perspective


class RecallPossessiveRepairTests(unittest.TestCase):
    def test_repairs_subject_and_possessive(self):
        fixed, changed = repair_recall_perspective(
            "I finished wiring my USB controller."
        )

        self.assertTrue(changed)
        self.assertEqual(
            fixed,
            "You finished wiring your USB controller.",
        )

    def test_repairs_possessive_after_model_used_you(self):
        fixed, changed = repair_recall_perspective(
            "You finished wiring my USB controller."
        )

        self.assertTrue(changed)
        self.assertEqual(
            fixed,
            "You finished wiring your USB controller.",
        )

    def test_repairs_possessive_after_me_who_conversion(self):
        fixed, changed = repair_recall_perspective(
            "Actually, it was me who finished wiring my power board."
        )

        self.assertTrue(changed)
        self.assertEqual(
            fixed,
            "Actually, it was you who finished wiring your power board.",
        )

    def test_preserves_nancee_memory_statement(self):
        original = "I remember my last answer."

        fixed, changed = repair_recall_perspective(original)

        self.assertFalse(changed)
        self.assertEqual(fixed, original)

    def test_preserves_unattributed_nancee_possessive(self):
        original = "That's my understanding."

        fixed, changed = repair_recall_perspective(original)

        self.assertFalse(changed)
        self.assertEqual(fixed, original)


if __name__ == "__main__":
    unittest.main()
