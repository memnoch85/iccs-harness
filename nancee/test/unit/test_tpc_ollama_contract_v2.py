from __future__ import annotations

import unittest
from unittest.mock import patch

import ollama_runtime
from prompt_identity import json_sha256


class TpcOllamaContractV2Tests(unittest.TestCase):
    def test_prefix_fingerprint_hashes_only_stable_prefix(self):
        history = [
            {"role": "user", "content": "Previous user."},
            {"role": "assistant", "content": "Previous answer."},
        ]

        with patch.object(
            ollama_runtime,
            "load_system_prompt",
            return_value="SYSTEM",
        ):
            expected_messages = ollama_runtime.build_ollama_prefix_messages(
                history=history,
                memory_context="PROFILE",
            )
            actual = ollama_runtime.ollama_prefix_sha256(
                history=history,
                memory_context="PROFILE",
            )

        self.assertEqual(json_sha256(expected_messages), actual)

    def test_dynamic_retrieval_does_not_change_stable_prefix_function(self):
        history = [{"role": "user", "content": "Previous user."}]

        with patch.object(
            ollama_runtime,
            "load_system_prompt",
            return_value="SYSTEM",
        ):
            stable_hash = ollama_runtime.ollama_prefix_sha256(
                history=history,
                memory_context="",
            )
            full_messages = ollama_runtime.build_ollama_messages(
                user_text="What did I buy?",
                history=history,
                memory_context="",
                retrieved_context="Confirmed memory: hot sauce.",
                response_instruction="Answer briefly.",
            )
            stable_messages = ollama_runtime.build_ollama_prefix_messages(
                history=history,
                memory_context="",
            )

        self.assertEqual(json_sha256(stable_messages), stable_hash)
        self.assertEqual(stable_messages, full_messages[: len(stable_messages)])
        self.assertGreater(len(full_messages), len(stable_messages))

    def test_factory_owns_prime_request_and_fingerprint_functions(self):
        tpc = ollama_runtime.create_ollama_tpc()

        try:
            self.assertIs(tpc._prime_function, ollama_runtime.prime_ollama_context)
            self.assertIs(tpc._request_function, ollama_runtime.stream_ollama_response)
            self.assertIs(
                tpc._prefix_fingerprint_function,
                ollama_runtime.ollama_prefix_sha256,
            )
        finally:
            tpc.shutdown()


if __name__ == "__main__":
    unittest.main()
