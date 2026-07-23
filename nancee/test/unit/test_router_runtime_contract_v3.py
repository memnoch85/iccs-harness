from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHAT_SOURCE = (ROOT / "sherpa" / "nancee_chat.py").read_text(encoding="utf-8")
ROUTER_SOURCE = (ROOT / "sherpa" / "input_router.py").read_text(encoding="utf-8")


class RouterRuntimeContractV3Tests(unittest.TestCase):
    def test_chat_routes_each_user_input_once(self):
        self.assertEqual(1, CHAT_SOURCE.count("route_user_input("))
        self.assertIn("[INPUT ROUTE]", CHAT_SOURCE)

    def test_old_top_level_classifiers_are_removed_from_chat(self):
        forbidden = (
            "def looks_like_recall_request",
            "def should_retrieve_recall",
            "def should_store_recall_turn",
            "select_response_policy(",
        )

        for text in forbidden:
            with self.subTest(text=text):
                self.assertNotIn(text, CHAT_SOURCE)

    def test_router_controls_retrieval_storage_and_history(self):
        self.assertIn("recall_requested = input_route.retrieve_recall", CHAT_SOURCE)
        self.assertIn("allow_weak_match=input_route.allow_weak_match", CHAT_SOURCE)
        self.assertIn("elif input_route.store_recall:", CHAT_SOURCE)
        self.assertIn("correction = input_route.correction", CHAT_SOURCE)
        self.assertIn("if input_route.force_keep_history:", CHAT_SOURCE)

    def test_background_enrichment_is_not_automatically_authoritative(self):
        self.assertIn("input_route.explicit_recall", CHAT_SOURCE)
        self.assertIn("and memory_context_found", CHAT_SOURCE)
        self.assertIn("authoritative_response_required", CHAT_SOURCE)

    def test_tpc_gateway_and_reprime_contract_remain_present(self):
        self.assertIn("tpc.prime_now(", CHAT_SOURCE)
        self.assertIn("response = tpc.stream_response(", CHAT_SOURCE)
        self.assertIn("require_exact_prefix=require_exact_tpc_prefix", CHAT_SOURCE)
        self.assertIn("tpc.prime_async(", CHAT_SOURCE)
        self.assertIn('reason="completed_turn"', CHAT_SOURCE)
        self.assertIn("tpc.shutdown()", CHAT_SOURCE)

    def test_stop_recording_feedback_precedes_blocking_asr_result_wait(self):
        feedback = CHAT_SOURCE.index(
            "[ASR] recording_stopped=true transcribing=true"
        )
        stop_command = CHAT_SOURCE.index(
            'send_asr_command("STOP")',
            feedback,
        )
        result_wait = CHAT_SOURCE.index(
            "message = read_asr_message()",
            stop_command,
        )

        self.assertLess(feedback, stop_command)
        self.assertLess(stop_command, result_wait)

    def test_tpc_prime_overlaps_only_queued_audio_playback(self):
        turn_update = CHAT_SOURCE.index(
            "recent_prompt_memory.add_turn("
        )
        synthesis_done = CHAT_SOURCE.index(
            "text_queue.join()",
            turn_update,
        )
        prime = CHAT_SOURCE.index(
            'reason="completed_turn"',
            synthesis_done,
        )
        playback_drain = CHAT_SOURCE.index(
            "wait_for_audio_to_drain()",
            prime,
        )

        self.assertLess(synthesis_done, prime)
        self.assertLess(prime, playback_drain)

    def test_router_sections_have_explicit_begin_and_end_markers(self):
        sections = (
            "Checking invalid input",
            "Checking exit commands",
            "Checking direct memory correction",
            "Checking perspective correction",
            "Checking explicit recall",
            "Checking greeting or backchannel",
            "Checking detailed request",
            "Checking directive",
            "Checking answer to Nancee's previous question",
            "Checking complete personal update",
            "Checking incomplete personal fact or ambiguous fragment",
            "Checking ordinary question",
            "Default model route",
        )

        for section in sections:
            with self.subTest(section=section):
                self.assertIn(f"# Begin:: {section}", ROUTER_SOURCE)
                self.assertIn(f"# End:: {section}", ROUTER_SOURCE)


if __name__ == "__main__":
    unittest.main()
