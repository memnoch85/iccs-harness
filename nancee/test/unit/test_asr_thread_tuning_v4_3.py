from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "asr/transcribe.py").read_text(encoding="utf-8")


class AsrThreadTuningV43Tests(unittest.TestCase):
    def test_thread_environment_controls_exist(self):
        self.assertIn("NANCEE_ASR_NUM_THREADS", SOURCE)
        self.assertIn("NANCEE_ASR_INTEROP_THREADS", SOURCE)

    def test_torch_thread_budget_is_applied_before_pipeline_creation(self):
        configure_index = SOURCE.index("configure_torch_threads()")
        pipeline_index = SOURCE.index("self.asr_pipeline = pipeline(")
        self.assertLess(configure_index, pipeline_index)
        self.assertIn("torch.set_num_threads(ASR_NUM_THREADS)", SOURCE)
        self.assertIn("torch.set_num_interop_threads(ASR_INTEROP_THREADS)", SOURCE)

    def test_runtime_reports_actual_thread_counts(self):
        self.assertIn("[ASR CONFIG]", SOURCE)
        self.assertIn("torch.get_num_threads()", SOURCE)
        self.assertIn("torch.get_num_interop_threads()", SOURCE)


if __name__ == "__main__":
    unittest.main()
