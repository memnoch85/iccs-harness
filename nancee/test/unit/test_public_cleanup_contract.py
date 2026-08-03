from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHERPA = ROOT / "sherpa"
TESTS = ROOT / "test" / "unit"
TOOLS = ROOT / "tools"


class PublicCleanupContractTests(unittest.TestCase):
    def test_old_checkout_paths_are_absent(self):
        transcribe = (ROOT / "asr" / "transcribe.py").read_text(
            encoding="utf-8"
        )
        benchmark = (TOOLS / "iccs_prefix_benchmark.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("$HOME/Nancee", transcribe)
        self.assertNotIn('Path.home() / "Nancee"', benchmark)
        self.assertNotIn("Nancee-benchmarks", benchmark)

    def test_public_router_has_no_vehicle_specific_shortcuts(self):
        router = (SHERPA / "input_router.py").read_text(
            encoding="utf-8"
        )

        for phrase in (
            "what am i driving",
            "what car",
            "what vehicle",
            "kind of car",
            "type of vehicle",
        ):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, router.lower())

    def test_speaker_named_test_and_unit_benchmark_are_absent(self):
        self.assertFalse(
            (TESTS / "test_input_router_speaker_v4_2.py").exists()
        )
        self.assertFalse(
            (TESTS / "iccs_prefix_bench_v2.py").exists()
        )
        self.assertTrue(
            (TOOLS / "iccs_prefix_benchmark.py").is_file()
        )

    def test_two_stage_startup_contract_remains(self):
        chat = (SHERPA / "nancee_chat.py").read_text(
            encoding="utf-8"
        )

        warmup_index = chat.index("ensure_ollama_model_loaded(")
        startup_prime_index = chat.index("iccs.prime_startup(")

        self.assertLess(warmup_index, startup_prime_index)


if __name__ == "__main__":
    unittest.main()
