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

    def test_short_hello_or_hi_is_hard_greeting_without_bridge(self):
        samples = (
            "Hi",
            "Hello",
            "Hi Nancy",
            "Hello Maki Man",
            "Hello fuck face.",
        )

        for text in samples:
            with self.subTest(text=text):
                with patch("input_router.classify_router_mon") as classify:
                    route = route_user_input(text)

                classify.assert_not_called()
                self.assertEqual("greeting", route.kind)
                self.assertEqual("leading_hello_or_hi", route.reason)
                self.assertTrue(route.skip_latency_bridge)

    def test_long_hello_request_goes_to_routermon(self):
        with patch(
            "input_router.classify_router_mon",
            return_value=self.router_result("detailed"),
        ) as classify:
            route = route_user_input(
                "Hello, explain step by step how a database index works."
            )

        self.assertEqual("detailed", route.kind)
        self.assertFalse(route.skip_latency_bridge)
        classify.assert_called_once()
        self.assertNotIn("hello", classify.call_args.args[0].lower())

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

    def test_detailed_overshare_can_store_declarative_user_memory(self):
        text = (
            "Finch is from Michigan and plays guitar. "
            "They mostly listen to metal and recently moved here."
        )

        with patch(
            "input_router.classify_router_mon",
            return_value=self.router_result(
                "detailed",
                confidence=1.0,
                source="overshare_rule",
            ),
        ):
            route = route_user_input(text)

        self.assertEqual("detailed", route.kind)
        self.assertTrue(route.store_recall)
        self.assertIsNotNone(route.recall_storage_text)

    def test_explicit_memory_store_is_fast_and_extracts_payload(self):
        with patch("input_router.classify_router_mon") as classify:
            route = route_user_input(
                "Remember that I want the greeting path to stay fast."
            )

        classify.assert_not_called()
        self.assertEqual("memory_store", route.kind)
        self.assertTrue(route.store_recall)
        self.assertEqual(
            "I want the greeting path to stay fast.",
            route.recall_storage_text,
        )

    def test_contextual_yes_beats_fast_affirmative(self):
        with patch("input_router.classify_router_mon") as classify:
            route = route_user_input(
                "Sure.",
                previous_turn={
                    "user": "Ask me whether I finished wiring the power board.",
                    "assistant": "Did you finish wiring the power board?",
                },
            )

        classify.assert_not_called()
        self.assertEqual("clarify", route.kind)
        self.assertEqual("contextual_answer", route.reason)
        self.assertTrue(route.store_recall)
        self.assertEqual(
            "I did finish wiring the power board.",
            route.recall_storage_text,
        )

    def test_obvious_fast_affirmative_negative_and_farewell(self):
        samples = {
            "Yeah.": "affirmative",
            "Nope.": "negative",
            "ttyl": "farewell",
        }

        for text, expected in samples.items():
            with self.subTest(text=text):
                with patch("input_router.classify_router_mon") as classify:
                    route = route_user_input(text)

                classify.assert_not_called()
                self.assertEqual(expected, route.kind)

    def test_directive_is_selected_by_routermon(self):
        with patch(
            "input_router.classify_router_mon",
            return_value=self.router_result("directive"),
        ):
            route = route_user_input(
                "Hey Becca, ask me what I bought yesterday."
            )

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
