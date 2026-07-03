import unittest

from session_archive import (
    SessionArchive,
    archive_active_memory_if_needed,
)
from short_term_memory import ShortTermMemory


class TestSessionArchive(unittest.TestCase):
    def test_turn_limit_three_archives_on_fourth_turn(self):
        memory = ShortTermMemory(max_turns=None)
        archive = SessionArchive()

        for turn_number in range(1, 4):
            memory.add_turn(
                user_text=f"user {turn_number}",
                assistant_text=f"assistant {turn_number}",
            )

            moved = archive_active_memory_if_needed(
                memory=memory,
                archive=archive,
                max_active_turns=3,
                max_active_characters=999999,
                keep_recent_turns=1,
            )

            self.assertEqual(moved, [])

        memory.add_turn(
            user_text="user 4",
            assistant_text="assistant 4",
        )

        moved = archive_active_memory_if_needed(
            memory=memory,
            archive=archive,
            max_active_turns=3,
            max_active_characters=999999,
            keep_recent_turns=1,
        )

        self.assertEqual(len(moved), 3)
        self.assertEqual(memory.get_stats()["turn_count"], 1)
        self.assertEqual(archive.get_stats()["turn_count"], 3)

    def test_add_turns_and_snapshot_are_deep_copies(self):
        archive = SessionArchive()
        original = [
            {
                "user": "My name is Anders.",
                "assistant": "Got it, Anders.",
            }
        ]

        archive.add_turns(original)
        original[0]["user"] = "changed"

        snapshot = archive.get_turns_snapshot()
        snapshot[0]["user"] = "also changed"

        self.assertEqual(
            archive.get_turns_snapshot()[0]["user"],
            "My name is Anders.",
        )

    def test_retrieve_name_turn(self):
        archive = SessionArchive()
        archive.add_turns(
            [
                {
                    "user": "My name is Anders.",
                    "assistant": "Nice to meet you, Anders.",
                },
                {
                    "user": "The road is quiet today.",
                    "assistant": "It is a calm drive.",
                },
            ]
        )

        hits = archive.retrieve(
            "What is my name?",
            limit=2,
            min_score=2.0,
        )

        self.assertEqual(len(hits), 1)
        self.assertIn("Anders", hits[0]["user"])

    def test_retrieve_exact_code_turn(self):
        archive = SessionArchive()
        archive.add_turns(
            [
                {
                    "user": "The exact test code is ORBIT-731.",
                    "assistant": "I will remember ORBIT-731.",
                }
            ]
        )

        hits = archive.retrieve(
            "What was that test code?",
            limit=2,
            min_score=2.0,
        )

        self.assertEqual(len(hits), 1)
        self.assertIn("ORBIT-731", hits[0]["user"])

    def test_irrelevant_query_returns_no_hits(self):
        archive = SessionArchive()
        archive.add_turns(
            [
                {
                    "user": "My daughter is named Copeland.",
                    "assistant": "Copeland is your daughter.",
                }
            ]
        )

        hits = archive.retrieve(
            "How is the weather?",
            limit=2,
            min_score=2.0,
        )

        self.assertEqual(hits, [])

    def test_retrieval_limit_is_respected(self):
        archive = SessionArchive()
        archive.add_turns(
            [
                {
                    "user": "My first snack is mango.",
                    "assistant": "Mango noted.",
                },
                {
                    "user": "My second snack is jerky.",
                    "assistant": "Jerky noted.",
                },
                {
                    "user": "My third snack is almonds.",
                    "assistant": "Almonds noted.",
                },
            ]
        )

        hits = archive.retrieve(
            "What snack did I mention?",
            limit=2,
            min_score=2.0,
        )

        self.assertEqual(len(hits), 2)

    def test_format_retrieved_context(self):
        archive = SessionArchive(max_turns=24)

        archive.add_turns(
            [
                {
                    "user": "We said the force equation is F equals m times a.",
                    "assistant": "Right, force equals mass times acceleration.",
                }
            ]
        )

        retrieved = archive.retrieve(
            "What was the force equation?",
            limit=1,
            min_score=1.0,
            snippet_words=18,
        )

        context = archive.format_related_context(
            retrieved,
            max_characters=650,
        )

        self.assertIn(
            "RELATED SESSION MEMORY",
            context,
        )

        self.assertIn(
            "force equation",
            context.lower(),
        )

        self.assertIn(
            "F equals m times a",
            context,
        )

    def test_archive_trigger_keeps_two_recent_turns(self):
        memory = ShortTermMemory(max_turns=None)
        archive = SessionArchive()

        for number in range(1, 10):
            memory.add_turn(
                f"user {number}",
                f"assistant {number}",
            )

        moved = archive_active_memory_if_needed(
            memory=memory,
            archive=archive,
            max_active_turns=8,
            max_active_characters=10000,
            keep_recent_turns=2,
        )

        self.assertEqual(len(moved), 7)
        self.assertEqual(memory.get_stats()["turn_count"], 2)
        self.assertEqual(archive.get_stats()["turn_count"], 7)
        self.assertEqual(
            memory.get_turns_snapshot()[0]["user"],
            "user 8",
        )

    def test_character_threshold_archives_oldest_turns(self):
        memory = ShortTermMemory(max_turns=None)
        archive = SessionArchive()

        for number in range(1, 5):
            memory.add_turn(
                "u" * 100,
                f"assistant {number}",
            )

        moved = archive_active_memory_if_needed(
            memory=memory,
            archive=archive,
            max_active_turns=8,
            max_active_characters=200,
            keep_recent_turns=2,
        )

        self.assertEqual(len(moved), 2)
        self.assertEqual(memory.get_stats()["turn_count"], 2)

    def test_no_archive_under_threshold(self):
        memory = ShortTermMemory(max_turns=None)
        archive = SessionArchive()

        memory.add_turn("hello", "hi")

        moved = archive_active_memory_if_needed(
            memory=memory,
            archive=archive,
            max_active_turns=8,
            max_active_characters=1600,
            keep_recent_turns=2,
        )

        self.assertEqual(moved, [])
        self.assertEqual(memory.get_stats()["turn_count"], 1)
        self.assertEqual(archive.get_stats()["turn_count"], 0)


if __name__ == "__main__":
    unittest.main()
