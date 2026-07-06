import unittest

from short_term_memory import ShortTermMemory


class TestShortTermMemory(unittest.TestCase):
    def test_recent_prompt_memory_keeps_one_turn(self):
        memory = ShortTermMemory(max_turns=1)

        memory.add_turn("user 1", "Okay.")
        evicted = memory.add_turn("user 2", "Okay.")

        self.assertEqual(
            evicted,
            {
                "user": "user 1",
                "assistant": "Okay.",
            },
        )

        self.assertEqual(memory.get_stats()["turn_count"], 1)
        self.assertEqual(memory.get_messages()[0]["content"], "user 2")

    def test_recent_prompt_messages_preserve_roles(self):
        memory = ShortTermMemory(max_turns=1)
        memory.add_turn("question", "Okay.")

        self.assertEqual(
            memory.get_messages(),
            [
                {
                    "role": "user",
                    "content": "question",
                },
                {
                    "role": "assistant",
                    "content": "Okay.",
                },
            ],
        )

    def test_unbounded_mode_still_available_for_tests_or_tools(self):
        memory = ShortTermMemory(max_turns=None)

        memory.add_turn("user 1", "Okay.")
        memory.add_turn("user 2", "Okay.")

        self.assertEqual(memory.get_stats()["turn_count"], 2)

    def test_turn_text_is_cleaned(self):
        memory = ShortTermMemory(max_turns=1)

        memory.add_turn("  hello  ", "  Okay.  ")

        self.assertEqual(memory.get_messages()[0]["content"], "hello")
        self.assertEqual(memory.get_messages()[1]["content"], "Okay.")

    def test_empty_user_text_is_rejected(self):
        memory = ShortTermMemory(max_turns=1)

        with self.assertRaises(ValueError):
            memory.add_turn("   ", "Okay.")

    def test_empty_assistant_text_is_rejected(self):
        memory = ShortTermMemory(max_turns=1)

        with self.assertRaises(ValueError):
            memory.add_turn("hello", "   ")

    def test_max_turn_validation(self):
        with self.assertRaises(TypeError):
            ShortTermMemory(max_turns=True)

        with self.assertRaises(TypeError):
            ShortTermMemory(max_turns="1")

        with self.assertRaises(ValueError):
            ShortTermMemory(max_turns=0)

        with self.assertRaises(ValueError):
            ShortTermMemory(max_turns=-1)

    def test_clear_session_clears_turns(self):
        memory = ShortTermMemory(max_turns=1)

        memory.add_turn("hello", "Okay.")
        memory.clear_session()

        self.assertEqual(memory.get_stats()["turn_count"], 0)
        self.assertEqual(memory.get_messages(), [])


if __name__ == "__main__":
    unittest.main()
