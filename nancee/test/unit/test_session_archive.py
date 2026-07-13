import unittest

from session_archive import SessionArchive


def row_text(row):
    return row.get("raw_text") or row.get("user") or ""


class TestSessionArchive(unittest.TestCase):
    def test_add_turn_returns_memory_id(self):
        recall = SessionArchive(max_turns=24)

        added = recall.add_turn("My name is Anders.")

        self.assertEqual(int(added), 1)
        self.assertEqual(len(recall), 1)

    def test_low_signal_asr_junk_is_not_stored(self):
        recall = SessionArchive(max_turns=24)

        self.assertIsNone(recall.add_turn("In my name."))
        self.assertEqual(len(recall), 0)

    def test_recall_store_keeps_only_recent_raw_utterances(self):
        recall = SessionArchive(max_turns=3)

        recall.add_turn("Memory one is alpha.")
        recall.add_turn("Memory two is bravo.")
        recall.add_turn("Memory three is charlie.")
        recall.add_turn("Memory four is delta.")

        snapshot = recall.debug_snapshot()
        rows = snapshot["rows"]

        self.assertEqual(snapshot["turn_count"], 3)

        texts = [row_text(row) for row in rows]

        self.assertNotIn("Memory one is alpha.", texts)
        self.assertIn("Memory two is bravo.", texts)
        self.assertIn("Memory three is charlie.", texts)
        self.assertIn("Memory four is delta.", texts)

    def test_recall_retrieves_name_by_token_overlap(self):
        recall = SessionArchive(max_turns=24)

        recall.add_turn("My name is Anders.")

        hits = recall.retrieve("What is my name?", limit=3)

        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0]["user"], "My name is Anders.")

    def test_recall_retrieves_drive_by_token_overlap(self):
        recall = SessionArchive(max_turns=24)

        recall.add_turn("I drive a black Jeep.")

        hits = recall.retrieve("What do I drive?", limit=3)

        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0]["user"], "I drive a black Jeep.")

    def test_recall_retrieves_hot_sauce_purchase(self):
        recall = SessionArchive(max_turns=24)

        recall.add_turn("I bought hot sauce at Ocean Market.")

        hits = recall.retrieve("Where did I buy hot sauce?", limit=3)

        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0]["user"], "I bought hot sauce at Ocean Market.")

    def test_porter_stemming_matches_park_and_parked(self):
        recall = SessionArchive(max_turns=24)

        recall.add_turn("I parked on level three near the west elevator.")

        hits = recall.retrieve("Where did I park?", limit=3)

        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(
            hits[0]["user"],
            "I parked on level three near the west elevator.",
        )

    def test_no_semantic_alias_expansion_in_pure_fts5(self):
        recall = SessionArchive(max_turns=24)

        recall.add_turn("I drive a black Jeep.")

        hits = recall.retrieve("What vehicle do I have?", limit=3)

        self.assertEqual(hits, [])

    def test_newest_tie_breaker_prefers_correction(self):
        recall = SessionArchive(max_turns=24)

        recall.add_turn("I drive a black keeper.")
        recall.add_turn("I drive a black Jeep.")

        hits = recall.retrieve("What do I drive?", limit=3)

        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0]["user"], "I drive a black Jeep.")

    def test_irrelevant_query_returns_no_hits(self):
        recall = SessionArchive(max_turns=24)

        recall.add_turn("My name is Anders.")
        recall.add_turn("I drive a black Jeep.")

        hits = recall.retrieve("banana moon turtle", limit=3)

        self.assertEqual(hits, [])

    def test_retrieval_limit_is_respected(self):
        recall = SessionArchive(max_turns=24)

        recall.add_turn("I bought hot sauce at Ocean Market.")
        recall.add_turn("I bought Japanese candy at Ocean Market.")
        recall.add_turn("I bought ramen at Ocean Market.")

        hits = recall.retrieve("What did I buy at Ocean Market?", limit=2)

        self.assertLessEqual(len(hits), 2)

    def test_related_context_uses_quote_overlay(self):
        recall = SessionArchive(max_turns=24)

        recall.add_turn("I bought hot sauce at Ocean Market.")

        hits = recall.retrieve("Where did I buy hot sauce?", limit=3)
        context = recall.format_related_context(hits, max_characters=650)

        self.assertIn("Confirmed user memory.", context)
        self.assertIn('User said: "I bought hot sauce at Ocean Market."', context)
        self.assertIn("I bought hot sauce at Ocean Market.", context)

    def test_related_context_is_capped(self):
        recall = SessionArchive(max_turns=24)

        recall.add_turn("I bought hot sauce at Ocean Market.")

        hits = recall.retrieve("Where did I buy hot sauce?", limit=3)
        context = recall.format_related_context(hits, max_characters=80)

        self.assertLessEqual(len(context), 80)
        self.assertTrue(context.startswith("Confirmed user memory."))


if __name__ == "__main__":
    unittest.main()
