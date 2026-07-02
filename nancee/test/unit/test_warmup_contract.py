#!/usr/bin/env python3
from __future__ import annotations

import json
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

SHERPA_DIRECTORY = REPOSITORY_ROOT / "sherpa"
sys.path.insert(
    0,
    str(SHERPA_DIRECTORY),
)

import config  # noqa: E402
import ollama_runtime  # noqa: E402
from ollama_runtime import (  # noqa: E402
    build_ollama_messages,
)
from prompt_identity import (  # noqa: E402
    json_sha256,
    text_sha256,
)
from warmup_contract import (  # noqa: E402
    CONTEXT_PRIME_USER_TEXT,
    build_startup_warmup_messages,
    build_warmup_fingerprint,
)


class WarmupContractTests(unittest.TestCase):
    def test_expected_model_is_configured(self):
        self.assertEqual(
            config.LLM_MODEL,
            "phi4-mini:3.8b",
        )

    def test_system_prompt_matches_approved_hash(self):
        expected_hash = (
            (SHERPA_DIRECTORY / "system-prompt.sha256")
            .read_text(
                encoding="utf-8",
            )
            .strip()
        )

        actual_hash = text_sha256(config.load_system_prompt())

        self.assertEqual(
            actual_hash,
            expected_hash,
            "system-prompt.txt changed. Review it, "
            "regenerate system-prompt.sha256, "
            "and rerun warmup.",
        )

    def test_warmup_uses_runtime_system_prompt(self):
        prompt = config.load_system_prompt()

        messages = build_startup_warmup_messages(prompt)

        self.assertEqual(
            messages[0],
            {
                "role": "system",
                "content": prompt,
            },
        )

    def test_service_preserves_literal_model_name(self):
        service_text = (SHERPA_DIRECTORY / "nancee-llm-warmup@.service").read_text(
            encoding="utf-8",
        )

        self.assertIn("%i", service_text)

        self.assertNotIn(
            "%I",
            service_text,
            "Uppercase %I changes the model-name hyphen into a slash.",
        )

    def test_warmup_helper_uses_configured_timeout(self):
        namespace = runpy.run_path(
            str(SHERPA_DIRECTORY / "nancee-ollama-warmup"),
            run_name="warmup_contract_test",
        )

        expected_timeout = max(
            30,
            config.OLLAMA_WARMUP_TIMEOUT - 10,
        )

        self.assertEqual(
            namespace["TOTAL_TIMEOUT_SECONDS"],
            expected_timeout,
        )

        self.assertLess(
            namespace["TOTAL_TIMEOUT_SECONDS"],
            config.OLLAMA_WARMUP_TIMEOUT,
        )

    def test_prime_and_request_share_exact_prefix(self):
        history = [
            {
                "role": "user",
                "content": "My favorite code is P0420.",
            },
            {
                "role": "assistant",
                "content": ("Well, that code concerns catalyst efficiency."),
            },
        ]

        memory_context = (
            "SESSION MEMORY - use only as context.\nCurrent topic: catalyst efficiency"
        )

        prime_messages = build_ollama_messages(
            user_text=CONTEXT_PRIME_USER_TEXT,
            history=history,
            memory_context=memory_context,
            retrieved_context="",
        )

        request_messages = build_ollama_messages(
            user_text="What code were we discussing?",
            history=history,
            memory_context=memory_context,
            retrieved_context="",
        )

        prime_prefix = prime_messages[:-1]
        request_prefix = request_messages[:-1]

        self.assertEqual(
            prime_prefix,
            request_prefix,
        )

        self.assertEqual(
            json_sha256(prime_prefix),
            json_sha256(request_prefix),
        )

        self.assertNotEqual(
            json_sha256(prime_messages),
            json_sha256(request_messages),
            "The full hashes should differ because the final user messages differ.",
        )

    def test_current_warmup_state_is_accepted(self):
        expected_state = build_warmup_fingerprint(
            config.LLM_MODEL,
            config.load_system_prompt(),
        )

        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "warmup-state.json"

            state_file.write_text(
                json.dumps(expected_state),
                encoding="utf-8",
            )

            with patch.object(
                ollama_runtime,
                "WARMUP_STATE_FILE",
                state_file,
            ):
                self.assertTrue(
                    ollama_runtime.is_current_warmup_state(config.LLM_MODEL)
                )

    def test_stale_prompt_state_is_rejected(self):
        stale_state = build_warmup_fingerprint(
            config.LLM_MODEL,
            config.load_system_prompt(),
        )

        stale_state["system_sha256"] = "stale-prompt-hash"

        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "warmup-state.json"

            state_file.write_text(
                json.dumps(stale_state),
                encoding="utf-8",
            )

            with patch.object(
                ollama_runtime,
                "WARMUP_STATE_FILE",
                state_file,
            ):
                self.assertFalse(
                    ollama_runtime.is_current_warmup_state(config.LLM_MODEL)
                )


if __name__ == "__main__":
    unittest.main()
