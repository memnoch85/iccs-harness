import unittest

from memory_policy import (
    is_complete_memory_statement,
    looks_like_personal_fact_fragment,
    memory_storage_skip_reason,
)


class MemoryPolicyGuardrailTests(unittest.TestCase):
    def test_backpack_statement_is_stored(self):
        self.assertTrue(
            is_complete_memory_statement(
                "So Nancy, I bought a blue backpack yesterday at Macy's."
            )
        )

    def test_vehicle_statement_is_stored(self):
        self.assertTrue(
            is_complete_memory_statement("I drive a black Jeep.")
        )

    def test_possessive_assignment_is_stored(self):
        self.assertTrue(
            is_complete_memory_statement("My wife's name is Anna.")
        )

    def test_hardly_drive_is_rejected(self):
        self.assertFalse(
            is_complete_memory_statement("Hardly drive.")
        )

    def test_incomplete_possessive_fragment_is_rejected(self):
        self.assertFalse(
            is_complete_memory_statement("My wife's name.")
        )

    def test_incomplete_possessive_fragment_is_recall_shaped(self):
        self.assertTrue(
            looks_like_personal_fact_fragment("My wife's name.")
        )

    def test_question_is_rejected(self):
        self.assertFalse(
            is_complete_memory_statement("What car do I drive?")
        )

    def test_command_is_rejected(self):
        self.assertFalse(
            is_complete_memory_statement("Explain how a turbo works.")
        )

    def test_skip_reason_is_visible(self):
        self.assertEqual(
            memory_storage_skip_reason("My wife's name."),
            "personal_fact_fragment",
        )


if __name__ == "__main__":
    unittest.main()
