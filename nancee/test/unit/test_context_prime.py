import threading
import time
import unittest

from context_prime import ContextPrimeCoordinator


class TestContextPrimeCoordinator(unittest.TestCase):
    def test_no_prime_returns_without_bridge(self):
        coordinator = ContextPrimeCoordinator(
            lambda **kwargs: {},
        )

        bridge_calls = []

        bridge_used = coordinator.wait_if_needed(
            grace_seconds=0,
            bridge_callback=lambda: bridge_calls.append(True),
        )

        self.assertFalse(bridge_used)
        self.assertEqual(bridge_calls, [])

        coordinator.shutdown()

    def test_completed_prime_does_not_use_bridge(self):
        coordinator = ContextPrimeCoordinator(
            lambda **kwargs: {
                "elapsed_seconds": 0.0,
            },
        )

        bridge_calls = []

        coordinator.start(
            history=[],
            memory_context="",
        )

        time.sleep(0.01)

        bridge_used = coordinator.wait_if_needed(
            grace_seconds=0.1,
            bridge_callback=lambda: bridge_calls.append(True),
        )

        self.assertFalse(bridge_used)
        self.assertEqual(bridge_calls, [])

        coordinator.shutdown()

    def test_running_prime_uses_bridge_and_waits(self):
        release_prime = threading.Event()
        prime_finished = threading.Event()
        bridge_calls = []

        def fake_prime(**kwargs):
            release_prime.wait(timeout=1.0)
            prime_finished.set()

            return {
                "elapsed_seconds": 0.1,
            }

        coordinator = ContextPrimeCoordinator(
            fake_prime,
        )

        coordinator.start(
            history=[
                {
                    "role": "user",
                    "content": "hello",
                }
            ],
            memory_context="test memory",
        )

        def bridge():
            bridge_calls.append(True)
            release_prime.set()

        bridge_used = coordinator.wait_if_needed(
            grace_seconds=0,
            bridge_callback=bridge,
        )

        self.assertTrue(bridge_used)
        self.assertEqual(bridge_calls, [True])
        self.assertTrue(prime_finished.is_set())
        self.assertFalse(coordinator.is_running())

        coordinator.shutdown()

    def test_prime_error_clears_running_state(self):
        def failing_prime(**kwargs):
            raise RuntimeError("simulated failure")

        coordinator = ContextPrimeCoordinator(
            failing_prime,
        )

        coordinator.start(
            history=[],
            memory_context="",
        )

        with self.assertRaises(RuntimeError):
            coordinator.wait_if_needed(
                grace_seconds=0.1,
            )

        self.assertFalse(coordinator.is_running())

        coordinator.shutdown()


if __name__ == "__main__":
    unittest.main()
