import unittest

from input_router import route_user_input
from response_policy import response_policy_for_route


class ResponsePolicyTests(unittest.TestCase):
    @staticmethod
    def policy_for(text, *, authoritative_context_found=False, fact_miss=False):
        route = route_user_input(text)
        return response_policy_for_route(
            route.kind,
            authoritative_context_found=authoritative_context_found,
            fact_miss=fact_miss,
        )

    def test_plain_greeting_is_short(self):
        policy = self.policy_for(
            "Hello Nancee, how are you?"
        )
        self.assertEqual("greeting", policy.name)

    def test_greeting_preface_does_not_hide_purchase(self):
        policy = self.policy_for(
            "Hey, Nancy, I bought a blue backpack at Macy's."
        )
        self.assertEqual("acknowledge", policy.name)
        self.assertEqual(18, policy.num_predict)
        self.assertAlmostEqual(0.25, policy.temperature)
        self.assertFalse(policy.drop_history)

    def test_name_preface_does_not_hide_detailed_request(self):
        policy = self.policy_for(
            "Nancy, explain step by step how a turbocharger works."
        )
        self.assertEqual("detailed", policy.name)

    def test_finished_wiring_is_acknowledgment(self):
        policy = self.policy_for(
            "I finished wiring a power board today."
        )
        self.assertEqual("acknowledge", policy.name)

    def test_missing_i_action_is_acknowledgment(self):
        policy = self.policy_for(
            "Bought a blue backpack at Macy's."
        )
        self.assertEqual("acknowledge", policy.name)

    def test_ambiguous_fragment_requests_clarification(self):
        policy = self.policy_for("Hardly drive.")
        self.assertEqual("clarify", policy.name)

    def test_recall_instruction_forbids_inference(self):
        policy = self.policy_for(
            "What did I buy yesterday?",
            authoritative_context_found=True,
        )
        self.assertEqual("recall", policy.name)
        self.assertIn("Never infer", policy.instruction)


if __name__ == "__main__":
    unittest.main()
