import unittest
from unittest.mock import patch

from input_router import route_user_input
from response_policy import response_policy_for_route
from router_mon import RouterMonResult


class ResponsePolicyTests(unittest.TestCase):
    @staticmethod
    def policy_for_intent(intent, text="test"):
        with patch(
            "input_router.classify_router_mon",
            return_value=RouterMonResult(intent, 0.9, "routerMon"),
        ):
            route = route_user_input(text)

        return response_policy_for_route(route.kind)

    def test_routermon_greeting_is_short(self):
        with patch(
            "input_router.classify_router_mon",
            return_value=RouterMonResult("greeting", 0.9, "routerMon"),
        ):
            route = route_user_input("Hello friend")

        policy = response_policy_for_route(route.kind)
        self.assertEqual("greeting", policy.name)
        self.assertTrue(route.skip_latency_bridge)

    def test_semantic_greeting_is_short(self):
        policy = self.policy_for_intent(
            "greeting",
            "Hey, how are things going today?",
        )
        self.assertEqual("greeting", policy.name)

    def test_normal_personal_update_uses_normal_policy(self):
        policy = self.policy_for_intent(
            "normal",
            "I finished wiring a power board today.",
        )
        self.assertEqual("normal", policy.name)

    def test_memory_store_uses_acknowledge_policy(self):
        with patch(
            "input_router.classify_router_mon",
            return_value=RouterMonResult("memory_store", 0.9, "routerMon"),
        ):
            route = route_user_input(
                "Remember that I bought a blue backpack at Macy's."
            )

        policy = response_policy_for_route(route.kind)
        self.assertEqual("memory_store", route.kind)
        self.assertEqual("acknowledge", policy.name)

    def test_detailed_uses_existing_detailed_policy(self):
        policy = self.policy_for_intent(
            "detailed",
            "Explain step by step how a database index works.",
        )
        self.assertEqual("detailed", policy.name)

    def test_question_uses_normal_policy_without_instruction(self):
        policy = self.policy_for_intent(
            "question",
            "What is the capital of France?",
        )
        self.assertEqual("normal", policy.name)
        self.assertEqual("", policy.instruction)

    def test_recall_route_selects_recall_policy(self):
        policy = response_policy_for_route(
            "recall",
            authoritative_context_found=True,
        )
        self.assertEqual("recall", policy.name)
        self.assertFalse(policy.drop_history)
        self.assertTrue(policy.instruction.strip())


if __name__ == "__main__":
    unittest.main()
