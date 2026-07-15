from __future__ import annotations

import unittest

from response_policy import select_response_policy


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
                policy = select_response_policy(request)

                self.assertEqual(
                    "directive",
                    policy.name,
                )

                self.assertFalse(
                    policy.drop_history,
                )

                self.assertIn(
                    "Preserve nouns, articles, and ownership",
                    policy.instruction,
                )

    def test_actual_personal_update_still_acknowledges(self):
        policy = select_response_policy(
            "I finished wiring the power board today."
        )

        self.assertEqual(
            "acknowledge",
            policy.name,
        )

    def test_contextual_answer_is_not_directive(self):
        policy = select_response_policy(
            "I sure did."
        )

        self.assertNotEqual(
            "directive",
            policy.name,
        )


if __name__ == "__main__":
    unittest.main()
