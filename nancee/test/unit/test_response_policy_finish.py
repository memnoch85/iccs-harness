import unittest

from response_policy import response_policy_for_route


class ResponsePolicyFinishTests(unittest.TestCase):
    def test_detailed_route_keeps_detailed_policy(self):
        self.assertEqual(
            "detailed",
            response_policy_for_route("detailed").name,
        )

    def test_directive_route_keeps_directive_policy(self):
        self.assertEqual(
            "directive",
            response_policy_for_route("directive").name,
        )

    def test_question_route_uses_normal_generation_policy(self):
        policy = response_policy_for_route("question")
        self.assertEqual("normal", policy.name)
        self.assertEqual("", policy.instruction)

    def test_affirmative_and_negative_use_acknowledge_policy(self):
        for route in ("affirmative", "negative"):
            with self.subTest(route=route):
                self.assertEqual(
                    "acknowledge",
                    response_policy_for_route(route).name,
                )


if __name__ == "__main__":
    unittest.main()
