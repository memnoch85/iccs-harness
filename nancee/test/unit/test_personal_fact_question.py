from __future__ import annotations

import ast
import unittest
from pathlib import Path

from input_router import route_user_input
from memory_policy import looks_like_personal_fact_question


class TestPersonalFactQuestion(unittest.TestCase):
    def test_stable_personal_attribute_questions_match(self):
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
                self.assertEqual(
                    "recall",
                    route_user_input(question).kind,
                )

    def test_diagnostic_questions_do_not_match(self):
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
                self.assertFalse(
                    route_user_input(question).explicit_recall
                )

    def test_router_calls_personal_question_helper(self):
        root = Path(__file__).resolve().parents[2]
        source_path = root / "sherpa/input_router.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))

        route_function = None

        for node in tree.body:
            if (
                isinstance(node, ast.FunctionDef)
                and node.name == "route_user_input"
            ):
                route_function = node
                break

        self.assertIsNotNone(route_function)

        called_names = {
            call.func.id
            for call in ast.walk(route_function)
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
            )
        }

        self.assertIn(
            "looks_like_personal_fact_question",
            called_names,
        )


if __name__ == "__main__":
    unittest.main()
