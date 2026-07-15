from __future__ import annotations

import unittest

from response_policy import (
    looks_like_directive,
    select_response_policy,
)


class DirectedRequestPolicyTests(unittest.TestCase):
    def assert_directive(self, text):
        policy = select_response_policy(text)

        self.assertTrue(
            looks_like_directive(text)
        )

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

        self.assertIn(
            "For ask-me commands, output only ""the question.",
            policy.instruction,
        )

    def test_direct_ask_request(self):
        self.assert_directive(
            "Ask me whether I finished wiring "
            "the power board."
        )

    def test_direct_ask_without_me(self):
        self.assert_directive(
            "Ask whether the CAN hat is connected."
        )

    def test_structural_you_to_request(self):
        self.assert_directive(
            "I want you to ask me whether "
            "the CAN hat is connected."
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
        policy = select_response_policy(
            "Explain step by step how a turbocharger works."
        )

        self.assertEqual(
            "detailed",
            policy.name,
        )

    def test_real_personal_update_still_acknowledges(self):
        policy = select_response_policy(
            "I finished wiring the power board today."
        )

        self.assertEqual(
            "acknowledge",
            policy.name,
        )

    def test_contextual_answer_is_not_a_directive(self):
        policy = select_response_policy(
            "I sure did."
        )

        self.assertNotEqual(
            "directive",
            policy.name,
        )


if __name__ == "__main__":
    unittest.main()
