import unittest

from memory_policy import (
    is_complete_memory_statement,
    normalize_memory_candidate,
)
from input_router import route_user_input
from recall_policy import repair_recall_perspective
from response_policy import response_policy_for_route


class PreBenchmarkRecallRegressionTests(
    unittest.TestCase
):
    def test_wired_answer_becomes_second_person(self):
        fixed, changed = repair_recall_perspective(
            "I wired a PCB board today."
        )

        self.assertTrue(changed)
        self.assertEqual(
            "You wired a PCB board today.",
            fixed,
        )

    def test_finished_answer_becomes_second_person(self):
        fixed, changed = repair_recall_perspective(
            "Yesterday I finished wiring a PCB."
        )

        self.assertTrue(changed)
        self.assertEqual(
            "Yesterday you finished wiring a PCB.",
            fixed,
        )

    def test_first_person_state_is_conjugated(self):
        fixed, changed = repair_recall_perspective(
            "I was at Macy's yesterday."
        )

        self.assertTrue(changed)
        self.assertEqual(
            "You were at Macy's yesterday.",
            fixed,
        )

    def test_nancee_memory_statement_is_preserved(self):
        original = (
            "I remember you said you wired a PCB."
        )

        fixed, changed = repair_recall_perspective(
            original
        )

        self.assertFalse(changed)
        self.assertEqual(original, fixed)

    def test_memory_miss_statement_is_preserved(self):
        original = (
            "I don't remember that yet."
        )

        fixed, changed = repair_recall_perspective(
            original
        )

        self.assertFalse(changed)
        self.assertEqual(original, fixed)

    def test_stacked_casual_preface_is_removed(self):
        text = (
            "Yeah, hey man, I finished wiring "
            "a PCB yesterday."
        )

        self.assertEqual(
            "I finished wiring a PCB yesterday.",
            normalize_memory_candidate(text),
        )

        self.assertTrue(
            is_complete_memory_statement(text)
        )

    def test_prefaced_update_uses_acknowledge_mode(self):
        route = route_user_input(
            "Yeah, hey man, I finished wiring "
            "a PCB yesterday."
        )
        policy = response_policy_for_route(route.kind)

        self.assertEqual(
            "acknowledge",
            policy.name,
        )


if __name__ == "__main__":
    unittest.main()
