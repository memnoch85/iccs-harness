from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHAT_SOURCE = (ROOT / "sherpa" / "nancee_chat.py").read_text(encoding="utf-8")
ROUTER_SOURCE = (ROOT / "sherpa" / "input_router.py").read_text(encoding="utf-8")
ROUTERMON_SOURCE = (ROOT / "sherpa" / "router_mon.py").read_text(encoding="utf-8")


class RouterRuntimeContractV3Tests(unittest.TestCase):
    def test_chat_routes_each_user_input_once(self):
        self.assertEqual(1, CHAT_SOURCE.count("route_user_input("))
        self.assertIn("[INPUT ROUTE]", CHAT_SOURCE)

    def test_routermon_owns_conversational_routing(self):
        self.assertIn("classify_router_mon(raw_text)", ROUTER_SOURCE)
        self.assertNotIn("import re", ROUTER_SOURCE)
        self.assertNotIn("re.compile", ROUTER_SOURCE)
        self.assertNotIn("_HARD_GREETING_PATTERN", ROUTER_SOURCE)
        self.assertNotIn("looks_like_perspective_correction", ROUTER_SOURCE)
        self.assertNotIn("_looks_like_overshare", ROUTERMON_SOURCE)
        self.assertNotIn("overshare_rule", ROUTERMON_SOURCE)
        self.assertNotIn("import re", ROUTERMON_SOURCE)

        for token in (
            "_FAST_AFFIRMATIVE",
            "_FAST_NEGATIVE",
            "_FAST_FAREWELL",
            "leading_hello_or_hi",
            "reason=\"explicit_memory_store\"",
            "reason=\"contextual_answer\"",
            "reason=\"simple_fact_correction\"",
            "reason=\"perspective_correction\"",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, ROUTER_SOURCE)

    def test_post_route_parsing_only_attaches_metadata(self):
        self.assertIn('if intent == "memory_store":', ROUTER_SOURCE)
        self.assertIn("extract_simple_fact_correction(raw_text)", ROUTER_SOURCE)
        self.assertIn("extract_explicit_memory_store_payload(raw_text)", ROUTER_SOURCE)
        self.assertIn("extract_pending_memory_topic(raw_text)", ROUTER_SOURCE)
        self.assertIn("resolve_contextual_answer_memory(", ROUTER_SOURCE)
        self.assertIn('if intent == "greeting":', ROUTER_SOURCE)
        self.assertIn('if intent in {"affirmative", "negative"}:', ROUTER_SOURCE)

    def test_short_greeting_can_disable_latency_bridge(self):
        self.assertIn("skip_latency_bridge: bool = False", ROUTER_SOURCE)
        self.assertIn("skip_latency_bridge=True", ROUTER_SOURCE)
        self.assertIn("and not input_route.skip_latency_bridge", CHAT_SOURCE)

    def test_model_recall_does_not_enter_llm_prompt(self):
        self.assertIn('input_route.kind == "model_recall"', CHAT_SOURCE)
        self.assertIn("assistant_recall_memory.retrieve_response(", CHAT_SOURCE)
        self.assertIn("[MODEL MEMORY DIRECT]", CHAT_SOURCE)
        self.assertIn("prompt_injection=false", CHAT_SOURCE)

        # The only Ollama gateway remains the existing ICCS respond call.
        self.assertEqual(1, CHAT_SOURCE.count("response = iccs.respond("))
        self.assertIn("if model_recall_requested:", CHAT_SOURCE)
        self.assertIn("else:\n                        response = iccs.respond(", CHAT_SOURCE)

    def test_model_recall_settles_pending_iccs_prime_before_direct_replay(self):
        direct_branch = CHAT_SOURCE.index(
            "# A normal turn consumes/clears the previous completed-turn"
        )
        settle = CHAT_SOURCE.index(
            "iccs.wait_for_prepared_prefix()",
            direct_branch,
        )
        replay = CHAT_SOURCE.index(
            "[MODEL MEMORY DIRECT]",
            settle,
        )
        completed_turn_prime = CHAT_SOURCE.index(
            'reason="completed_turn"',
            replay,
        )

        self.assertLess(settle, replay)
        self.assertLess(replay, completed_turn_prime)

    def test_ask_me_pending_answer_uses_existing_user_memory_only(self):
        self.assertIn("pending_memory_topic: str | None = None", ROUTER_SOURCE)
        self.assertIn("pending_memory_topic=extract_pending_memory_topic(raw_text)", ROUTER_SOURCE)
        self.assertIn("pending_user_memory_topic = None", CHAT_SOURCE)
        self.assertIn("pending_answer_memory = build_pending_answer_memory(", CHAT_SOURCE)
        self.assertIn("elif pending_answer_memory:", CHAT_SOURCE)

        # The pending state is memory bookkeeping, not a new LLM prompt field.
        prompt_call = CHAT_SOURCE.split("response = iccs.respond(", 1)[1].split(")", 1)[0]
        self.assertNotIn("pending_", prompt_call)

    def test_assistant_memory_only_stores_question_and_detailed(self):
        self.assertIn(
            'if input_route.kind in {"question", "detailed"}:',
            CHAT_SOURCE,
        )
        self.assertIn("assistant_recall_memory.add_response(", CHAT_SOURCE)

    def test_existing_prompt_arguments_are_unchanged(self):
        self.assertIn("memory_context=\"\"", CHAT_SOURCE)
        self.assertIn("retrieved_context=retrieved_context", CHAT_SOURCE)
        self.assertIn("response_instruction=response_policy.instruction", CHAT_SOURCE)
        self.assertNotIn("routerMon", CHAT_SOURCE.split("response = iccs.respond(", 1)[1].split(")", 1)[0])

    def test_iccs_gateway_and_reprime_contract_remain_present(self):
        self.assertIn("iccs.prime_startup(", CHAT_SOURCE)
        self.assertIn("response = iccs.respond(", CHAT_SOURCE)
        self.assertIn("require_exact_prefix=require_exact_iccs_prefix", CHAT_SOURCE)
        self.assertIn("iccs.prime_next(", CHAT_SOURCE)
        self.assertIn('reason="completed_turn"', CHAT_SOURCE)
        self.assertIn("iccs.close()", CHAT_SOURCE)

    def test_router_model_load_is_after_startup_prime(self):
        prime = CHAT_SOURCE.index("iccs.prime_startup(")
        load = CHAT_SOURCE.index("load_router_mon()", prime)
        self.assertLess(prime, load)

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

    def test_iccs_prime_overlaps_only_queued_audio_playback(self):
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


if __name__ == "__main__":
    unittest.main()
