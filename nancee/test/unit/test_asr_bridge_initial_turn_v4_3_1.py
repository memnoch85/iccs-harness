from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHAT = (ROOT / "sherpa/nancee_chat.py").read_text(encoding="utf-8")
CONFIG = (ROOT / "sherpa/config.py").read_text(encoding="utf-8")


class AsrBridgeInitialTurnV431Tests(unittest.TestCase):
    def test_initial_turn_gate_is_configurable_and_enabled_by_default(self):
        self.assertIn(
            "NANCEE_LATENCY_BRIDGE_ASR_SKIP_INITIAL_TURN",
            CONFIG,
        )
        self.assertIn('"true"', CONFIG)

    def test_initial_turn_is_detected_before_recording_starts(self):
        detection = CHAT.index(
            "is_initial_turn = not recent_prompt_memory.get_messages()"
        )
        input_call = CHAT.index(
            "spoken_input = get_spoken_user_input(",
            detection,
        )
        self.assertLess(detection, input_call)

    def test_initial_turn_disables_only_the_asr_bridge_factory(self):
        self.assertIn("asr_bridge_factory = start_asr_latency_bridge", CHAT)
        self.assertIn("asr_bridge_factory = None", CHAT)
        self.assertIn("bridge_factory=asr_bridge_factory", CHAT)
        self.assertIn("reason=initial_turn", CHAT)

    def test_existing_route_bridge_remains_present(self):
        self.assertIn('response_policy.name == "greeting"', CHAT)
        self.assertIn("greeting_bridge_audio_cycle", CHAT)
        self.assertIn("LATENCY_BRIDGE_GREETING_SECONDS", CHAT)


if __name__ == "__main__":
    unittest.main()
