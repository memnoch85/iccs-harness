from __future__ import annotations

import re
import unittest
from pathlib import Path


PROMPT = (
    Path(__file__).resolve().parents[2]
    / "sherpa/system-prompt.txt"
).read_text(encoding="utf-8").strip()


class SystemPromptContractV4Tests(unittest.TestCase):
    def test_prompt_is_shorter_and_route_agnostic(self):
        words = re.findall(r"\b[\w'-]+\b", PROMPT)
        self.assertLessEqual(len(words), 225)
        self.assertNotIn("no more than 20 words", PROMPT)
        self.assertNotIn("three sentences and 40 words", PROMPT)
        self.assertNotIn("Use up to 60 words", PROMPT)

    def test_streaming_and_accuracy_contracts_remain(self):
        self.assertIn("one-to-four-word clause", PROMPT)
        self.assertIn("short complete clauses", PROMPT)
        self.assertIn("Add punctuation at natural pauses", PROMPT)
        self.assertIn("Do not invent facts", PROMPT)

    def test_memory_personality_and_default_response_contracts_remain(self):
        self.assertIn("confirmed memory", PROMPT)
        self.assertIn("you or your", PROMPT)
        self.assertIn("warm, witty, occasionally sarcastic", PROMPT)
        self.assertIn(
            "For ordinary conversation, respond warmly and briefly.",
            PROMPT,
        )
        self.assertIn(
            "Expand only when the current turn explicitly asks for detail.",
            PROMPT,
        )


if __name__ == "__main__":
    unittest.main()
