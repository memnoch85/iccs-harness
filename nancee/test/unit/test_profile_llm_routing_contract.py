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

    def test_profile_context_is_retrieval_only(self):
        # The full profile must not be injected merely because
        # the utterance looks like a question or recall request.
        self.assertNotIn(
            "or recall_requested",
            SOURCE,
        )

        # Profile context is supplied only when the retrieval
        # layer finds a matching authoritative profile fact.
        self.assertIn(
            "profile_context_found",
            SOURCE,
        )

        self.assertIn(
            "effective_profile_context",
            SOURCE,
        )

    def test_profile_context_reaches_ollama(self):
        self.assertIn(
            "effective_profile_context,",
            SOURCE,
        )
        self.assertIn(
            "memory_context=request_memory_context",
            SOURCE,
        )


if __name__ == "__main__":
    unittest.main()
