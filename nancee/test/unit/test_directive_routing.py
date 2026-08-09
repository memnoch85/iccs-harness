from __future__ import annotations

import unittest
from unittest.mock import patch

from input_router import route_user_input
from response_policy import response_policy_for_route
from router_mon import RouterMonResult


class DirectiveRoutingTests(unittest.TestCase):
    def assert_directive(self, text: str) -> None:
        with patch(
            "input_router.classify_router_mon",
            return_value=RouterMonResult("directive", 0.9, "routerMon"),
        ):
            route = route_user_input(text)

        policy = response_policy_for_route(route.kind)

        self.assertEqual("directive", route.kind)
        self.assertEqual("directive", policy.name)
        self.assertFalse(policy.drop_history)

    def test_direct_ask_variants_route_directive(self):
        requests = (
            "Ask me whether I finished wiring the power board.",
            "Ask whether I finished wiring the power board.",
            "Nancee, I want you to ask me whether I finished wiring the power board.",
            "I need you to ask me if I finished wiring the power board.",
            "I would like you to ask me whether I finished wiring the power board.",
            "I'd like you to ask me whether I finished wiring the power board.",
            "Hey Becca, ask me what I bought yesterday.",
        )

        for request in requests:
            with self.subTest(request=request):
                self.assert_directive(request)

    def test_ask_me_directive_carries_pending_memory_topic(self):
        with patch(
            "input_router.classify_router_mon",
            return_value=RouterMonResult("directive", 0.9, "routerMon"),
        ):
            route = route_user_input(
                "Hey Becca, ask me what I bought at the store yesterday."
            )

        self.assertEqual("directive", route.kind)
        self.assertEqual(
            "what I bought at the store yesterday",
            route.pending_memory_topic,
        )

    def test_non_ask_directive_has_no_pending_memory_topic(self):
        with patch(
            "input_router.classify_router_mon",
            return_value=RouterMonResult("directive", 0.9, "routerMon"),
        ):
            route = route_user_input("Run the benchmark again.")

        self.assertEqual("directive", route.kind)
        self.assertIsNone(route.pending_memory_topic)

    def test_other_commands_route_directive(self):
        requests = (
            "Tell me a joke.",
            "Show me the current project status.",
            "Remind me to check the fuse.",
            "Name France's capital.",
        )

        for request in requests:
            with self.subTest(request=request):
                self.assert_directive(request)

    def test_contextual_answer_keeps_classifier_route(self):
        with patch(
            "input_router.classify_router_mon",
            return_value=RouterMonResult("affirmative", 0.9, "routerMon"),
        ):
            route = route_user_input(
                "I sure did.",
                previous_turn={
                    "user": "Ask me whether I finished wiring the power board.",
                    "assistant": "Did you finish wiring the power board?",
                },
            )

        self.assertEqual("affirmative", route.kind)
        self.assertTrue(route.store_recall)


if __name__ == "__main__":
    unittest.main()
