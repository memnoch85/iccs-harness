import threading
import time
import unittest

from sherpa.latency_bridge import (
    LatencyBridge,
    calculate_remaining_bridge_delay,
)


class LatencyBridgeTests(unittest.TestCase):
    def test_resolve_before_deadline_prevents_fire(self):
        fired = threading.Event()
        bridge = LatencyBridge(delay_seconds=0.05, on_fire=fired.set)
        bridge.start()
        time.sleep(0.01)
        self.assertFalse(bridge.resolve())
        time.sleep(0.07)
        self.assertFalse(fired.is_set())
        self.assertFalse(bridge.fired)

    def test_deadline_fires_once(self):
        calls = []
        fired = threading.Event()

        def callback():
            calls.append("fired")
            fired.set()

        bridge = LatencyBridge(delay_seconds=0.02, on_fire=callback)
        bridge.start()
        self.assertTrue(fired.wait(timeout=0.25))
        self.assertTrue(bridge.resolve())
        time.sleep(0.03)
        self.assertEqual(calls, ["fired"])
        self.assertTrue(bridge.fired)

    def test_disabled_bridge_never_fires(self):
        fired = threading.Event()
        bridge = LatencyBridge(
            delay_seconds=0.01,
            on_fire=fired.set,
            enabled=False,
        )
        bridge.start()
        time.sleep(0.03)
        self.assertFalse(fired.is_set())


class LatencyBridgeDeadlineTests(unittest.TestCase):
    def test_asr_elapsed_time_is_subtracted_from_target(self):
        remaining, elapsed = calculate_remaining_bridge_delay(
            6.3,
            started_at=10.0,
            now=12.4,
        )

        self.assertAlmostEqual(elapsed, 2.4)
        self.assertAlmostEqual(remaining, 3.9)

    def test_elapsed_deadline_returns_tiny_positive_delay(self):
        remaining, elapsed = calculate_remaining_bridge_delay(
            4.5,
            started_at=10.0,
            now=16.0,
        )

        self.assertAlmostEqual(elapsed, 6.0)
        self.assertGreater(remaining, 0.0)
        self.assertLess(remaining, 0.01)

    def test_missing_start_time_preserves_original_delay(self):
        remaining, elapsed = calculate_remaining_bridge_delay(
            5.2,
            started_at=None,
            now=100.0,
        )

        self.assertEqual(remaining, 5.2)
        self.assertEqual(elapsed, 0.0)


if __name__ == "__main__":
    unittest.main()
