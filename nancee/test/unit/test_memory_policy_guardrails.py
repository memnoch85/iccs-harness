import unittest

from memory_policy import (
    extract_storable_memory_text,
    is_complete_memory_statement,
    looks_like_personal_fact_fragment,
    memory_storage_skip_reason,
    normalize_memory_candidate,
)


class MemoryPolicyGuardrailTests(unittest.TestCase):
    def test_punctuated_greeting_preface_is_removed(self):
        self.assertEqual(
            normalize_memory_candidate(
                "Hey, Nancy, I bought a blue backpack at Macy's."
            ),
            "I bought a blue backpack at Macy's.",
        )

    def test_greeting_prefaced_purchase_is_stored(self):
        self.assertTrue(
            is_complete_memory_statement(
                "Hey, Nancy, I bought a blue backpack at Macy's."
            )
        )

    def test_finished_wiring_statement_is_stored(self):
        self.assertTrue(
            is_complete_memory_statement(
                "I finished wiring a power board today."
            )
        )

    def test_temporal_preface_statement_is_stored(self):
        self.assertTrue(
            is_complete_memory_statement(
                "Today I bought hot sauce at Macy's."
            )
        )

    def test_missing_i_completed_action_is_stored(self):
        self.assertTrue(
            is_complete_memory_statement(
                "Bought a blue backpack at Macy's."
            )
        )

    def test_possessive_assignment_is_stored(self):
        self.assertTrue(
            is_complete_memory_statement(
                "My wife's name is Anna."
            )
        )

    def test_related_third_person_clauses_are_preserved(self):
        text = (
            "My favorite band is Finch. "
            "They are from Temecula, California. "
            "They play post-hardcore music."
        )

        self.assertEqual(
            text,
            extract_storable_memory_text(text),
        )

    def test_barely_works_is_rejected(self):
        self.assertFalse(
            is_complete_memory_statement("Barely works.")
        )

    def test_incomplete_possessive_fragment_is_rejected(self):
        self.assertFalse(
            is_complete_memory_statement("My wife's name.")
        )
        self.assertTrue(
            looks_like_personal_fact_fragment("My wife's name.")
        )

    def test_question_and_command_are_rejected(self):
        self.assertFalse(
            is_complete_memory_statement(
                "What did I buy yesterday?"
            )
        )
        self.assertFalse(
            is_complete_memory_statement(
                "Explain how a database index works."
            )
        )

    def test_low_value_first_person_is_rejected(self):
        self.assertFalse(
            is_complete_memory_statement("I don't know.")
        )
        self.assertEqual(
            memory_storage_skip_reason("I don't know."),
            "low_value_first_person",
        )


if __name__ == "__main__":
    unittest.main()

