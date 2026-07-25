from __future__ import annotations

import unittest

from response_policy import response_policy_for_route


class ResponsePolicyHistoryTests(unittest.TestCase):
    def test_every_route_keeps_one_turn_history_by_default(self):
        route_names = (
            "greeting",
            "acknowledge",
            "detailed",
            "clarify",
            "normal",
            "recall",
            "directive",
        )

        for route_name in route_names:
            with self.subTest(route=route_name):
                policy = response_policy_for_route(route_name)
                self.assertEqual(route_name, policy.name)
                self.assertFalse(policy.drop_history)


if __name__ == "__main__":
    unittest.main()
