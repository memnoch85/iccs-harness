from __future__ import annotations

import unittest
from unittest.mock import patch

from input_router import route_user_input
from memory_policy import looks_like_personal_fact_question
from router_mon import RouterMonResult


class TestPersonalFactQuestion(unittest.TestCase):
    def test_memory_policy_helper_still_identifies_stable_personal_questions(self):
        matching_questions = (
            "What color is my helicopter?",
            "What colour is my controller?",
            "What model is my phone?",
            "What make is our laptop?",
            "Which version is my controller?",
            "What's the brand of my laptop?",
            "What is the color of my power board?",
        )

        for question in matching_questions:
            with self.subTest(question=question):
                self.assertTrue(
                    looks_like_personal_fact_question(question)
                )

    def test_diagnostic_questions_do_not_match_memory_policy_helper(self):
        nonmatching_questions = (
            "Why is my application crashing?",
            "How do I fix my printer?",
            "What temperature is my laptop running?",
            "What voltage is my power supply producing?",
            "Is my keyboard broken?",
            "Why is my status light flashing?",
            "What color should printer ink be?",
        )

        for question in nonmatching_questions:
            with self.subTest(question=question):
                self.assertFalse(
                    looks_like_personal_fact_question(question)
                )

    def test_routermon_now_owns_semantic_personal_recall_classification(self):
        with patch(
            "input_router.classify_router_mon",
            return_value=RouterMonResult("recall", 0.9, "routerMon"),
        ):
            route = route_user_input("What color is my helicopter?")

        self.assertEqual("recall", route.kind)
        self.assertTrue(route.explicit_recall)
        self.assertTrue(route.retrieve_recall)


if __name__ == "__main__":
    unittest.main()
