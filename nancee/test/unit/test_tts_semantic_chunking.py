import unittest
from sherpa.tts_chunking import extract_tts_chunk

class SemanticChunkingTests(unittest.TestCase):
    def test_later_chunk_prefers_comma(self):
        chunk, remainder = extract_tts_chunk(
            "A turbine spins quickly, forcing more air into the engine.",
            False,
        )
        self.assertEqual(chunk, "A turbine spins quickly,")
        self.assertEqual(remainder, "forcing more air into the engine.")

    def test_later_chunk_waits_for_lookahead(self):
        self.assertIsNone(extract_tts_chunk("forcing more air into the engine", False))

    def test_forced_chunk_avoids_connector(self):
        chunk, _ = extract_tts_chunk(
            "exhaust pressure spins the turbine and then pushes more air into the cylinders for combustion",
            False,
        )
        self.assertNotRegex(chunk.lower(), r"\b(?:and|the|to|of|with)$")

if __name__ == "__main__":
    unittest.main()
