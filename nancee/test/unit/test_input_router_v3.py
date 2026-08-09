from __future__ import annotations

import unittest
from unittest.mock import patch

from input_router import route_user_input
from router_mon import RouterMonResult


class InputRouterV3Tests(unittest.TestCase):
    def router_result(
        self,
        intent: str,
        confidence: float = 0.80,
        source: str = "routerMon",
    ) -> RouterMonResult:
        return RouterMonResult(
            intent=intent,
            confidence=confidence,
            source=source,
        )

    def test_greetings_are_selected_by_routermon(self):
        samples = (
            "Hi",
            "Hello",
            "Hi Nancy",
            "Hello Maki Man",
            "Hello fuck face.",
        )

        for text in samples:
            with self.subTest(text=text):
                with patch(
                    "input_router.classify_router_mon",
                    return_value=self.router_result("greeting"),
                ) as classify:
                    route = route_user_input(text)

                classify.assert_called_once_with(text)
                self.assertEqual("greeting", route.kind)
                self.assertTrue(route.reason.startswith("routerMon:greeting:"))
                self.assertTrue(route.skip_latency_bridge)

    def test_long_hello_request_is_not_forced_to_greeting(self):
        text = "Hello, explain step by step how a database index works."

        with patch(
            "input_router.classify_router_mon",
            return_value=self.router_result("detailed"),
        ) as classify:
            route = route_user_input(text)

        classify.assert_called_once_with(text)
        self.assertEqual("detailed", route.kind)

    def test_model_recall_is_distinct_from_user_recall(self):
        with patch(
            "input_router.classify_router_mon",
            return_value=self.router_result("model_recall"),
        ):
            model_route = route_user_input(
                "What did you say about prefix caching?"
            )

        with patch(
            "input_router.classify_router_mon",
            return_value=self.router_result("recall"),
        ):
            user_route = route_user_input(
                "What did I say about prefix caching?"
            )

        self.assertEqual("model_recall", model_route.kind)
        self.assertFalse(model_route.retrieve_recall)
        self.assertEqual("recall", user_route.kind)
        self.assertTrue(user_route.retrieve_recall)
        self.assertTrue(user_route.explicit_recall)

    def test_question_preserves_existing_background_enrichment(self):
        with patch(
            "input_router.classify_router_mon",
            return_value=self.router_result("question"),
        ):
            route = route_user_input("What is the capital of France?")

        self.assertEqual("question", route.kind)
        self.assertTrue(route.retrieve_recall)
        self.assertFalse(route.explicit_recall)
        self.assertFalse(route.allow_weak_match)

    def test_detailed_route_can_store_declarative_user_memory(self):
        text = (
            "Finch is from Michigan and plays guitar. "
            "They mostly listen to metal and recently moved here."
        )

        with patch(
            "input_router.classify_router_mon",
            return_value=self.router_result("detailed"),
        ):
            route = route_user_input(text)

        self.assertEqual("detailed", route.kind)
        self.assertTrue(route.store_recall)
        self.assertIsNotNone(route.recall_storage_text)

    def test_memory_store_route_extracts_command_payload_after_classification(self):
        text = "Remember that I want the greeting path to stay fast."

        with patch(
            "input_router.classify_router_mon",
            return_value=self.router_result("memory_store"),
        ) as classify:
            route = route_user_input(text)

        classify.assert_called_once_with(text)
        self.assertEqual("memory_store", route.kind)
        self.assertTrue(route.store_recall)
        self.assertEqual(
            "I want the greeting path to stay fast.",
            route.recall_storage_text,
        )

    def test_memory_store_route_can_carry_fact_correction_metadata(self):
        text = "Actually, it was the power board, not the USB controller."

        with patch(
            "input_router.classify_router_mon",
            return_value=self.router_result("memory_store"),
        ) as classify:
            route = route_user_input(text)

        classify.assert_called_once_with(text)
        self.assertEqual("memory_store", route.kind)
        self.assertEqual(("the power board", "the USB controller"), route.correction)
        self.assertFalse(route.store_recall)

    def test_contextual_answer_keeps_routermon_route_and_adds_memory_metadata(self):
        text = "Sure."

        with patch(
            "input_router.classify_router_mon",
            return_value=self.router_result("affirmative"),
        ) as classify:
            route = route_user_input(
                text,
                previous_turn={
                    "user": "Ask me whether I finished wiring the power board.",
                    "assistant": "Did you finish wiring the power board?",
                },
            )

        classify.assert_called_once_with(text)
        self.assertEqual("affirmative", route.kind)
        self.assertTrue(route.store_recall)
        self.assertEqual(
            "I did finish wiring the power board.",
            route.recall_storage_text,
        )

    def test_affirmative_negative_and_farewell_are_selected_by_routermon(self):
        samples = {
            "Yeah.": "affirmative",
            "Nope.": "negative",
            "ttyl": "farewell",
        }

        for text, expected in samples.items():
            with self.subTest(text=text):
                with patch(
                    "input_router.classify_router_mon",
                    return_value=self.router_result(expected),
                ) as classify:
                    route = route_user_input(text)

                classify.assert_called_once_with(text)
                self.assertEqual(expected, route.kind)
                self.assertTrue(route.reason.startswith(f"routerMon:{expected}:"))

    def test_directive_is_selected_by_routermon(self):
        text = "Hey Becca, ask me what I bought yesterday."

        with patch(
            "input_router.classify_router_mon",
            return_value=self.router_result("directive"),
        ) as classify:
            route = route_user_input(text)

        classify.assert_called_once_with(text)
        self.assertEqual("directive", route.kind)

    def test_normal_personal_statement_can_still_store_user_memory(self):
        with patch(
            "input_router.classify_router_mon",
            return_value=self.router_result("normal"),
        ):
            route = route_user_input("My sister lives in Boise.")

        self.assertEqual("normal", route.kind)
        self.assertTrue(route.store_recall)
        self.assertEqual("My sister lives in Boise.", route.recall_storage_text)


if __name__ == "__main__":
    unittest.main()
