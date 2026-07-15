import threading
import time
import unittest

from sherpa.latency_bridge import LatencyBridge


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


if __name__ == "__main__":
    unittest.main()
