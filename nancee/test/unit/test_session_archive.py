import unittest

from session_archive import SessionArchive


class TestSessionArchive(unittest.TestCase):
    def test_recall_store_keeps_only_last_24_turns(self):
        recall = SessionArchive(max_turns=24)

        for index in range(30):
            recall.add_turn(
                f"User turn {index} about topic {index}.",
                "Okay.",
            )

        turns = recall.get_turns_snapshot()

        self.assertEqual(len(turns), 24)
        self.assertIn("User turn 6", turns[0]["user"])
        self.assertIn("User turn 29", turns[-1]["user"])

    def test_add_turn_returns_added_record(self):
        recall = SessionArchive(max_turns=24)

        added = recall.add_turn(
            "My name is Anders.",
            "Okay.",
        )

        self.assertEqual(added["archive_id"], 1)
        self.assertEqual(added["user"], "My name is Anders.")
        self.assertEqual(added["assistant"], "Okay.")

    def test_recall_store_retrieves_name(self):
        recall = SessionArchive(max_turns=24)

        recall.add_turn("My name is Anders.", "Okay.")
        recall.add_turn("The road is quiet today.", "Okay.")

        hits = recall.retrieve(
            "What is my name?",
            limit=3,
            min_score=1.0,
        )

        self.assertGreaterEqual(len(hits), 1)
        self.assertIn("Anders", hits[0]["user"])

    def test_recall_store_retrieves_top_three(self):
        recall = SessionArchive(max_turns=24)

        recall.add_turn("My name is Anders.", "Okay.")
        recall.add_turn("My favorite band is Finch.", "Okay.")
        recall.add_turn("Finch is from Temecula California.", "Okay.")
        recall.add_turn("My car is a black 2016 Jeep Patriot.", "Okay.")

        hits = recall.retrieve(
            "Where is Finch from?",
            limit=3,
            min_score=1.0,
            snippet_words=18,
        )

        self.assertGreaterEqual(len(hits), 1)

        self.assertTrue(
            any(
                "Temecula" in hit["user"] or "Temecula" in hit["snippet"]
                for hit in hits
            )
        )

        self.assertLessEqual(len(hits), 3)

    def test_command_words_do_not_dominate_recall(self):
        recall = SessionArchive(max_turns=24)

        recall.add_turn("My name is Anders.", "Okay.")
        recall.add_turn("I am 41 years old.", "Okay.")

        hits = recall.retrieve(
            "Nancee, do you remember how old I am?",
            limit=3,
            min_score=1.0,
        )

        self.assertGreaterEqual(len(hits), 1)
        self.assertTrue(
            "41" in hits[0]["user"] or "41" in hits[0]["snippet"]
        )

    def test_retrieval_limit_is_respected(self):
        recall = SessionArchive(max_turns=24)

        recall.add_turn("My first snack is mango.", "Okay.")
        recall.add_turn("My second snack is jerky.", "Okay.")
        recall.add_turn("My third snack is almonds.", "Okay.")

        hits = recall.retrieve(
            "What snack did I mention?",
            limit=2,
            min_score=1.0,
        )

        self.assertEqual(len(hits), 2)

    def test_irrelevant_query_returns_no_hits(self):
        recall = SessionArchive(max_turns=24)

        recall.add_turn(
            "We discussed the force equation.",
            "Okay.",
        )

        hits = recall.retrieve(
            "banana sandwich weather",
            limit=3,
            min_score=2.0,
        )

        self.assertEqual(hits, [])

    def test_related_context_is_capped(self):
        recall = SessionArchive(max_turns=24)

        recall.add_turn(
            "We discussed force equation details for a physics problem.",
            "Okay.",
        )

        hits = recall.retrieve(
            "force equation",
            limit=3,
            min_score=1.0,
        )

        context = recall.format_related_context(
            hits,
            max_characters=160,
        )

        self.assertIn("RELATED SESSION MEMORY", context)
        self.assertLessEqual(len(context), 160)
        self.assertIn("force", context.lower())

    def test_snapshot_is_deep_copy(self):
        recall = SessionArchive(max_turns=24)

        recall.add_turn("My mechanic is named Dave.", "Okay.")

        snapshot = recall.get_turns_snapshot()
        snapshot[0]["user"] = "changed"

        self.assertEqual(
            recall.get_turns_snapshot()[0]["user"],
            "My mechanic is named Dave.",
        )

    def test_clear_resets_store(self):
        recall = SessionArchive(max_turns=24)

        recall.add_turn("My mechanic is named Dave.", "Okay.")
        recall.clear()

        self.assertEqual(recall.get_turns_snapshot(), [])
        self.assertEqual(recall.get_stats()["turn_count"], 0)

        added = recall.add_turn("My car is a Jeep.", "Okay.")
        self.assertEqual(added["archive_id"], 1)

    def test_drive_query_matches_owned_vehicle_fact(self):
        recall = SessionArchive(max_turns=24)

        recall.add_turn(
            "I own a black 2016 Jeep Patriot.",
            "Okay.",
        )

        hits = recall.retrieve(
            "What do I drive?",
            limit=3,
            min_score=1.0,
            snippet_words=18,
        )

        self.assertGreaterEqual(len(hits), 1)
        self.assertIn("Jeep Patriot", hits[0]["snippet"])


if __name__ == "__main__":
    unittest.main()
