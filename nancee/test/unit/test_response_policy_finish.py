import unittest

from input_router import route_user_input
from response_policy import response_policy_for_route


class ResponsePolicyFinishTests(unittest.TestCase):
    def assert_policy(self, text, expected):
        route = route_user_input(text)
        policy = response_policy_for_route(route.kind)
        self.assertEqual(policy.name, expected)

    def test_sauron_relationship_routes_detailed(self):
        self.assert_policy(
            "Who was Sauron, and what was his relationship to Morgoth?",
            "detailed",
        )

    def test_asr_explaining_exact_sentences_routes_detailed(self):
        self.assert_policy(
            "Explaining exactly two complete sentences, how turbochargers work.",
            "detailed",
        )

    def test_short_explain_is_not_misclassified_as_fragment(self):
        self.assert_policy(
            "Explain quantum entanglement.",
            "detailed",
        )

    def test_name_command_routes_directive(self):
        self.assert_policy(
            "Name France's capital.",
            "directive",
        )

    def test_hardly_drive_still_routes_clarify(self):
        self.assert_policy(
            "Hardly drive.",
            "clarify",
        )

    def test_simple_fact_stays_normal(self):
        self.assert_policy(
            "What is the capital of France?",
            "normal",
        )


if __name__ == "__main__":
    unittest.main()
