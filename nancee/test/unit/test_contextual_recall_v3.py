from __future__ import annotations

import unittest
from unittest.mock import patch

from input_router import route_user_input
from router_mon import RouterMonResult
from session_memory_store import SessionMemoryStore


class ContextualRecallV3Tests(unittest.TestCase):
    def test_affirmative_answer_becomes_searchable_fact(self):
        with patch(
            "input_router.classify_router_mon",
            return_value=RouterMonResult("affirmative", 0.9, "routerMon"),
        ):
            route = route_user_input(
                "I sure did.",
                previous_turn={
                    "user": "Ask me whether I finished wiring the power board.",
                    "assistant": "Did you finish wiring the power board?",
                },
            )

        store = SessionMemoryStore(max_memories=8)

        try:
            memory_id = store.add_memory(route.recall_storage_text)
            hits = store.search_memory("What did I finish wiring?", limit=3)

            self.assertIsNotNone(memory_id)
            self.assertTrue(hits)
            self.assertIn("power board", hits[0].raw_text.lower())
        finally:
            store.conn.close()


    def test_negative_answer_is_resolved_without_inventing_completion(self):
        with patch(
            "input_router.classify_router_mon",
            return_value=RouterMonResult("negative", 0.9, "routerMon"),
        ):
            route = route_user_input(
                "Not yet.",
                previous_turn={
                    "user": "Ask me whether I finished wiring the power board.",
                    "assistant": "Did you finish wiring the power board?",
                },
            )

        self.assertEqual(
            "I did not finish wiring the power board.",
            route.recall_storage_text,
        )


if __name__ == "__main__":
    unittest.main()
