import unittest

from tts_chunking import extract_tts_chunk


class TtsStreamWordBoundaryTests(unittest.TestCase):
    def test_partial_final_word_is_not_emitted(self):
        self.assertIsNone(
            extract_tts_chunk(
                "Your name is N",
                True,
            )
        )

    def test_completed_name_can_be_emitted(self):
        result = extract_tts_chunk(
            "Your name is Anders. ",
            True,
        )

        self.assertIsNotNone(result)
        chunk, remainder = result
        self.assertEqual(chunk, "Your name is Anders.")
        self.assertEqual(remainder, "")


if __name__ == "__main__":
    unittest.main()
