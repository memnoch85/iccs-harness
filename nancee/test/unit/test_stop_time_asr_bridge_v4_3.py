from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHAT_PATH = ROOT / "sherpa/nancee_chat.py"
CONFIG_PATH = ROOT / "sherpa/config.py"
CHAT_SOURCE = CHAT_PATH.read_text(encoding="utf-8")
CONFIG_SOURCE = CONFIG_PATH.read_text(encoding="utf-8")
CHAT_TREE = ast.parse(CHAT_SOURCE)


class StopTimeAsrBridgeV43Tests(unittest.TestCase):
    def test_stop_time_bridge_configuration_exists(self):
        self.assertIn("NANCEE_LATENCY_BRIDGE_ASR_SECONDS", CONFIG_SOURCE)
        self.assertIn("NANCEE_LATENCY_BRIDGE_ASR_PHRASES", CONFIG_SOURCE)
        self.assertIn("LATENCY_BRIDGE_ASR_SECONDS", CHAT_SOURCE)
        self.assertIn("LATENCY_BRIDGE_ASR_PHRASES", CHAT_SOURCE)

    def test_spoken_input_carries_the_armed_bridge(self):
        self.assertIn("bridge: LatencyBridge | None = None", CHAT_SOURCE)
        self.assertIn("bridge_factory=None", CHAT_SOURCE)
        self.assertIn("bridge_factory(stop_requested_at)", CHAT_SOURCE)
        self.assertIn("turn_bridge,\n    )", CHAT_SOURCE)

    def test_bridge_is_armed_before_blocking_for_asr_result(self):
        factory_index = CHAT_SOURCE.index("bridge_factory(stop_requested_at)")
        stop_command_index = CHAT_SOURCE.index(
            'send_asr_command("STOP")',
            factory_index,
        )
        result_wait_index = CHAT_SOURCE.index(
            "message = read_asr_message()",
            stop_command_index,
        )
        self.assertLess(factory_index, stop_command_index)
        self.assertLess(stop_command_index, result_wait_index)

    def test_main_passes_factory_and_receives_bridge(self):
        self.assertIn("asr_bridge_factory = start_asr_latency_bridge", CHAT_SOURCE)
        self.assertIn("bridge_factory=asr_bridge_factory", CHAT_SOURCE)
        self.assertIn("bridge = spoken_input.bridge", CHAT_SOURCE)

    def test_only_one_turn_bridge_survives_handoff(self):
        self.assertIn("asr_bridge_fired = (", CHAT_SOURCE)
        self.assertIn("asr_fired=true route_bridge_armed=false", CHAT_SOURCE)
        self.assertIn("asr_fired=false route_bridge_armed=", CHAT_SOURCE)

    def test_real_audio_still_resolves_the_active_bridge(self):
        self.assertIn("first_audio_callback=bridge.resolve", CHAT_SOURCE)

    def test_asr_callback_only_enqueues_prebuilt_audio(self):
        function = next(
            node
            for node in ast.walk(CHAT_TREE)
            if isinstance(node, ast.FunctionDef)
            and node.name == "play_asr_latency_bridge"
        )
        calls = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
        ]
        self.assertTrue(
            any(
                isinstance(call.func, ast.Name)
                and call.func.id == "enqueue_audio"
                for call in calls
            )
        )
        self.assertFalse(
            any(
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "generate"
                for call in calls
            )
        )


if __name__ == "__main__":
    unittest.main()
