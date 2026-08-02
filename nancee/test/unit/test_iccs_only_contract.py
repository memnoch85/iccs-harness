from pathlib import Path
import unittest

from response_policy import response_policy_for_route
from warmup_contract import (
    CONTEXT_PRIME_EXPECTED_REPLY,
    CONTEXT_PRIME_NUM_PREDICT,
    CONTEXT_PRIME_TEMPERATURE,
    CONTEXT_PRIME_USER_TEXT,
)


ROOT = Path(__file__).resolve().parents[2]
SHERPA = ROOT / "sherpa"


class IccsOnlyContractTests(unittest.TestCase):
    def test_legacy_cache_runtime_is_absent(self):
        self.assertFalse((SHERPA / ("tenacious_" + "prefix_cache.py")).exists())

        runtime = (SHERPA / "ollama_runtime.py").read_text(encoding="utf-8")
        chat = (SHERPA / "nancee_chat.py").read_text(encoding="utf-8")

        for token in (
            "Tenacious" + "PrefixCache",
            "create_ollama_" + "tpc",
            "[" + "TPC" + " PRIME]",
            "[" + "TPC" + " PREFIX]",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, runtime)
                self.assertNotIn(token, chat)

        self.assertIn("create_ollama_iccs", runtime)
        self.assertIn("iccs = create_ollama_iccs()", chat)

    def test_prime_contract_is_one_lowercase_k(self):
        self.assertEqual("k", CONTEXT_PRIME_EXPECTED_REPLY)
        self.assertIn("lowercase k", CONTEXT_PRIME_USER_TEXT)
        self.assertEqual(0.0, CONTEXT_PRIME_TEMPERATURE)
        self.assertEqual(1, CONTEXT_PRIME_NUM_PREDICT)

    def test_normal_route_has_no_dynamic_instruction(self):
        self.assertEqual(
            "",
            response_policy_for_route("normal").instruction,
        )

    def test_live_iccs_prefix_has_no_turn_specific_memory_context(self):
        chat = (SHERPA / "nancee_chat.py").read_text(encoding="utf-8")
        self.assertIn('memory_context="",', chat)
        self.assertNotIn("request_memory_context", chat)


if __name__ == "__main__":
    unittest.main()
