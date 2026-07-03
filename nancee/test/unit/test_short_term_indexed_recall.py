#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SHERPA_DIRECTORY = REPOSITORY_ROOT / "sherpa"
sys.path.insert(0, str(SHERPA_DIRECTORY))

from session_archive import SessionArchive  # noqa: E402


class TestShortTermIndexedRecall(unittest.TestCase):
    def test_archive_keeps_only_last_24_turns(self):
        archive = SessionArchive(max_turns=24)

        archive.add_turns(
            [
                {
                    "user": f"User turn {number} about topic {number}.",
                    "assistant": f"Nancee turn {number}.",
                }
                for number in range(30)
            ]
        )

        turns = archive.get_turns_snapshot()

        self.assertEqual(24, len(turns))
        self.assertIn("User turn 6", turns[0]["user"])
        self.assertIn("User turn 29", turns[-1]["user"])

    def test_arbitrary_force_equation_recall(self):
        archive = SessionArchive(max_turns=24)

        archive.add_turns(
            [
                {
                    "user": "We are solving a force equation problem.",
                    "assistant": "Use F = m times a, meaning force equals mass times acceleration.",
                },
                {
                    "user": "Now tell me a joke.",
                    "assistant": "So, tiny wrench walks into a bar.",
                },
            ]
        )

        hits = archive.retrieve(
            "What was the equation for force?",
            limit=3,
            min_score=1.0,
            snippet_words=18,
        )

        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(1, hits[0]["archive_id"])
        self.assertIn("F = m", hits[0]["snippet"])

    def test_finch_bench_alias_recall(self):
        archive = SessionArchive(max_turns=24)

        archive.add_turns(
            [
                {
                    "user": "My favorite band is Finch, but ASR may hear Bench.",
                    "assistant": "Alright, I will treat Bench as likely Finch in this session.",
                }
            ]
        )

        hits = archive.retrieve(
            "What did I say about Bench?",
            limit=3,
            min_score=1.0,
            snippet_words=18,
        )

        self.assertEqual(1, len(hits))
        self.assertIn("Finch", hits[0]["snippet"])

    def test_related_context_is_capped(self):
        archive = SessionArchive(max_turns=24)
        archive.add_turns(
            [
                {
                    "user": "We discussed force equation details for a physics problem.",
                    "assistant": "The useful equation was F = m times a.",
                }
            ]
        )

        hits = archive.retrieve("force equation", limit=3, min_score=1.0)
        context = archive.format_related_context(hits, max_characters=160)

        self.assertIn("RELATED SESSION MEMORY", context)
        self.assertLessEqual(len(context), 160)
        self.assertIn("force", context.lower())

    def test_irrelevant_query_returns_no_hits(self):
        archive = SessionArchive(max_turns=24)
        archive.add_turns(
            [
                {
                    "user": "We discussed a force equation.",
                    "assistant": "Use F = m times a.",
                }
            ]
        )

        hits = archive.retrieve(
            "banana sandwich weather",
            limit=3,
            min_score=2.0,
        )

        self.assertEqual([], hits)


if __name__ == "__main__":
    unittest.main()
