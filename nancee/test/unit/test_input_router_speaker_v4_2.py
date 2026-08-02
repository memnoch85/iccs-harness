import unittest

from input_router import route_user_input


class InputRouterSpeakerV42Tests(unittest.TestCase):



    def test_unrelated_who_question_remains_normal(self):
        route = route_user_input("Who invented the transistor?")
        self.assertEqual("normal", route.kind)

    def test_leading_hi_is_unconditionally_a_greeting(self):
        route = route_user_input(
            "Hi, this is Daniel. I like to cross-country ski. How are you?"
        )
        self.assertEqual("greeting", route.kind)
        self.assertEqual("leading_hello_or_hi", route.reason)
        self.assertFalse(route.store_recall)



if __name__ == "__main__":
    unittest.main()
