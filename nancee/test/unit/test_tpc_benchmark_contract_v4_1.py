from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
BENCH = (ROOT / "tools" / "tpc_routing_benchmark.py").read_text(encoding="utf-8")
COMPARE = (ROOT / "tools" / "compare_tpc_routing_benchmark.py").read_text(encoding="utf-8")
RUNNER = (ROOT / "tools" / "run_tpc_routing_benchmark.sh").read_text(encoding="utf-8")


class TpcBenchmarkContractV41Tests(unittest.TestCase):
    def test_benchmark_has_exactly_thirty_cases(self):
        self.assertEqual(30, BENCH.count("BenchmarkCase("))

    def test_benchmark_supports_both_modes(self):
        self.assertIn('choices=("tpc", "no-tpc")', BENCH)
        self.assertIn('if args.mode == "tpc":', BENCH)

    def test_runner_resets_model_between_modes(self):
        self.assertIn('ollama stop "$model"', RUNNER)

    def test_runner_has_configurable_thermal_cooldown(self):
        self.assertIn("NANCEE_BENCH_COOLDOWN_SECONDS", RUNNER)
        self.assertIn('sleep "$cooldown_seconds"', RUNNER)

    def test_benchmark_uses_zero_temperature_and_fixed_token_cap(self):
        self.assertIn("default=0.0", BENCH)
        self.assertIn("default=12", BENCH)

    def test_foreground_metrics_include_tpc_wait(self):
        self.assertIn('"foreground_first_token_seconds"', BENCH)
        self.assertIn("tpc_wait_seconds", BENCH)
        self.assertIn("Foreground metrics include any TPC wait", COMPARE)

    def test_comparison_uses_steady_state_turns(self):
        self.assertIn('tpc["steady_state"]', COMPARE)
        self.assertIn("turns 2-30", COMPARE)


if __name__ == "__main__":
    unittest.main()
