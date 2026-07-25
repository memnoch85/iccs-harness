import unittest

from recall_policy import repair_recall_perspective


class RecallQuotedPerspectiveV41Tests(unittest.TestCase):
    def test_strips_you_said_wrapper_and_repairs_human_first_person(self):
        fixed, changed = repair_recall_perspective(
            'You said "I did finish wiring the power board."'
        )

        self.assertTrue(changed)
        self.assertEqual(
            "You did finish wiring the power board.",
            fixed,
        )

    def test_strips_you_told_me_wrapper(self):
        fixed, changed = repair_recall_perspective(
            'You told me: "My dad\'s name is Daniel."'
        )

        self.assertTrue(changed)
        self.assertEqual(
            "Your dad's name is Daniel.",
            fixed,
        )

    def test_normal_you_said_sentence_without_quotes_is_unchanged(self):
        original = "You said the connector was loose."
        fixed, changed = repair_recall_perspective(original)

        self.assertFalse(changed)
        self.assertEqual(original, fixed)


if __name__ == "__main__":
    unittest.main()
