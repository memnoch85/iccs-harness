import unittest

from memory_policy import extract_simple_fact_correction
from session_memory_store import SessionMemoryStore


class SimpleMemoryCorrectionTests(unittest.TestCase):
    def test_extracts_direct_correction(self):
        self.assertEqual(
            extract_simple_fact_correction(
                "Actually, it was the ceramic mug, not the glass mug."
            ),
            (
                "the ceramic mug",
                "the glass mug",
            ),
        )

    def test_extracts_correction_inside_feedback(self):
        self.assertEqual(
            extract_simple_fact_correction(
                "That was a fail. I told you actually it was "
                "the power board not the USB controller."
            ),
            (
                "the power board",
                "the USB controller",
            ),
        )

    def test_rewrites_original_memory_and_preserves_action_terms(self):
        store = SessionMemoryStore()

        memory_id = store.add_memory(
            "Hey Nancy, I finally finished wiring "
            "the USB controller tonight."
        )

        corrected_id = store.apply_simple_correction(
            new_value="the power board",
            old_value="the USB controller",
        )

        self.assertEqual(corrected_id, memory_id)

        hits = store.search_memory(
            "What did I finish wiring?",
            limit=3,
        )

        self.assertTrue(hits)
        self.assertIn(
            "power board",
            hits[0].raw_text.lower(),
        )
        self.assertNotIn(
            "controller",
            hits[0].raw_text.lower(),
        )


if __name__ == "__main__":
    unittest.main()
