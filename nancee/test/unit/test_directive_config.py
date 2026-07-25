from __future__ import annotations

import unittest
from unittest.mock import patch

import response_policy


class DirectiveConfigTests(unittest.TestCase):
    def test_directive_uses_dedicated_generation_settings(self):
        with (
            patch.object(
                response_policy,
                "RESPONSE_DIRECTIVE_NUM_PREDICT",
                37,
            ),
            patch.object(
                response_policy,
                "RESPONSE_DIRECTIVE_TEMPERATURE",
                0.19,
            ),
        ):
            policy = response_policy.response_policy_for_route(
                "directive"
            )

        self.assertEqual(
            "directive",
            policy.name,
        )

        self.assertEqual(
            37,
            policy.num_predict,
        )

        self.assertAlmostEqual(
            0.19,
            policy.temperature,
        )


if __name__ == "__main__":
    unittest.main()
