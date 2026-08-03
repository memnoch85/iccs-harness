from __future__ import annotations

import unittest

from response_policy import response_policy_for_route


class ResponsePolicyRouterV3Tests(unittest.TestCase):
    def test_route_names_map_without_reclassifying_text(self):
        expected = {
            "greeting": "greeting",
            "acknowledge": "acknowledge",
            "directive": "directive",
            "clarify": "clarify",
            "detailed": "detailed",
            "normal": "normal",
            "recall": "recall",
        }

        for route_kind, policy_name in expected.items():
            with self.subTest(route=route_kind):
                self.assertEqual(
                    policy_name,
                    response_policy_for_route(route_kind).name,
                )

    def test_explicit_fact_miss_uses_recall_policy(self):
        policy = response_policy_for_route("normal", fact_miss=True)
        self.assertEqual("recall", policy.name)

    def test_normal_policy_adds_no_dynamic_instruction(self):
        policy = response_policy_for_route("normal")
        self.assertEqual("", policy.instruction)

if __name__ == "__main__":
    unittest.main()
