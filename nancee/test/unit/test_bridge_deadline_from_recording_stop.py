from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "sherpa/nancee_chat.py").read_text(encoding="utf-8")


class BridgeDeadlineFromRecordingStopTests(unittest.TestCase):
    def test_spoken_input_carries_recording_stop_timestamp(self):
        self.assertIn("class SpokenUserInput:", SOURCE)
        self.assertIn("stopped_at: float | None", SOURCE)
        self.assertIn("recording_stopped_at = spoken_input.stopped_at", SOURCE)

    def test_bridge_uses_recording_stop_deadline(self):
        self.assertIn("calculate_remaining_bridge_delay(", SOURCE)
        self.assertIn("started_at=recording_stopped_at", SOURCE)
        self.assertIn("[LATENCY BRIDGE DEADLINE]", SOURCE)
        self.assertIn("elapsed_since_stop=", SOURCE)
        self.assertIn("remaining=", SOURCE)


if __name__ == "__main__":
    unittest.main()
