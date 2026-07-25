import unittest

from generation_completion import (
    prepare_clarification_response,
    trim_prompt_role_leak,
)
from session_memory_store import filter_memory_hits_by_overlap


class PromptRoleLeakGuardTests(unittest.TestCase):
    def test_trims_invented_next_user_turn(self):
        text = (
            "Sauron served Morgoth as his chief lieutenant.\n\n"
            "USER MESSAGE:\n"
            "What are your thoughts on artificial intelligence?\n"
            "ASSISTANT:"
        )

        cleaned, trimmed = trim_prompt_role_leak(text)

        self.assertTrue(trimmed)
        self.assertEqual(
            cleaned,
            "Sauron served Morgoth as his chief lieutenant.",
        )

    def test_normal_answer_is_unchanged(self):
        cleaned, trimmed = trim_prompt_role_leak(
            "Paris is the capital of France."
        )

        self.assertFalse(trimmed)
        self.assertEqual(cleaned, "Paris is the capital of France.")


class ClarificationGuardTests(unittest.TestCase):
    def test_length_cutoff_keeps_only_complete_first_sentence(self):
        answer, action = prepare_clarification_response(
            'Could you repeat that? I thought you said "drive',
            {"done_reason": "length"},
        )

        self.assertEqual(answer, "Could you repeat that?")
        self.assertEqual(action, "length_tail_trimmed")

    def test_length_cutoff_rejects_interjection_only_sentence(self):
        answer, action = prepare_clarification_response(
            (
                "Ah! Apologies for misunderstanding; "
                "I meant to say"
            ),
            {"done_reason": "length"},
        )

        self.assertEqual(
            answer,
            "Could you repeat that?",
        )
        self.assertEqual(
            action,
            "fallback_low_information",
        )

    def test_length_cutoff_keeps_meaningful_one_word_response(self):
        answer, action = prepare_clarification_response(
            (
                "Great! Is there anything else you'd like "
                "to check or set up on"
            ),
            {"done_reason": "length"},
        )

        self.assertEqual(
            answer,
            "Great!",
        )

        self.assertEqual(
            action,
            "length_tail_trimmed",
        )

    def test_length_cutoff_keeps_two_word_acknowledgment(self):
        answer, action = prepare_clarification_response(
            "Got it! I was going to add",
            {"done_reason": "length"},
        )

        self.assertEqual(
            answer,
            "Got it!",
        )
        self.assertEqual(
            action,
            "length_tail_trimmed",
        )

    def test_length_cutoff_without_sentence_uses_fallback(self):
        answer, action = prepare_clarification_response(
            'Did you mean "Drive',
            {"done_reason": "length"},
        )

        self.assertEqual(answer, "Could you repeat that?")
        self.assertEqual(action, "fallback")

    def test_stopped_clarification_uses_first_sentence(self):
        answer, action = prepare_clarification_response(
            "Could you repeat that? I did not catch the last word.",
            {"done_reason": "stop"},
        )

        self.assertEqual(answer, "Could you repeat that?")
        self.assertEqual(action, "accepted")


class MemoryRelevanceGuardTests(unittest.TestCase):
    def test_power_board_does_not_hijack_four_stroke_question(self):
        hits = [
            {
                "id": 1,
                "search_text": (
                    "finally finished wiring power board tonight"
                ),
            }
        ]

        filtered = filter_memory_hits_by_overlap(
            (
                "Explain in detail how a four stroke engine completes "
                "the intake compression power and exhaust cycle."
            ),
            hits,
            minimum_overlap=2,
        )

        self.assertEqual(filtered, [])

    def test_two_topic_terms_allow_background_enrichment(self):
        hit = {
            "id": 2,
            "search_text": "interested artificial intelligence",
        }

        filtered = filter_memory_hits_by_overlap(
            "What are your thoughts on artificial intelligence?",
            [hit],
            minimum_overlap=2,
        )

        self.assertEqual(filtered, [hit])


    def test_explicit_recall_can_keep_a_single_term_hit(self):
        hit = {
            "id": 4,
            "search_text": "bought jeans yesterday",
        }

        filtered = filter_memory_hits_by_overlap(
            "What did I buy?",
            [hit],
            minimum_overlap=2,
            allow_weak_match=True,
        )

        self.assertEqual(filtered, [hit])

    def test_finish_wiring_recall_has_two_term_overlap(self):
        hit = {
            "id": 3,
            "search_text": "finally finished wiring power board tonight",
        }

        filtered = filter_memory_hits_by_overlap(
            "What did I finish wiring?",
            [hit],
            minimum_overlap=2,
        )

        self.assertEqual(filtered, [hit])


class PipelineWiringContractTests(unittest.TestCase):
    def test_nancee_chat_wires_all_three_guards(self):
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[2]
            / "sherpa"
            / "nancee_chat.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "allow_weak_match=input_route.allow_weak_match",
            source,
        )
        self.assertIn(
            "buffer, role_leak_found = trim_prompt_role_leak(buffer)",
            source,
        )
        self.assertIn(
            'elif response_policy.name == "clarify":',
            source,
        )


if __name__ == "__main__":
    unittest.main()
