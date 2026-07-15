from __future__ import annotations

import unittest

from response_policy import select_response_policy


class ResponsePolicyHistoryTests(unittest.TestCase):
    def test_every_route_keeps_one_turn_history(self):
        cases = (
            (
                "greeting",
                select_response_policy(
                    "Hello Nancee."
                ),
            ),
            (
                "acknowledge",
                select_response_policy(
                    "I finished wiring my power board."
                ),
            ),
            (
                "detailed",
                select_response_policy(
                    "Explain step by step how a turbo works."
                ),
            ),
            (
                "clarify",
                select_response_policy(
                    "Hardly drive."
                ),
            ),
            (
                "normal",
                select_response_policy(
                    "What is the capital of France?"
                ),
            ),
            (
                "recall",
                select_response_policy(
                    "What did I buy yesterday?",
                    authoritative_context_found=True,
                ),
            ),
        )

        for expected_name, policy in cases:
            with self.subTest(
                route=expected_name
            ):
                self.assertEqual(
                    expected_name,
                    policy.name,
                )

                self.assertFalse(
                    policy.drop_history,
                )


if __name__ == "__main__":
    unittest.main()
