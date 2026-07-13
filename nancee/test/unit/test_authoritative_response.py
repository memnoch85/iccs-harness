import unittest

from authoritative_response import prepare_authoritative_response
from profile_fact_index import ProfileFactHit


class AuthoritativeResponseTests(unittest.TestCase):
    def test_correct_name_answer_is_trimmed_to_one_sentence(self):
        answer, action = prepare_authoritative_response(
            "Your name is Anders. How can I assist you further today?",
            profile_hits=[ProfileFactHit("name", "Anders", -1.0)],
            fact_miss=False,
        )

        self.assertEqual(answer, "Your name is Anders.")
        self.assertEqual(action, "accepted")

    def test_wrong_name_answer_is_replaced(self):
        answer, action = prepare_authoritative_response(
            "Your name is Nancee. How can I assist you further today?",
            profile_hits=[ProfileFactHit("name", "Anders", -1.0)],
            fact_miss=False,
        )

        self.assertEqual(answer, "You're Anders.")
        self.assertEqual(action, "profile_fallback")

    def test_vehicle_answer_must_contain_confirmed_value(self):
        answer, action = prepare_authoritative_response(
            "You barely drive.",
            profile_hits=[ProfileFactHit("vehicle", "black Jeep", -1.0)],
            fact_miss=False,
        )

        self.assertEqual(answer, "You drive a black Jeep.")
        self.assertEqual(action, "profile_fallback")

    def test_fact_miss_drops_guessing_second_sentence(self):
        answer, action = prepare_authoritative_response(
            "I don't remember that yet. Could it be Anna?",
            profile_hits=[],
            fact_miss=True,
        )

        self.assertEqual(answer, "I don't remember that yet.")
        self.assertEqual(action, "fact_miss_accepted")

    def test_invalid_fact_miss_uses_safe_fallback(self):
        answer, action = prepare_authoritative_response(
            "Maybe her name is Anna.",
            profile_hits=[],
            fact_miss=True,
        )

        self.assertEqual(answer, "I don't remember that yet.")
        self.assertEqual(action, "fact_miss_fallback")


if __name__ == "__main__":
    unittest.main()
