from __future__ import annotations

import unittest
from unittest.mock import patch

import ollama_runtime


class TpcRouteInstructionContractTests(unittest.TestCase):
    def test_route_instruction_is_dynamic_after_stable_prefix(self):
        with patch.object(
            ollama_runtime,
            "load_system_prompt",
            return_value="SYSTEM",
        ):
            first = ollama_runtime.build_ollama_messages(
                user_text="Hello.",
                history=[{"role": "assistant", "content": "Hi."}],
                response_instruction="Be playful.",
            )
            second = ollama_runtime.build_ollama_messages(
                user_text="Hello.",
                history=[{"role": "assistant", "content": "Hi."}],
                response_instruction="Be exact.",
            )

        self.assertEqual(first[:-1], second[:-1])
        self.assertNotEqual(first[-1]["content"], second[-1]["content"])
        self.assertEqual(first[-1]["role"], "user")
        self.assertEqual(second[-1]["role"], "user")

    def test_route_instruction_does_not_change_prefix_fingerprint(self):
        with patch.object(
            ollama_runtime,
            "load_system_prompt",
            return_value="SYSTEM",
        ):
            expected = ollama_runtime.ollama_prefix_sha256(
                history=[],
                memory_context="",
            )
            messages = ollama_runtime.build_ollama_messages(
                user_text="Question",
                history=[],
                memory_context="",
                response_instruction="Route-specific constraint.",
            )

        self.assertEqual(
            expected,
            ollama_runtime.json_sha256(messages[:-1]),
        )


if __name__ == "__main__":
    unittest.main()
