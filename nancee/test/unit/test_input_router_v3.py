from __future__ import annotations

import unittest

from input_router import route_user_input


class InputRouterV3Tests(unittest.TestCase):
    def test_greeting_route(self):
        route = route_user_input("Hello Nancee, how are you?")
        self.assertEqual("greeting", route.kind)

    def test_detailed_route_is_stored(self):
        text = "Explain step by step how a database index works."
        route = route_user_input(text)

        self.assertEqual("detailed", route.kind)
        self.assertTrue(route.store_recall)
        self.assertEqual(text, route.recall_storage_text)

    def test_detailed_personal_overshare_is_stored(self):
        text = (
            "A little bit about myself, my favorite band in the whole "
            "world is Finch. They are from Temecula, California. "
            "They play post-hardcore screamo emo music."
        )

        route = route_user_input(text)

        self.assertEqual("detailed", route.kind)
        self.assertEqual("detailed_request", route.reason)
        self.assertTrue(route.store_recall)
        self.assertEqual(text, route.recall_storage_text)

    def test_directive_route(self):
        route = route_user_input("Ask me whether I finished wiring the power board.")
        self.assertEqual("directive", route.kind)

    def test_explicit_recall_controls_authoritative_miss(self):
        route = route_user_input("What did I finish wiring?")
        self.assertEqual("recall", route.kind)
        self.assertTrue(route.retrieve_recall)
        self.assertTrue(route.explicit_recall)
        self.assertTrue(route.allow_weak_match)

    def test_ordinary_question_gets_strict_background_enrichment(self):
        route = route_user_input("What is the capital of France?")
        self.assertEqual("normal", route.kind)
        self.assertTrue(route.retrieve_recall)
        self.assertFalse(route.explicit_recall)
        self.assertFalse(route.allow_weak_match)

    def test_general_where_question_is_not_forced_recall(self):
        route = route_user_input("Where is the nearest library?")
        self.assertEqual("normal", route.kind)
        self.assertTrue(route.retrieve_recall)
        self.assertFalse(route.explicit_recall)

    def test_personal_location_question_is_explicit_recall(self):
        route = route_user_input("Where does my sister live?")
        self.assertEqual("recall", route.kind)
        self.assertTrue(route.explicit_recall)

    def test_possessive_assignment_is_acknowledged_and_stored(self):
        route = route_user_input(
            "My favorite snack is salt and vinegar chips."
        )

        self.assertEqual("acknowledge", route.kind)
        self.assertTrue(route.store_recall)

    def test_first_person_location_update_is_acknowledged_and_stored(self):
        route = route_user_input(
            "I put a copper flashlight inside the garage cabinet."
        )

        self.assertEqual("acknowledge", route.kind)
        self.assertTrue(route.store_recall)

    def test_relationship_fact_is_acknowledged_and_stored(self):
        route = route_user_input("My sister lives in Boise.")
        self.assertEqual("acknowledge", route.kind)
        self.assertTrue(route.store_recall)
        self.assertEqual("My sister lives in Boise.", route.recall_storage_text)

    def test_unrelated_who_question_remains_normal(self):
        route = route_user_input("Who invented the transistor?")
        self.assertEqual("normal", route.kind)

    def test_contextual_answer_resolves_previous_question_for_storage(self):
        route = route_user_input(
            "I sure did.",
            previous_turn={
                "user": "Ask me whether I finished wiring the power board.",
                "assistant": "Did you finish wiring the power board?",
            },
        )

        self.assertEqual("clarify", route.kind)
        self.assertEqual("contextual_answer", route.reason)
        self.assertTrue(route.force_keep_history)
        self.assertTrue(route.store_recall)
        self.assertEqual(
            "I did finish wiring the power board.",
            route.recall_storage_text,
        )

    def test_sure_answer_beats_generic_backchannel_routing(self):
        route = route_user_input(
            "Sure.",
            previous_turn={
                "user": "Ask me whether I finished wiring the power board.",
                "assistant": "Did you finish wiring the power board?",
            },
        )

        self.assertEqual("clarify", route.kind)
        self.assertEqual("contextual_answer", route.reason)
        self.assertEqual(
            "I did finish wiring the power board.",
            route.recall_storage_text,
        )

    def test_same_short_answer_without_question_stays_ambiguous(self):
        route = route_user_input(
            "I sure did.",
            previous_turn={
                "user": "Tell me a joke.",
                "assistant": "A wrench walked into a bar.",
            },
        )

        self.assertEqual("clarify", route.kind)
        self.assertEqual("ambiguous_fragment", route.reason)
        self.assertFalse(route.store_recall)

    def test_incomplete_personal_fact_does_not_force_miss(self):
        route = route_user_input("My wife's name.")
        self.assertEqual("clarify", route.kind)
        self.assertTrue(route.retrieve_recall)
        self.assertFalse(route.explicit_recall)

    def test_default_route_is_normal(self):
        route = route_user_input("That sounds pretty useful to me.")
        self.assertEqual("normal", route.kind)
        self.assertEqual("default_model_route", route.reason)
        self.assertFalse(route.explicit_recall)


    def test_short_hello_or_hi_is_a_hard_greeting(self):
        samples = (
            "Hi",
            "Hello",
            "Hi Nancy",
            "Hello Maki Man",
            "Hello fuck face.",
        )

        for text in samples:
            with self.subTest(text=text):
                route = route_user_input(text)
                self.assertEqual("greeting", route.kind)
                self.assertEqual("leading_hello_or_hi", route.reason)

    def test_long_hello_or_hi_request_continues_routing(self):
        detailed = route_user_input(
            "Hello, explain step by step how a database index works."
        )
        directive = route_user_input("Hi, tell me a joke.")

        self.assertEqual("detailed", detailed.kind)
        self.assertEqual("directive", directive.kind)

    def test_split_name_asr_prefix_is_removed_for_retrieval(self):
        route = route_user_input("And see where is Finch from?")

        self.assertEqual("normal", route.kind)
        self.assertTrue(route.retrieve_recall)
        self.assertEqual("where is finch from?", route.normalized_text)

    def test_existing_soft_greeting_prefaces_keep_existing_routing(self):
        route = route_user_input(
            "Hey Nancee, explain step by step how a database index works."
        )

        self.assertEqual("detailed", route.kind)
        self.assertEqual("detailed_request", route.reason)


if __name__ == "__main__":
    unittest.main()
