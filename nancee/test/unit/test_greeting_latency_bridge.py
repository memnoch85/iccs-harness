from __future__ import annotations

import unittest
from pathlib import Path

from config import (
    LATENCY_BRIDGE_GREETING_PHRASES,
    LATENCY_BRIDGE_PHRASES,
)


SOURCE = (
    Path(__file__).resolve().parents[2]
    / "sherpa"
    / "nancee_chat.py"
).read_text(
    encoding="utf-8",
)


class GreetingLatencyBridgeTests(unittest.TestCase):
    def test_greeting_phrases_are_intentionally_conversational(self):
        self.assertEqual(
            LATENCY_BRIDGE_GREETING_PHRASES,
            (
                "Oh hey, umm...",
                "What's up, humm...",
                "Oh hi, umm...",
                "Hey there, umm...",
                "Hi, umm...",
                "Hey, humm...",
                "Oh hey...",
                "Oh hi there...",
                "Umm...",
                "Humm...",
            ),
        )

    def test_greeting_phrases_are_one_to_four_words(self):
        self.assertEqual(
            10,
            len(LATENCY_BRIDGE_GREETING_PHRASES),
        )

        for phrase in LATENCY_BRIDGE_GREETING_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertGreaterEqual(
                    len(phrase.split()),
                    1,
                )
                self.assertLessEqual(
                    len(phrase.split()),
                    4,
                )

    def test_greeting_phrases_do_not_claim_work_is_happening(self):
        forbidden_words = {
            "check",
            "checking",
            "moment",
            "briefly",
        }

        for phrase in LATENCY_BRIDGE_GREETING_PHRASES:
            normalized_words = {
                word.strip(".,!?").lower()
                for word in phrase.split()
            }

            with self.subTest(phrase=phrase):
                self.assertTrue(
                    forbidden_words.isdisjoint(
                        normalized_words
                    )
                )

    def test_normal_bridge_phrases_remain_available(self):
        self.assertIn(
            "Let me check that,",
            LATENCY_BRIDGE_PHRASES,
        )

        self.assertIn(
            "Give me one moment,",
            LATENCY_BRIDGE_PHRASES,
        )

    def test_existing_greeting_policy_selects_greeting_cycle(self):
        self.assertIn(
            'if response_policy.name == "greeting":',
            SOURCE,
        )

        self.assertIn(
            "greeting_bridge_audio_cycle",
            SOURCE,
        )

        self.assertIn(
            "selected_bridge_audio_cycle",
            SOURCE,
        )

        self.assertIn(
            "next(\n"
            "                selected_bridge_audio_cycle\n"
            "            )",
            SOURCE,
        )

    def test_greeting_uses_separate_bridge_threshold(self):
        self.assertIn(
            "LATENCY_BRIDGE_GREETING_SECONDS",
            SOURCE,
        )

        self.assertIn(
            'if response_policy.name == "greeting":',
            SOURCE,
        )

        self.assertIn(
            "bridge_delay_seconds = (",
            SOURCE,
        )


if __name__ == "__main__":
    unittest.main()
