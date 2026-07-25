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

    def test_authoritative_answers_and_misses_are_collected_before_tts(self):
        self.assertIn(
            "if authoritative_response_required:",
            SOURCE,
        )
        self.assertIn(
            "prepare_authoritative_response(",
            SOURCE,
        )

    def test_memory_storage_uses_router_decision(self):
        self.assertIn(
            "elif input_route.store_recall:",
            SOURCE,
        )
        self.assertIn(
            "input_route.recall_storage_text",
            SOURCE,
        )
        self.assertIn(
            "memory_storage_skip_reason(user_text)",
            SOURCE,
        )

    def test_router_is_the_only_top_level_classifier(self):
        self.assertIn(
            "from input_router import route_user_input",
            SOURCE,
        )
        self.assertEqual(1, SOURCE.count("route_user_input("))
        self.assertNotIn("def looks_like_recall_request", SOURCE)
        self.assertNotIn("def should_retrieve_recall", SOURCE)


if __name__ == "__main__":
    unittest.main()
