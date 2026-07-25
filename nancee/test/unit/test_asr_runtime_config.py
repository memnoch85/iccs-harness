import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SHERPA = ROOT / "sherpa"

if str(SHERPA) not in sys.path:
    sys.path.insert(0, str(SHERPA))


class AsrRuntimeConfigTests(unittest.TestCase):
    def load_config(self):
        sys.modules.pop("config", None)
        import config
        return config

    def tearDown(self):
        sys.modules.pop("config", None)

    def test_default_backend_matches_benchmark_winner(self):
        controlled = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("NANCEE_ASR_")
        }

        with patch.dict(os.environ, controlled, clear=True):
            config = self.load_config()

        self.assertEqual("faster_whisper", config.ASR_BACKEND)
        self.assertEqual("base.en", config.ASR_MODEL)
        self.assertEqual("int8", config.ASR_COMPUTE_TYPE)
        self.assertEqual(4, config.ASR_THREADS)
        self.assertEqual(1, config.ASR_BEAM_SIZE)
        self.assertFalse(config.ASR_VAD_FILTER)
        self.assertEqual(16000, config.ASR_SAMPLE_RATE)

    def test_hf_backend_selects_hf_model_identifier(self):
        controlled = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("NANCEE_ASR_")
        }
        controlled["NANCEE_ASR_BACKEND"] = "hf_direct"

        with patch.dict(os.environ, controlled, clear=True):
            config = self.load_config()

        self.assertEqual("hf_direct", config.ASR_BACKEND)
        self.assertEqual(
            "openai/whisper-base.en",
            config.ASR_MODEL,
        )


if __name__ == "__main__":
    unittest.main()
