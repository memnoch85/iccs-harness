import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHAT_SOURCE = (ROOT / "sherpa" / "nancee_chat.py").read_text(encoding="utf-8")
POLICY_SOURCE = (ROOT / "sherpa" / "response_policy.py").read_text(encoding="utf-8")


class SpeakerIccsContractTests(unittest.TestCase):
    def test_speaker_state_is_stable_iccs_memory_context(self):
        self.assertIn(
            "memory_context=speaker_state.prompt_context()",
            CHAT_SOURCE,
        )
        self.assertIn(
            "memory_context=speaker_state.next_prompt_context()",
            CHAT_SOURCE,
        )
        self.assertIn(
            "memory_context=request_memory_context",
            CHAT_SOURCE,
        )

    def test_unexpected_direct_identity_change_relaxes_exact_match(self):
        self.assertIn(
            "and not speaker_context_changed_for_request",
            CHAT_SOURCE,
        )

    def test_speaker_query_skips_primary_profile_retrieval(self):
        self.assertIn(
            'and input_route.kind != "speaker"',
            CHAT_SOURCE,
        )

    def test_speaker_answers_bypass_the_llm_and_use_session_state(self):
        self.assertIn(
            "direct_speaker_identity_response(",
            CHAT_SOURCE,
        )
        self.assertIn(
            "direct_speaker_return_response()",
            CHAT_SOURCE,
        )
        self.assertIn(
            "[SPEAKER DIRECT RESPONSE]",
            CHAT_SOURCE,
        )
        self.assertIn(
            "if handled_directly:",
            CHAT_SOURCE,
        )

    def test_direct_response_consumes_pending_prime_before_rescheduling(self):
        self.assertIn(
            "text_queue.join()\n\n"
            "                # Direct speaker responses bypass "
            "iccs.respond()",
            CHAT_SOURCE,
        )
        wait_index = CHAT_SOURCE.index(
            "                iccs.wait_for_prepared_prefix()\n\n"
            "                iccs.prime_next("
        )
        completed_prime_index = CHAT_SOURCE.index(
            'reason="completed_turn"',
            wait_index,
        )
        self.assertLess(wait_index, completed_prime_index)

    def test_speaker_route_has_dedicated_policy(self):
        self.assertIn('if route_kind == "speaker":', POLICY_SOURCE)
        self.assertIn('name="speaker"', POLICY_SOURCE)


if __name__ == "__main__":
    unittest.main()
