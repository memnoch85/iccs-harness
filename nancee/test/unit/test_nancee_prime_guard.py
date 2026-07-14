import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ollama_runtime
from config import (
    LLM_MODEL,
    load_system_prompt,
)
from warmup_contract import build_warmup_fingerprint


class NanceePrimeGuardTests(unittest.TestCase):
    def setUp(self):
        self.current_fingerprint = build_warmup_fingerprint(
            LLM_MODEL,
            load_system_prompt(),
        )

    @staticmethod
    def write_state(path, state):
        path.write_text(
            json.dumps(state),
            encoding="utf-8",
        )

    def test_current_warmup_fingerprint_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "warmup-state.json"

            self.write_state(
                state_file,
                self.current_fingerprint,
            )

            with patch.object(
                ollama_runtime,
                "WARMUP_STATE_FILE",
                state_file,
            ):
                self.assertTrue(
                    ollama_runtime.is_current_warmup_state(
                        LLM_MODEL
                    )
                )

    def test_stale_warmup_fingerprint_is_rejected(self):
        stale_values = {
            "model": "not-the-current-model",
            "system_sha256": "0" * 64,
            "warmup_full_sha256": "f" * 64,
            "warmup_format_version": (
                int(
                    self.current_fingerprint[
                        "warmup_format_version"
                    ]
                )
                + 1
            ),
        }

        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "warmup-state.json"

            with patch.object(
                ollama_runtime,
                "WARMUP_STATE_FILE",
                state_file,
            ):
                for field, stale_value in stale_values.items():
                    with self.subTest(field=field):
                        stale_state = dict(
                            self.current_fingerprint
                        )

                        stale_state[field] = stale_value

                        self.write_state(
                            state_file,
                            stale_state,
                        )

                        self.assertFalse(
                            ollama_runtime.is_current_warmup_state(
                                LLM_MODEL
                            )
                        )

    def test_missing_warmup_state_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            missing_file = (
                Path(directory)
                / "does-not-exist.json"
            )

            with patch.object(
                ollama_runtime,
                "WARMUP_STATE_FILE",
                missing_file,
            ):
                self.assertFalse(
                    ollama_runtime.is_current_warmup_state(
                        LLM_MODEL
                    )
                )


if __name__ == "__main__":
    unittest.main()
