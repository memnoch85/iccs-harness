import unittest

from sherpa.session_memory_store import (
    SessionMemoryStore,
    make_fts_query,
)


class MemoryQueryExpansionTests(unittest.TestCase):
    def test_buy_query_contains_bought_variant(self):
        query = make_fts_query("What did I buy?")
        self.assertIn("buy", query)
        self.assertIn("bought", query)

    def test_bought_memory_matches_buy_question(self):
        store = SessionMemoryStore(max_memories=8)

        try:
            store.add_memory(
                "Today I bought hot sauce at Macy's.",
                turn_id=1,
            )

            hits = store.search_memory(
                "What did I buy?",
                limit=3,
            )

            self.assertEqual(len(hits), 1)
            self.assertIn("hot sauce", hits[0].raw_text)
        finally:
            store.conn.close()


if __name__ == "__main__":
    unittest.main()
