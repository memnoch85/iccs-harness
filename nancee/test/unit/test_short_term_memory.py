import unittest

from short_term_memory import ShortTermMemory


class TestShortTermMemory(unittest.TestCase):
    def test_max_turn_validation(self):
        with self.assertRaises(TypeError):
            ShortTermMemory(max_turns=True)

        with self.assertRaises(TypeError):
            ShortTermMemory(max_turns="1")

        with self.assertRaises(ValueError):
            ShortTermMemory(max_turns=-1)

    def test_zero_turn_mode_keeps_no_prompt_history(self):
        memory = ShortTermMemory(max_turns=0)

        memory.add_turn("hello", "okay")

        self.assertEqual(memory.get_messages(), [])
        self.assertEqual(memory.get_stats()["turn_count"], 0)
        self.assertEqual(memory.get_stats()["message_count"], 0)

    def test_recent_prompt_memory_keeps_one_turn(self):
        memory = ShortTermMemory(max_turns=1)

        memory.add_turn("first user", "first assistant")
        evicted = memory.add_turn("second user", "second assistant")

        self.assertEqual(evicted["user"], "first user")

        self.assertEqual(
            memory.get_messages(),
            [
                {"role": "user", "content": "second user"},
                {"role": "assistant", "content": "second assistant"},
            ],
        )

    def test_recent_prompt_messages_preserve_roles(self):
        memory = ShortTermMemory(max_turns=2)

        memory.add_turn("user one", "assistant one")
        memory.add_turn("user two", "assistant two")

        self.assertEqual(
            memory.get_messages(),
            [
                {"role": "user", "content": "user one"},
                {"role": "assistant", "content": "assistant one"},
                {"role": "user", "content": "user two"},
                {"role": "assistant", "content": "assistant two"},
            ],
        )

    def test_turn_text_is_cleaned(self):
        memory = ShortTermMemory(max_turns=1)

        memory.add_turn("  hello  ", "  okay  ")

        self.assertEqual(
            memory.get_turns_snapshot(),
            [
                {
                    "user": "hello",
                    "assistant": "okay",
                }
            ],
        )

    def test_empty_user_text_is_rejected(self):
        memory = ShortTermMemory(max_turns=1)

        with self.assertRaises(ValueError):
            memory.add_turn("", "okay")

    def test_empty_assistant_text_is_rejected(self):
        memory = ShortTermMemory(max_turns=1)

        with self.assertRaises(ValueError):
            memory.add_turn("hello", "")

    def test_unbounded_mode_still_available_for_tests_or_tools(self):
        memory = ShortTermMemory(max_turns=None)

        for index in range(5):
            memory.add_turn(f"user {index}", f"assistant {index}")

        self.assertEqual(memory.get_stats()["turn_count"], 5)


if __name__ == "__main__":
    unittest.main()
