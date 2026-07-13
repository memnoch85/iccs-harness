import unittest

from response_policy import select_response_policy


class ResponsePolicyTests(unittest.TestCase):
    def test_plain_greeting_is_short(self):
        policy = select_response_policy(
            "Hello Nancee, how are you?"
        )
        self.assertEqual("greeting", policy.name)

    def test_greeting_preface_does_not_hide_purchase(self):
        policy = select_response_policy(
            "Hey, Nancy, I bought a blue backpack at Macy's."
        )
        self.assertEqual("acknowledge", policy.name)
        self.assertEqual(18, policy.num_predict)
        self.assertAlmostEqual(0.25, policy.temperature)
        self.assertTrue(policy.drop_history)

    def test_name_preface_does_not_hide_detailed_request(self):
        policy = select_response_policy(
            "Nancy, explain step by step how a turbocharger works."
        )
        self.assertEqual("detailed", policy.name)

    def test_finished_wiring_is_acknowledgment(self):
        policy = select_response_policy(
            "I finished wiring a power board today."
        )
        self.assertEqual("acknowledge", policy.name)

    def test_missing_i_action_is_acknowledgment(self):
        policy = select_response_policy(
            "Bought a blue backpack at Macy's."
        )
        self.assertEqual("acknowledge", policy.name)

    def test_ambiguous_fragment_requests_clarification(self):
        policy = select_response_policy("Hardly drive.")
        self.assertEqual("clarify", policy.name)

    def test_recall_instruction_forbids_inference(self):
        policy = select_response_policy(
            "What did I buy yesterday?",
            authoritative_context_found=True,
        )
        self.assertEqual("recall", policy.name)
        self.assertIn("Never infer", policy.instruction)


if __name__ == "__main__":
    unittest.main()

