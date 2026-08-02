import unittest

from input_router import route_user_input


class InputRouterSpeakerV42Tests(unittest.TestCase):



    def test_unrelated_who_question_remains_normal(self):
        route = route_user_input("Who invented the transistor?")
        self.assertEqual("normal", route.kind)

    def test_self_introduction_still_uses_normal_conversation_route(self):
        route = route_user_input(
            "Hi, this is Daniel. I like to cross-country ski. How are you?"
        )
        self.assertEqual("normal", route.kind)
        self.assertTrue(route.store_recall)



if __name__ == "__main__":
    unittest.main()
