from __future__ import annotations

import threading
import time
import unittest
from copy import deepcopy

from iccs import ICCS


def fingerprint(prefix_messages):
    return "|".join(
        f"{message['role']}:{message['content']}"
        for message in prefix_messages
    )


class FakeBackend:
    def __init__(self):
        self.primes = []
        self.requests = []
        self.prime_release = None
        self.request_release = None

    def build_prefix(self, *, history, memory_context):
        messages = [{"role": "system", "content": "base"}]
        clean_memory_context = str(memory_context).strip()

        if clean_memory_context:
            messages.append(
                {
                    "role": "system",
                    "content": clean_memory_context,
                }
            )

        messages.extend(deepcopy(list(history or [])))
        return messages

    def fingerprint(self, prefix_messages):
        return fingerprint(prefix_messages)

    def prime(self, *, prefix_messages):
        self.primes.append(deepcopy(list(prefix_messages)))

        if self.prime_release is not None:
            self.prime_release.wait(timeout=1.0)

        return {
            "prefix_sha256": fingerprint(prefix_messages),
            "elapsed_seconds": 0.01,
        }

    def stream(self, **kwargs):
        self.requests.append(deepcopy(kwargs))

        if self.request_release is not None:
            self.request_release.wait(timeout=1.0)

        yield "answer"


class IccsSpineTests(unittest.TestCase):
    def test_startup_prime_then_exact_request(self):
        backend = FakeBackend()
        iccs = ICCS(backend=backend)

        try:
            result = iccs.prime_startup(history=[])
            tokens = list(
                iccs.respond(
                    history=[],
                    user_text="hello",
                )
            )

            self.assertEqual(["answer"], tokens)
            self.assertEqual(
                fingerprint(backend.primes[0]),
                result["prefix_sha256"],
            )
            self.assertEqual(
                "prepared_snapshot",
                backend.requests[0]["prefix_source"],
            )
        finally:
            iccs.close()

    def test_background_prime_freezes_history_before_worker_runs(self):
        backend = FakeBackend()
        release = threading.Event()
        backend.prime_release = release
        history = [{"role": "user", "content": "original"}]
        iccs = ICCS(backend=backend)

        try:
            iccs.prime_next(
                history=history,
                memory_context="stable",
            )
            history[0]["content"] = "mutated"
            history.append(
                {"role": "assistant", "content": "later"}
            )
            release.set()
            iccs.wait_for_prepared_prefix()

            self.assertEqual(
                [
                    {"role": "system", "content": "base"},
                    {"role": "system", "content": "stable"},
                    {"role": "user", "content": "original"},
                ],
                backend.primes[0],
            )
        finally:
            release.set()
            iccs.close()

    def test_gateway_waits_for_pending_prime(self):
        backend = FakeBackend()
        release = threading.Event()
        backend.prime_release = release
        history = [{"role": "user", "content": "stable"}]
        iccs = ICCS(backend=backend)

        try:
            iccs.prime_next(history=history)
            finished = threading.Event()

            def consume():
                list(
                    iccs.respond(
                        history=history,
                        user_text="hello",
                    )
                )
                finished.set()

            worker = threading.Thread(target=consume, daemon=True)
            worker.start()
            time.sleep(0.03)
            self.assertFalse(finished.is_set())
            self.assertEqual([], backend.requests)

            release.set()
            self.assertTrue(finished.wait(timeout=0.5))
            worker.join(timeout=0.5)
        finally:
            release.set()
            iccs.close()

    def test_required_prefix_mismatch_blocks_request(self):
        backend = FakeBackend()
        iccs = ICCS(backend=backend)

        try:
            iccs.prime_startup(history=[])

            with self.assertRaisesRegex(RuntimeError, "exact-prefix"):
                list(
                    iccs.respond(
                        history=[
                            {"role": "user", "content": "different"}
                        ],
                        user_text="hello",
                    )
                )

            self.assertEqual([], backend.requests)
        finally:
            iccs.close()

    def test_expected_dynamic_shape_uses_fresh_snapshot(self):
        backend = FakeBackend()
        iccs = ICCS(backend=backend)

        try:
            iccs.prime_startup(history=[])
            tokens = list(
                iccs.respond(
                    history=[],
                    memory_context="dynamic profile",
                    require_exact_prefix=False,
                    user_text="hello",
                )
            )

            self.assertEqual(["answer"], tokens)
            self.assertEqual(
                "fresh_snapshot",
                backend.requests[0]["prefix_source"],
            )
            self.assertEqual(
                {"role": "system", "content": "dynamic profile"},
                backend.requests[0]["prefix_messages"][1],
            )
        finally:
            iccs.close()

    def test_prime_result_must_match_scheduled_fingerprint(self):
        class BadBackend(FakeBackend):
            def prime(self, *, prefix_messages):
                return {"prefix_sha256": "wrong"}

        iccs = ICCS(backend=BadBackend())

        try:
            with self.assertRaisesRegex(
                RuntimeError,
                "wrong prefix fingerprint",
            ):
                iccs.prime_startup(history=[])
        finally:
            iccs.close()

    def test_request_failure_releases_active_state(self):
        class FailingBackend(FakeBackend):
            def stream(self, **kwargs):
                self.requests.append(deepcopy(kwargs))
                raise RuntimeError("request failed")
                yield "unreachable"

        backend = FailingBackend()
        iccs = ICCS(backend=backend)

        try:
            iccs.prime_startup(history=[])

            with self.assertRaisesRegex(RuntimeError, "request failed"):
                list(iccs.respond(history=[], user_text="hello"))

            self.assertFalse(iccs.request_active)
            iccs.prime_next(history=[], reason="request_recovery")
            iccs.wait_for_prepared_prefix()
            self.assertIsNotNone(iccs.prepared_prefix_sha256)
        finally:
            iccs.close()

    def test_completion_state_receives_iccs_gateway_metrics(self):
        backend = FakeBackend()
        iccs = ICCS(backend=backend)
        completion_state = {}

        try:
            iccs.prime_startup(history=[])
            list(
                iccs.respond(
                    history=[],
                    user_text="hello",
                    completion_state=completion_state,
                )
            )

            self.assertEqual(
                "prepared_snapshot",
                completion_state["iccs_prefix_source"],
            )
            self.assertTrue(completion_state["iccs_prefix_match"])
            self.assertIn("iccs_wait_seconds", completion_state)
            self.assertIn("iccs_prefix_sha256", completion_state)
        finally:
            iccs.close()

    def test_close_is_idempotent(self):
        iccs = ICCS(backend=FakeBackend())
        iccs.close()
        iccs.close()


if __name__ == "__main__":
    unittest.main()
