import unittest
from pathlib import Path

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

    def test_input_is_routed_once(self):
        self.assertEqual(1, SOURCE.count("route_user_input("))
        self.assertIn("[INPUT ROUTE]", SOURCE)

    def test_router_controls_memory_and_storage(self):
        self.assertIn("recall_requested = input_route.retrieve_recall", SOURCE)
        self.assertIn("allow_weak_match=input_route.allow_weak_match", SOURCE)
        self.assertIn("elif input_route.store_recall:", SOURCE)
        self.assertIn("correction = input_route.correction", SOURCE)

    def test_only_explicit_recall_promotes_session_memory_to_authority(self):
        self.assertIn("input_route.explicit_recall", SOURCE)
        self.assertIn("and memory_context_found", SOURCE)
        self.assertIn("authoritative_response_required", SOURCE)

    def test_authoritative_response_or_policy_can_drop_history(self):
        self.assertIn(
            "elif authoritative_response_required or response_policy.drop_history:",
            SOURCE,
        )
        self.assertIn("request_history = []", SOURCE)



if __name__ == "__main__":
    unittest.main()
