import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHAT = (ROOT / "sherpa" / "nancee_chat.py").read_text(
    encoding="utf-8"
)
CONFIG = (ROOT / "sherpa" / "config.py").read_text(
    encoding="utf-8"
)


class RouteOnlyLatencyBridgeV44Tests(unittest.TestCase):
    def test_asr_latency_configuration_is_removed(self):
        for token in (
            "LATENCY_BRIDGE_ASR_SECONDS",
            "LATENCY_BRIDGE_ASR_PHRASES",
            "LATENCY_BRIDGE_ASR_SKIP_INITIAL_TURN",
        ):
            self.assertNotIn(token, CONFIG)
            self.assertNotIn(token, CHAT)

    def test_spoken_input_only_carries_text_and_stop_time(self):
        block = CHAT.split(
            "class SpokenUserInput:",
            1,
        )[1].split(
            "def retrieve_session_context",
            1,
        )[0]

        self.assertIn("text: str", block)
        self.assertIn("stopped_at: float | None", block)
        self.assertNotIn("bridge:", block)

    def test_recording_stop_clock_and_asr_telemetry_remain(self):
        self.assertIn(
            "stop_requested_at = time.perf_counter()",
            CHAT,
        )
        self.assertIn(
            "stop_to_result_seconds = "
            "time.perf_counter() - stop_requested_at",
            CHAT,
        )
        self.assertIn(
            "started_at=recording_stopped_at",
            CHAT,
        )

    def test_only_route_latency_bridge_remains(self):
        self.assertNotIn("start_asr_latency_bridge", CHAT)
        self.assertNotIn("bridge_factory", CHAT)
        self.assertNotIn("LATENCY BRIDGE HANDOFF", CHAT)
        self.assertIn("bridge = LatencyBridge(", CHAT)
        self.assertIn("bridge.start()", CHAT)

    def test_faster_whisper_runtime_configuration_remains(self):
        for token in (
            "ASR_BACKEND",
            "ASR_MODEL",
            "ASR_COMPUTE_TYPE",
            "ASR_THREADS",
            "ASR_BEAM_SIZE",
        ):
            self.assertIn(token, CONFIG)


if __name__ == "__main__":
    unittest.main()
