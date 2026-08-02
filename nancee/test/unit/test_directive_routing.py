from __future__ import annotations

import unittest

from input_router import route_user_input
from response_policy import response_policy_for_route


class DirectiveRoutingTests(unittest.TestCase):
    def assert_directive(self, text: str) -> None:
        route = route_user_input(text)
        policy = response_policy_for_route(route.kind)

        self.assertEqual("directive", route.kind)
        self.assertEqual("directive", policy.name)
        self.assertFalse(policy.drop_history)

    def test_direct_ask_variants_route_directive(self):
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
                self.assert_directive(request)

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

    def test_detailed_request_keeps_detailed_route(self):
        route = route_user_input(
            "Explain step by step how a database index works."
        )
        self.assertEqual("detailed", route.kind)

    def test_personal_update_still_acknowledges(self):
        route = route_user_input(
            "I finished wiring the power board today."
        )
        self.assertEqual("acknowledge", route.kind)

    def test_contextual_answer_is_not_directive(self):
        route = route_user_input("I sure did.")
        self.assertNotEqual("directive", route.kind)


if __name__ == "__main__":
    unittest.main()
