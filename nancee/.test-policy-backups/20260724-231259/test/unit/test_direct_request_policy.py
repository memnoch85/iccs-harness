from __future__ import annotations

import unittest

from input_router import route_user_input
from response_policy import response_policy_for_route


class DirectRequestPolicyTests(unittest.TestCase):
    def test_direct_ask_commands_route_directive(self):
        requests = (
            "Ask me whether I finished wiring the power board.",
            "Ask whether I finished wiring the power board.",
            (
                "Nancee, I want you to ask me whether "
                "I finished wiring the power board."
            ),
            (
                "I need you to ask me if I finished "
                "wiring the power board."
            ),
            (
                "I would like you to ask me whether "
                "I finished wiring the power board."
            ),
            (
                "I'd like you to ask me whether "
                "I finished wiring the power board."
            ),
        )

        for request in requests:
            with self.subTest(request=request):
                route = route_user_input(request)
                policy = response_policy_for_route(route.kind)

                self.assertEqual("directive", route.kind)
                self.assertEqual("directive", policy.name)
                self.assertFalse(policy.drop_history)
                self.assertIn(
                    "Preserve nouns, articles, and ownership",
                    policy.instruction,
                )

    def test_actual_personal_update_still_acknowledges(self):
        route = route_user_input("I finished wiring the power board today.")
        policy = response_policy_for_route(route.kind)
        self.assertEqual("acknowledge", policy.name)

    def test_contextual_answer_is_not_directive(self):
        route = route_user_input("I sure did.")
        self.assertNotEqual("directive", route.kind)


if __name__ == "__main__":
    unittest.main()
