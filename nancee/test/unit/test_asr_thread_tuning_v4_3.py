import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

CONFIG_SOURCE = (
    ROOT / "sherpa" / "config.py"
).read_text(
    encoding="utf-8",
)

TRANSCRIBE_SOURCE = (
    ROOT / "asr" / "transcribe.py"
).read_text(
    encoding="utf-8",
)


class AsrThreadTuningV43Tests(unittest.TestCase):
    """
    Verify the current Faster-Whisper thread configuration contract.

    The previous Hugging Face backend configured PyTorch using
    torch.set_num_threads() and torch.set_num_interop_threads().

    Faster-Whisper uses CTranslate2 instead. Its CPU thread budget is passed
    directly into WhisperModel through the cpu_threads argument.
    """

    def test_thread_environment_control_exists_in_config(self):
        self.assertIn(
            "NANCEE_ASR_THREADS",
            CONFIG_SOURCE,
        )

        self.assertIn(
            "ASR_THREADS",
            TRANSCRIBE_SOURCE,
        )

    def test_thread_budget_is_applied_to_faster_whisper(self):
        model_index = TRANSCRIBE_SOURCE.index(
            "WhisperModel("
        )

        thread_index = TRANSCRIBE_SOURCE.index(
            "cpu_threads=self.cpu_threads",
            model_index,
        )

        self.assertGreater(
            thread_index,
            model_index,
        )

    def test_runtime_reports_selected_thread_count(self):
        self.assertIn(
            '"[ASR] Loading "',
            TRANSCRIBE_SOURCE,
        )

        self.assertIn(
            'f"backend={self.backend} "',
            TRANSCRIBE_SOURCE,
        )

        self.assertIn(
            'f"threads={self.cpu_threads} "',
            TRANSCRIBE_SOURCE,
        )

    def test_benchmarked_default_thread_count(self):
        self.assertIn(
            '"NANCEE_ASR_THREADS"',
            CONFIG_SOURCE,
        )

        self.assertIn(
            '"4"',
            CONFIG_SOURCE,
        )


if __name__ == "__main__":
    unittest.main()
