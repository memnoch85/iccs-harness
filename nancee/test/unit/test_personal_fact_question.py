from __future__ import annotations

import ast
import unittest
from pathlib import Path

from memory_policy import looks_like_personal_fact_question


class TestPersonalFactQuestion(unittest.TestCase):
    def test_stable_personal_attribute_questions_match(self):
        matching_questions = (
            "What color is my helicopter?",
            "What colour is my truck?",
            "What model is my phone?",
            "What make is our car?",
            "Which version is my controller?",
            "What's the brand of my laptop?",
            "What is the color of my power board?",
        )

        for question in matching_questions:
            with self.subTest(question=question):
                self.assertTrue(
                    looks_like_personal_fact_question(
                        question
                    )
                )

    def test_diagnostic_questions_do_not_match(self):
        nonmatching_questions = (
            "Why is my engine overheating?",
            "How do I fix my transmission?",
            "What temperature is my engine running?",
            "What voltage is my battery producing?",
            "Is my battery bad?",
            "Why is my warning light flashing?",
            "What color should engine oil be?",
        )

        for question in nonmatching_questions:
            with self.subTest(question=question):
                self.assertFalse(
                    looks_like_personal_fact_question(
                        question
                    )
                )

    def test_recall_router_calls_personal_question_helper(self):
        root = Path(__file__).resolve().parents[2]
        source_path = root / "sherpa/nancee_chat.py"

        tree = ast.parse(
            source_path.read_text(
                encoding="utf-8",
            )
        )

        recall_function = None

        for node in tree.body:
            if (
                isinstance(node, ast.FunctionDef)
                and node.name == "looks_like_recall_request"
            ):
                recall_function = node
                break

        self.assertIsNotNone(
            recall_function,
            "looks_like_recall_request was not found.",
        )

        called_names = {
            call.func.id
            for call in ast.walk(recall_function)
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
