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

    def test_streaming_and_safety_contracts_remain(self):
        self.assertIn("one-to-four-word clause", PROMPT)
        self.assertIn("Never split names, numbers, units", PROMPT)
        self.assertIn("Do not invent facts", PROMPT)

    def test_memory_and_personality_contracts_remain(self):
        self.assertIn("confirmed memory", PROMPT)
        self.assertIn("you or your", PROMPT)
        self.assertIn("occasional dry wit", PROMPT)
        self.assertIn("never for safety, diagnostics", PROMPT)


if __name__ == "__main__":
    unittest.main()
