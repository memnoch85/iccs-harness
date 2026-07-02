
#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = (
    Path(__file__).resolve().parents[2]
)

SHERPA_DIRECTORY = (
    REPOSITORY_ROOT
    / "sherpa"
)

sys.path.insert(
    0,
    str(SHERPA_DIRECTORY),
)

from session_fact_extractor import (  # noqa: E402
    promote_archived_facts,
)
from short_term_memory import (  # noqa: E402
    ShortTermMemory,
)


class TestSessionFactExtractor(unittest.TestCase):
    def test_promotes_supported_user_facts(self):
        memory = ShortTermMemory(max_turns=None)

        archived_turns = [
            {
                "user": (
                    "My name is Anders, please address me by name. "
                    "My favorite type of music is punk and screamo. "
                    "My favorite band is called Finch. "
                    "They are from Temecula, California."
                ),
                "assistant": "Assistant response is irrelevant.",
            },
            {
                "user": (
                    "How many MPG does my 2016 Jeep Patriot get? "
                    "It also has code P0420."
                ),
                "assistant": "Assistant response is irrelevant.",
            },
        ]

        changes = promote_archived_facts(
            memory,
            archived_turns,
        )

        self.assertEqual(
            changes["user_name"],
            "Anders",
        )
        self.assertEqual(
            changes["favorite_music"],
            "punk and screamo",
        )
        self.assertEqual(
            changes["favorite_band"],
            "Finch",
        )
        self.assertEqual(
            changes["favorite_band_origin"],
            "Temecula, California",
        )
        self.assertEqual(
            changes["vehicle"],
            "2016 Jeep Patriot",
        )
        self.assertEqual(
            changes["last_dtc_codes"],
            ["P0420"],
        )

    def test_assistant_hallucination_is_not_promoted(self):
        memory = ShortTermMemory(max_turns=None)

        changes = promote_archived_facts(
            memory,
            [
                {
                    "user": "Tell me about my favorite band.",
                    "assistant": (
                        "Your favorite band is Finch, "
                        "and they are from New York City."
                    ),
                }
            ],
        )

        self.assertEqual(changes, {})
        self.assertEqual(
            memory.build_memory_context(),
            "",
        )

    def test_later_user_correction_replaces_origin(self):
        memory = ShortTermMemory(max_turns=None)

        promote_archived_facts(
            memory,
            [
                {
                    "user": (
                        "My favorite band is Finch. "
                        "They are from New York City."
                    ),
                    "assistant": "Okay.",
                },
                {
                    "user": (
                        "Finch is an American rock band "
                        "from Temecula, California."
                    ),
                    "assistant": "Understood.",
                },
            ],
        )

        context = memory.build_memory_context()

        self.assertIn(
            '"favorite_band": "Finch"',
            context,
        )
        self.assertIn(
            '"favorite_band_origin": '
            '"Temecula, California"',
            context,
        )
        self.assertNotIn(
            "New York City",
            context,
        )

    def test_memory_context_contains_compact_facts(self):
        memory = ShortTermMemory(max_turns=None)

        promote_archived_facts(
            memory,
            [
                {
                    "user": (
                        "My name is Anders. "
                        "I drive a 2016 Jeep Patriot. "
                        "I have a P0420 code."
                    ),
                    "assistant": "Okay.",
                }
            ],
        )

        context = memory.build_memory_context()

        self.assertIn(
            "SESSION MEMORY - use only as context.",
            context,
        )
        self.assertIn(
            '"user_name": "Anders"',
            context,
        )
        self.assertIn(
            '"vehicle": "2016 Jeep Patriot"',
            context,
        )
        self.assertIn(
            "Last DTC codes: P0420",
            context,
        )


if __name__ == "__main__":
    unittest.main()
