from pathlib import Path
import unittest


SOURCE = (
    Path(__file__).resolve().parents[2]
    / "sherpa"
    / "nancee_chat.py"
).read_text(encoding="utf-8")


class NanceeChatPatchContractTests(unittest.TestCase):
    def test_bridge_is_resolved_by_first_audio_callbacks(self):
        self.assertIn(
            "first_audio_callback=bridge.resolve",
            SOURCE,
        )
        self.assertNotIn(
            "first_token_callback=bridge.resolve",
            SOURCE,
        )

    def test_history_routing_uses_authoritative_context_not_every_question(self):
        self.assertIn(
            "authoritative_context_found = (",
            SOURCE,
        )

        self.assertIn(
            "memory_context_found",
            SOURCE,
        )

        self.assertIn(
            "profile_context_found",
            SOURCE,
        )

        # Authoritative context must be supplied to the
        # per-turn response-policy selector. Allow optional
        # parentheses and arbitrary source formatting.
        self.assertRegex(
            SOURCE,
            (
                r"response_policy\s*=\s*"
                r"select_response_policy\("
                r"[\s\S]*?"
                r"authoritative_context_found\s*=\s*"
                r"\(\s*"
                r"authoritative_context_found"
                r"\s*\)"
                r"[\s\S]*?"
                r"\)"
            ),
        )

        # History is discarded for either authoritative
        # retrieved context or a response mode whose policy
        # explicitly requests history removal.
        self.assertRegex(
            SOURCE,
            (
                r"elif\s*\(\s*"
                r"authoritative_context_found"
                r"\s+or\s+"
                r"response_policy\.drop_history"
                r"\s*\)\s*:"
            ),
        )

        self.assertRegex(
            SOURCE,
            (
                r"response_policy\.drop_history"
                r"[\s\S]*?"
                r"request_history\s*=\s*\[\]"
            ),
        )


    def test_effective_profile_context_is_used(self):
        self.assertIn(
            "memory_context=effective_profile_context",
            SOURCE,
        )


if __name__ == "__main__":
    unittest.main()
