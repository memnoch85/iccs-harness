from pathlib import Path
import unittest


SOURCE = (
    Path(__file__).resolve().parents[2]
    / "sherpa"
    / "nancee_chat.py"
).read_text(encoding="utf-8")


class ProfileLlmRoutingContractTests(unittest.TestCase):
    def test_direct_profile_answer_is_not_used(self):
        self.assertNotIn(
            "user_profile.direct_answer(",
            SOURCE,
        )

    def test_profile_context_is_available_for_recall_questions(self):
        self.assertIn(
            "or recall_requested",
            SOURCE,
        )

    def test_profile_context_reaches_ollama(self):
        self.assertIn(
            "memory_context=effective_profile_context",
            SOURCE,
        )


if __name__ == "__main__":
    unittest.main()
