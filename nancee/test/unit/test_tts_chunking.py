import unittest

from tts_chunking import (
    extract_tts_chunk,
    is_filler_preface,
)


class TestTtsChunking(unittest.TestCase):
    def test_first_chunk_does_not_split_mix_up(self):
        self.assertEqual(
            extract_tts_chunk(
                (
                    "Apologies for that mix up; "
                    "you were right. "
                ),
                is_first=True,
            ),
            (
                "Apologies for that",
                "mix up; you were right. ",
            ),
        )

    def test_stream_waits_when_buffer_ends_at_mix(self):
        self.assertIsNone(
            extract_tts_chunk(
                "Apologies for that mix ",
                is_first=True,
            )
        )

    def test_first_chunk_emits_at_one_word_punctuation(self):
        self.assertEqual(
            extract_tts_chunk(
                "Absolutely, ",
                is_first=True,
            ),
            (
                "Absolutely,",
                "",
            ),
        )

    def test_later_chunk_prefers_four_word_punctuation(self):
        self.assertEqual(
            extract_tts_chunk(
                "this is exactly four, ",
                is_first=False,
            ),
            (
                "this is exactly four,",
                "",
            ),
        )

    def test_ten_words_without_punctuation_waits_for_lookahead(self):
        self.assertIsNone(
            extract_tts_chunk(
                "one two three four five six seven eight nine ten ",
                False,
            )
        )

    def test_nine_word_complete_sentence_stays_together(self):
        self.assertEqual(
            extract_tts_chunk(
                "one two three four five six seven eight nine. ",
                False,
            ),
            (
                "one two three four five six seven eight nine.",
                "",
            ),
        )

    def test_nine_words_without_punctuation_wait(self):
        self.assertIsNone(
            extract_tts_chunk(
                ("one two three four five six seven eight nine "),
                is_first=False,
            )
        )

    def test_eight_words_without_lookahead_wait(self):
        self.assertIsNone(
            extract_tts_chunk(
                ("one two three four five six seven eight "),
                is_first=False,
            )
        )

    def test_punctuation_only_is_never_emitted(self):
        self.assertIsNone(
            extract_tts_chunk(
                "? ",
                is_first=True,
            )
        )

    def test_filler_prefaces_are_detected(self):
        for text in (
            "Well,",
            "Actually...",
            "Hang on,",
            "*Okay*,",
        ):
            with self.subTest(text=text):
                self.assertTrue(is_filler_preface(text))

    def test_complete_sentence_is_not_filler(self):
        self.assertFalse(is_filler_preface("Well, the coolant is stable."))


if __name__ == "__main__":
    unittest.main()
