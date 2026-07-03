import unittest

from short_term_memory import ShortTermMemory


class TestShortTermMemory(unittest.TestCase):
    def test_generic_fact_limit_pops_oldest(self):
        memory = ShortTermMemory(max_turns=None)

        for index in range(30):
            memory.add_generic_fact(f"Fact number {index}")

        snapshot = memory.snapshot()
        facts = snapshot["working_state"]["generic_facts"]

        self.assertEqual(len(facts), 24)
        self.assertEqual(facts[0]["fact"], "Fact number 6")
        self.assertEqual(facts[-1]["fact"], "Fact number 29")

    def test_related_memory_context_returns_match(self):
        memory = ShortTermMemory(max_turns=None)
        memory.add_generic_fact(
            "Anders's mechanic is named Dave.",
            source_text="Remember that my mechanic's name is Dave.",
        )

        context = memory.build_related_memory_context("What is my mechanic's name?")

        self.assertIn("Dave", context)
        self.assertIn("RELATED SESSION MEMORY", context)

    def test_stats_and_snapshot_exclude_removed_consolidation_state(self):
        memory = ShortTermMemory()
        memory.add_turn("hello", "hi")

        stats = memory.get_stats()
        snapshot = memory.snapshot()

        self.assertNotIn("summary_characters", stats)
        self.assertNotIn("consolidation_count", stats)
        self.assertNotIn("session_summary", snapshot)
        self.assertNotIn("consolidation_count", snapshot)

    def test_extract_oldest_turns_removes_only_archived_turns(self):
        memory = ShortTermMemory()
        memory.add_turn("user 1", "assistant 1")
        memory.add_turn("user 2", "assistant 2")
        memory.add_turn("user 3", "assistant 3")
        memory.add_turn("user 4", "assistant 4")
        extracted = memory.extract_oldest_turns(
            keep_recent_turns=2,
        )

        self.assertEqual(
            extracted,
            [
                {
                    "user": "user 1",
                    "assistant": "assistant 1",
                },
                {
                    "user": "user 2",
                    "assistant": "assistant 2",
                },
            ],
        )

        self.assertEqual(
            memory.get_turns_snapshot(),
            [
                {
                    "user": "user 3",
                    "assistant": "assistant 3",
                },
                {
                    "user": "user 4",
                    "assistant": "assistant 4",
                },
            ],
        )

    def test_clear_session_removes_turns_and_working_state(self):
        memory = ShortTermMemory(max_turns=3)

        memory.add_turn(
            "What code does the Jeep have?",
            "The stored code is P0420.",
        )
        memory.set_session_fact(
            "vehicle",
            "2016 Jeep Patriot",
        )
        memory.set_last_dtc_codes(["P0420"])

        memory.clear_session()

        snapshot = memory.snapshot()

        self.assertEqual(
            memory.get_turns_snapshot(),
            [],
        )
        self.assertEqual(
            snapshot["working_memory"]["session_facts"],
            {},
        )
        self.assertEqual(
            snapshot["working_memory"]["last_dtc_codes"],
            [],
        )
        self.assertEqual(
            snapshot["max_turns"],
            3,
        )

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

        with self.assertRaises(ValueError):
            ShortTermMemory(max_turns=-1)

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
