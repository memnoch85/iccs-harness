import unittest

from sherpa.tts_chunking import extract_tts_chunk


class SemanticChunkingTests(unittest.TestCase):
    def test_later_chunk_prefers_comma(self):
        chunk, remainder = extract_tts_chunk(
            "A scheduler runs quickly, assigning more work to each thread.",
            False,
        )
        self.assertEqual(chunk, "A scheduler runs quickly,")
        self.assertEqual(remainder, "assigning more work to each thread.")

    def test_later_chunk_waits_for_lookahead(self):
        self.assertIsNone(extract_tts_chunk("assigning more work to each thread", False))

    def test_forced_chunk_avoids_connector(self):
        chunk, _ = extract_tts_chunk(
            "exhaust pressure spins the turbine and then pushes more air into the cylinders for combustion",
            False,
        )
        self.assertNotRegex(chunk.lower(), r"\b(?:and|the|to|of|with)$")

if __name__ == "__main__":
    unittest.main()
