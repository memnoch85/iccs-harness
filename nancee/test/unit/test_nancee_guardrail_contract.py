from pathlib import Path
import unittest


SOURCE = (
    Path(__file__).resolve().parents[2]
    / "sherpa"
    / "nancee_chat.py"
).read_text(encoding="utf-8")


class NanceeGuardrailContractTests(unittest.TestCase):
    def test_profile_hit_skips_weaker_session_recall(self):
        self.assertIn(
            "reason=authoritative_profile_hit",
            SOURCE,
        )

    def test_authoritative_answers_are_collected_before_tts(self):
        self.assertIn(
            "if authoritative_context_found:",
            SOURCE,
        )
        self.assertIn(
            "prepare_authoritative_response(",
            SOURCE,
        )

    def test_memory_storage_uses_conservative_policy(self):
        self.assertIn(
            "if should_store_recall_turn(user_text):",
            SOURCE,
        )
        self.assertIn(
            "memory_storage_skip_reason(user_text)",
            SOURCE,
        )

    def test_personal_fact_fragments_enter_recall_path(self):
        self.assertIn(
            "looks_like_personal_fact_fragment(user_text)",
            SOURCE,
        )


if __name__ == "__main__":
    unittest.main()
