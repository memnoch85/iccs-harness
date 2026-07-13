import unittest

from ollama_runtime import build_ollama_messages


class OllamaResponseInstructionTests(unittest.TestCase):
    def test_response_instruction_is_not_a_second_system_message(self):
        messages = build_ollama_messages(
            user_text="I finished wiring a power board today.",
            history=[],
            memory_context="",
            retrieved_context="",
            response_instruction="Acknowledge briefly.",
        )

        system_messages = [
            message
            for message in messages
            if message["role"] == "system"
        ]

        self.assertEqual(1, len(system_messages))
        self.assertEqual("user", messages[-1]["role"])
        self.assertIn(
            "TURN RESPONSE CONSTRAINT:",
            messages[-1]["content"],
        )
        self.assertIn(
            "I finished wiring a power board today.",
            messages[-1]["content"],
        )


if __name__ == "__main__":
    unittest.main()

