from pathlib import Path
import re
import unittest

from profile_fact_index import ProfileFactIndex


class ProfileFactIndexTests(unittest.TestCase):
    def setUp(self):
        self.index = ProfileFactIndex(
            {
                "name": "Anders",
                "project": "NANCEE in-car OBD assistant",
                "vehicle": "black Jeep",
            }
        )

    def keys_for(self, query):
        return [
            hit.key
            for hit in self.index.search(query)
        ]

    def test_greeting_does_not_inject_profile(self):
        self.assertEqual(
            self.keys_for("Hello Nancee, how are you?"),
            [],
        )

    def test_name_query_returns_only_name(self):
        self.assertEqual(
            self.keys_for("What is my name?"),
            ["name"],
        )

    def test_wife_name_does_not_substitute_user_name(self):
        self.assertEqual(
            self.keys_for("What is my wife's name?"),
            [],
        )

    def test_vehicle_query_returns_vehicle(self):
        self.assertEqual(
            self.keys_for("What car do I drive?"),
            ["vehicle"],
        )

    def test_session_memory_question_does_not_inject_profile(self):
        self.assertEqual(
            self.keys_for("What did I buy yesterday?"),
            [],
        )

    def test_context_contains_only_matching_fact(self):
        context, hits = self.index.retrieve_context(
            "What is my project?"
        )

        self.assertEqual(
            [hit.key for hit in hits],
            ["project"],
        )
        self.assertIn("NANCEE in-car OBD assistant", context)
        self.assertNotIn("black Jeep", context)
        self.assertNotIn("Anders", context)


class ProfileRoutingSourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        cls.source = (
            root
            / "sherpa"
            / "nancee_chat.py"
        ).read_text(encoding="utf-8")

    def test_full_profile_is_not_formatted_each_turn(self):
        self.assertNotIn(
            "user_profile.format_context()",
            self.source,
        )

    def test_profile_index_is_queried(self):
        self.assertIn(
            "profile_index.retrieve_context(",
            self.source,
        )

    def test_canned_recall_miss_is_removed(self):
        self.assertNotIn(
            "[MEMORY RECALL MISS] answered_without_llm=true",
            self.source,
        )

    def test_authoritative_fact_answers_drop_chat_history(self):
        self.assertIn(
            "authoritative_response_required",
            self.source,
        )

        self.assertIn(
            "elif authoritative_response_required or response_policy.drop_history:",
            self.source,
        )

        self.assertIn(
            "request_history = []",
            self.source,
        )

    def test_background_session_enrichment_is_not_automatically_authoritative(self):
        self.assertIn(
            "input_route.explicit_recall",
            self.source,
        )

        self.assertIn(
            "and memory_context_found",
            self.source,
        )

if __name__ == "__main__":
    unittest.main()
