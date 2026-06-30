import unittest

from short_term_memory import ShortTermMemory


class TestShortTermMemory(unittest.TestCase):
    def test_default_history_is_unbounded(self):
        memory = ShortTermMemory()

        for index in range(10):
            memory.add_turn(
                f"user {index}",
                f"assistant {index}",
            )

        self.assertEqual(memory.get_stats()["turn_count"], 10)
        self.assertEqual(memory.get_messages()[0]["content"], "user 0")

    def test_explicit_none_is_unbounded(self):
        memory = ShortTermMemory(max_turns=None)

        for index in range(5):
            evicted = memory.add_turn(
                f"user {index}",
                f"assistant {index}",
            )
            self.assertIsNone(evicted)

        self.assertEqual(memory.get_stats()["turn_count"], 5)

    def test_optional_bounded_mode_evicts_oldest_turn(self):
        memory = ShortTermMemory(max_turns=2)
        memory.add_turn("u1", "a1")
        memory.add_turn("u2", "a2")
        evicted = memory.add_turn("u3", "a3")

        self.assertEqual(evicted, {"user": "u1", "assistant": "a1"})
        self.assertEqual(memory.get_stats()["turn_count"], 2)
        self.assertEqual(memory.get_messages()[0]["content"], "u2")

    def test_max_turn_validation(self):
        with self.assertRaises(TypeError):
            ShortTermMemory(max_turns=True)

        with self.assertRaises(TypeError):
            ShortTermMemory(max_turns="3")

        with self.assertRaises(ValueError):
            ShortTermMemory(max_turns=0)

    def test_messages_preserve_roles_and_order(self):
        memory = ShortTermMemory()
        memory.add_turn("question", "answer")

        self.assertEqual(
            memory.get_messages(),
            [
                {"role": "user", "content": "question"},
                {"role": "assistant", "content": "answer"},
            ],
        )

    def test_turn_text_is_cleaned(self):
        memory = ShortTermMemory()
        memory.add_turn("  hello  ", "  hi  ")

        self.assertEqual(memory.get_messages()[0]["content"], "hello")
        self.assertEqual(memory.get_messages()[1]["content"], "hi")

        with self.assertRaises(ValueError):
            memory.add_turn("   ", "answer")

    def test_empty_working_state_builds_no_context_message(self):
        memory = ShortTermMemory()
        self.assertEqual(memory.build_memory_context(), "")

    def test_structured_state_builds_compact_context(self):
        memory = ShortTermMemory()
        memory.set_current_topic("catalyst efficiency")
        memory.set_referenced_component("catalytic converter")
        memory.set_last_dtc_codes([" p0420 ", "P0420", "p0300"])
        memory.set_pid_reading("coolant_temp_f", 203)
        memory.set_pending_confirmation("clear stored DTCs")
        memory.set_vehicle_state(moving=False, engine_running=True)

        context = memory.build_memory_context()

        self.assertIn("Current topic: catalyst efficiency", context)
        self.assertIn("Last DTC codes: P0420, P0300", context)
        self.assertIn('"coolant_temp_f": 203', context)
        self.assertIn("Pending confirmation: clear stored DTCs", context)
        self.assertIn('"engine_running": true', context)

    def test_working_state_survives_optional_turn_eviction(self):
        memory = ShortTermMemory(max_turns=1)
        memory.set_last_dtc_codes(["P0420"])
        memory.add_turn("first", "reply one")
        memory.add_turn("second", "reply two")

        self.assertIn("P0420", memory.build_memory_context())
        self.assertEqual(memory.get_stats()["turn_count"], 1)

    def test_snapshot_is_a_deep_copy(self):
        memory = ShortTermMemory()
        memory.set_last_dtc_codes(["P0420"])

        snapshot = memory.snapshot()
        snapshot["working_memory"]["last_dtc_codes"].append("P0300")

        self.assertNotIn("P0300", memory.build_memory_context())

    def test_clear_and_clear_session_have_different_scope(self):
        memory = ShortTermMemory()
        memory.add_turn("hello", "hi")
        memory.set_last_dtc_codes(["P0420"])

        memory.clear()
        self.assertEqual(memory.get_stats()["turn_count"], 0)
        self.assertIn("P0420", memory.build_memory_context())

        memory.clear_session()
        self.assertEqual(memory.build_memory_context(), "")
        self.assertEqual(memory.snapshot()["working_memory"]["last_dtc_codes"], [])


if __name__ == "__main__":
    unittest.main()
