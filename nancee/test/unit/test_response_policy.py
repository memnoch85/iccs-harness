import unittest

from response_policy import select_response_policy


class ResponsePolicyTests(unittest.TestCase):
    def test_greeting_is_short(self):
        policy = select_response_policy(
            "Hello Nancee, how are you?"
        )

        self.assertEqual("greeting", policy.name)
        self.assertLessEqual(policy.num_predict, 20)

    def test_simple_purchase_is_acknowledgment(self):
        policy = select_response_policy(
            "I bought a blue backpack yesterday at Macy's."
        )

        self.assertEqual("acknowledge", policy.name)
        self.assertTrue(policy.drop_history)
        self.assertLessEqual(policy.num_predict, 24)

    def test_simple_update_does_not_request_followup(self):
        policy = select_response_policy(
            "I finished the wiring today."
        )

        self.assertIn(
            "do not ask a follow-up",
            policy.instruction.lower(),
        )

    def test_detailed_question_gets_full_budget(self):
        policy = select_response_policy(
            "Explain step by step how a turbocharger works."
        )

        self.assertEqual("detailed", policy.name)
        self.assertGreaterEqual(policy.num_predict, 55)

    def test_authoritative_fact_uses_recall_mode(self):
        policy = select_response_policy(
            "What is my name?",
            authoritative_context_found=True,
        )

        self.assertEqual("recall", policy.name)
        self.assertTrue(policy.drop_history)

    def test_short_malformed_fragment_requests_clarification(self):
        policy = select_response_policy(
            "Hardly drive."
        )

        self.assertEqual("clarify", policy.name)
        self.assertTrue(policy.drop_history)

    def test_normal_question_remains_normal(self):
        policy = select_response_policy(
            "What is the capital of France?"
        )

        self.assertEqual("normal", policy.name)


if __name__ == "__main__":
    unittest.main()
