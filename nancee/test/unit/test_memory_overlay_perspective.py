import unittest

from sherpa.session_memory_store import MemoryHit, format_memory_overlay


class MemoryOverlayPerspectiveTests(unittest.TestCase):
    def test_overlay_labels_human_speaker_and_pronoun_mapping(self):
        overlay = format_memory_overlay([
            MemoryHit(
                id=1,
                raw_text="I bought hot sauce at Macy's.",
                search_text="bought hot sauce macy s",
                bm25_score=-1.0,
                created_ts=1.0,
                turn_id=1,
            )
        ])

        self.assertIn("MEMORY SPEAKER: human user", overlay)
        self.assertIn("answer as you/your", overlay)
        self.assertIn("I bought hot sauce", overlay)


if __name__ == "__main__":
    unittest.main()
