from __future__ import annotations

import unittest
from unittest.mock import patch

import ollama_runtime
from prompt_identity import json_sha256


class IccsOllamaContractV2Tests(unittest.TestCase):

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

    def test_factory_binds_iccs_to_the_proven_ollama_backend(self):
        controller = ollama_runtime.create_ollama_iccs()

        try:
            self.assertIsInstance(
                controller._backend,
                ollama_runtime.OllamaIccsBackend,
            )
            self.assertIs(
                controller._backend.build_prefix.__func__,
                ollama_runtime.OllamaIccsBackend.build_prefix,
            )
            self.assertIs(
                controller._backend.prime.__func__,
                ollama_runtime.OllamaIccsBackend.prime,
            )
            self.assertIs(
                controller._backend.stream.__func__,
                ollama_runtime.OllamaIccsBackend.stream,
            )
        finally:
            controller.close()


if __name__ == "__main__":
    unittest.main()
