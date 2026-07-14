from pathlib import Path
import re
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
        assignment_match = re.search(
            (
                r"authoritative_context_found\s*=\s*"
                r"memory_context_found\s+or\s+"
                r"bool\(\s*"
                r"effective_profile_context\.strip\(\)"
                r"\s*\)"
            ),
            SOURCE,
        )

        self.assertIsNotNone(
            assignment_match,
            (
                "authoritative_context_found must combine "
                "memory and profile context"
            ),
        )

        policy_match = re.search(
            (
                r"select_response_policy\("
                r"[\s\S]*?"
                r"authoritative_context_found\s*=\s*"
                r"(?:\(\s*)?"
                r"authoritative_context_found"
                r"(?:\s*\))?"
            ),
            SOURCE,
        )

        self.assertIsNotNone(
            policy_match,
            (
                "select_response_policy must receive "
                "authoritative_context_found"
            ),
        )

        history_drop_match = re.search(
            (
                r"elif\s+"
                r"(?:\(\s*)?"
                r"authoritative_context_found"
                r"\s+or\s+"
                r"response_policy\.drop_history"
                r"(?:\s*\))?"
                r"\s*:"
                r"[\s\S]*?"
                r"request_history\s*=\s*\[\]"
            ),
            SOURCE,
        )

        self.assertIsNotNone(
            history_drop_match,
            (
                "authoritative context or drop_history "
                "must discard recent chat history"
            ),
        )

    def test_effective_profile_context_is_used(self):
        self.assertIn(
            "memory_context=effective_profile_context",
            SOURCE,
        )


if __name__ == "__main__":
    unittest.main()
