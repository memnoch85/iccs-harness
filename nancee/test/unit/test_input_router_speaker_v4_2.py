import unittest

from input_router import route_user_input


class InputRouterSpeakerV42Tests(unittest.TestCase):
    def test_current_speaker_query_bypasses_fts_recall(self):
        route = route_user_input(
            "Do you recall who's talking to you right now?"
        )
        self.assertEqual("speaker", route.kind)
        self.assertEqual("current_speaker_query", route.reason)
        self.assertFalse(route.retrieve_recall)
        self.assertFalse(route.explicit_recall)

    def test_past_wording_still_uses_current_speaker_state(self):
        route = route_user_input(
            "Do you remember who you were talking to?"
        )
        self.assertEqual("speaker", route.kind)

    def test_self_identity_wording_uses_speaker_state(self):
        for text in (
            "Who am I?",
            "Do you recall who I am?",
            "Do you remember who I am?",
            "What is my name?",
        ):
            with self.subTest(text=text):
                route = route_user_input(text)
                self.assertEqual("speaker", route.kind)
                self.assertEqual("current_speaker_query", route.reason)
                self.assertFalse(route.retrieve_recall)
                self.assertFalse(route.explicit_recall)

    def test_unrelated_who_question_remains_normal(self):
        route = route_user_input("Who invented the transistor?")
        self.assertEqual("normal", route.kind)

    def test_self_introduction_still_uses_normal_conversation_route(self):
        route = route_user_input(
            "Hi, this is Daniel. I like to cross-country ski. How are you?"
        )
        self.assertEqual("normal", route.kind)
        self.assertTrue(route.store_recall)

    def test_primary_return_routes_before_ambiguous_fragment(self):
        for text in (
            "I'm back.",
            "Okay, I'm back.",
            "All right, I'm back.",
            "So, I'm back.",
        ):
            with self.subTest(text=text):
                route = route_user_input(text)
                self.assertEqual("speaker_return", route.kind)
                self.assertEqual("primary_speaker_return", route.reason)
                self.assertFalse(route.retrieve_recall)
                self.assertFalse(route.explicit_recall)


if __name__ == "__main__":
    unittest.main()
