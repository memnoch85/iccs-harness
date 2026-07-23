from __future__ import annotations

import unittest

from input_router import route_user_input
from response_policy import response_policy_for_route


class DirectedRequestPolicyTests(unittest.TestCase):
    def assert_directive(self, text):
        route = route_user_input(text)
        policy = response_policy_for_route(route.kind)

        self.assertEqual("directive", route.kind)
        self.assertEqual("directive", policy.name)
        self.assertFalse(policy.drop_history)
        self.assertIn(
            "Preserve nouns, articles, and ownership",
            policy.instruction,
        )
        self.assertIn(
            "For ask-me commands, output only the question.",
            policy.instruction,
        )

    def test_direct_ask_request(self):
        self.assert_directive(
            "Ask me whether I finished wiring the power board."
        )

    def test_direct_ask_without_me(self):
        self.assert_directive(
            "Ask whether the CAN hat is connected."
        )

    def test_structural_you_to_request(self):
        self.assert_directive(
            "I want you to ask me whether the CAN hat is connected."
        )

    def test_other_existing_commands_are_directives(self):
        samples = (
            "Tell me a joke.",
            "Show me the current vehicle status.",
            "Remind me to check the fuse.",
            "Name France's capital.",
        )

        for text in samples:
            with self.subTest(text=text):
                self.assert_directive(text)

    def test_detailed_request_keeps_detailed_route(self):
        route = route_user_input(
            "Explain step by step how a turbocharger works."
        )
        self.assertEqual("detailed", route.kind)

    def test_real_personal_update_still_acknowledges(self):
        route = route_user_input(
            "I finished wiring the power board today."
        )
        self.assertEqual("acknowledge", route.kind)

    def test_contextual_answer_is_not_a_directive(self):
        route = route_user_input("I sure did.")
        self.assertNotEqual("directive", route.kind)


if __name__ == "__main__":
    unittest.main()
