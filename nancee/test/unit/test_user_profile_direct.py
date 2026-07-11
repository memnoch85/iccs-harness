import unittest

from user_profile import UserProfile


class TestUserProfileDirect(unittest.TestCase):
    def test_direct_name_answer(self):
        profile = UserProfile(
            {
                "name": "Anders",
                "vehicle": "black Jeep",
            }
        )

        self.assertEqual(
            profile.direct_answer("What is my name?"),
            "Your name is Anders.",
        )

    def test_direct_vehicle_answer(self):
        profile = UserProfile(
            {
                "name": "Anders",
                "vehicle": "black Jeep",
            }
        )

        self.assertEqual(
            profile.direct_answer("What vehicle do I have?"),
            "You drive a black Jeep.",
        )

    def test_unknown_profile_question_returns_empty(self):
        profile = UserProfile(
            {
                "name": "Anders",
                "vehicle": "black Jeep",
            }
        )

        self.assertEqual(
            profile.direct_answer("What is my favorite color?"),
            "",
        )


if __name__ == "__main__":
    unittest.main()
