from __future__ import annotations

import threading
import time
import unittest

from tenacious_prefix_cache import TenaciousPrefixCache


def fingerprint(*, history, memory_context):
    parts = [message["content"] for message in history]
    return "|".join(parts + [str(memory_context)])


class TenaciousPrefixCacheV2Tests(unittest.TestCase):
    def make_tpc(self, *, prime_function=None, request_function=None):
        if prime_function is None:
            def prime_function(*, history, memory_context):
                return {
                    "prefix_sha256": fingerprint(
                        history=history,
                        memory_context=memory_context,
                    )
                }

        if request_function is None:
            def request_function(**_kwargs):
                yield "ok"

        return TenaciousPrefixCache(
            prime_function=prime_function,
            request_function=request_function,
            prefix_fingerprint_function=fingerprint,
        )

    def test_synchronous_startup_prime_records_prepared_prefix(self):
        tpc = self.make_tpc()

        try:
            result = tpc.prime_now(
                history=[],
                memory_context="",
            )

            self.assertEqual("", result["prefix_sha256"])
            self.assertEqual("", tpc.prepared_prefix_sha256)
        finally:
            tpc.shutdown()

    def test_background_prime_uses_frozen_history_snapshot(self):
        started = threading.Event()
        release = threading.Event()
        captured = {}

        def prime_function(*, history, memory_context):
            started.set()
            release.wait(timeout=1.0)
            captured["history"] = history
            captured["memory_context"] = memory_context
            return {
                "prefix_sha256": fingerprint(
                    history=history,
                    memory_context=memory_context,
                )
            }

        tpc = self.make_tpc(prime_function=prime_function)
        history = [{"role": "user", "content": "original"}]

        try:
            tpc.prime_async(history=history, memory_context="stable")
            self.assertTrue(started.wait(timeout=0.25))

            history[0]["content"] = "mutated"
            history.append({"role": "assistant", "content": "later"})

            release.set()
            tpc.wait_until_ready()

            self.assertEqual(
                [{"role": "user", "content": "original"}],
                captured["history"],
            )
            self.assertEqual("stable", captured["memory_context"])
            self.assertEqual("original|stable", tpc.prepared_prefix_sha256)
        finally:
            release.set()
            tpc.shutdown()

    def test_gateway_waits_for_pending_prime_before_request(self):
        release = threading.Event()
        request_started = threading.Event()

        def prime_function(*, history, memory_context):
            release.wait(timeout=1.0)
            return {
                "prefix_sha256": fingerprint(
                    history=history,
                    memory_context=memory_context,
                )
            }

        def request_function(**_kwargs):
            request_started.set()
            yield "answer"

        tpc = self.make_tpc(
            prime_function=prime_function,
            request_function=request_function,
        )
        history = [{"role": "user", "content": "stable"}]

        try:
            tpc.prime_async(history=history)
            finished = threading.Event()

            def consume():
                list(tpc.stream_response(history=history, user_text="hello"))
                finished.set()

            worker = threading.Thread(target=consume, daemon=True)
            worker.start()

            time.sleep(0.03)
            self.assertFalse(request_started.is_set())
            self.assertFalse(finished.is_set())

            release.set()
            self.assertTrue(finished.wait(timeout=0.25))
            self.assertTrue(request_started.is_set())
            worker.join(timeout=0.25)
        finally:
            release.set()
            tpc.shutdown()

    def test_required_prefix_mismatch_blocks_raw_request(self):
        request_calls = []

        def request_function(**_kwargs):
            request_calls.append("called")
            yield "answer"

        tpc = self.make_tpc(request_function=request_function)

        try:
            tpc.prime_now(history=[], memory_context="")

            with self.assertRaisesRegex(RuntimeError, "exact-prefix contract"):
                list(
                    tpc.stream_response(
                        history=[{"role": "user", "content": "different"}],
                        memory_context="",
                        require_exact_prefix=True,
                        user_text="hello",
                    )
                )

            self.assertEqual([], request_calls)
        finally:
            tpc.shutdown()

    def test_expected_dynamic_branch_can_proceed_without_exact_match(self):
        request_calls = []

        def request_function(**kwargs):
            request_calls.append(kwargs)
            yield "answer"

        tpc = self.make_tpc(request_function=request_function)

        try:
            tpc.prime_now(history=[], memory_context="")
            tokens = list(
                tpc.stream_response(
                    history=[],
                    memory_context="dynamic profile",
                    require_exact_prefix=False,
                    user_text="hello",
                )
            )

            self.assertEqual(["answer"], tokens)
            self.assertEqual(1, len(request_calls))
        finally:
            tpc.shutdown()

    def test_real_request_invalidates_prepared_prefix(self):
        tpc = self.make_tpc()

        try:
            tpc.prime_now(history=[])
            self.assertEqual("", tpc.prepared_prefix_sha256)

            self.assertEqual(
                ["ok"],
                list(tpc.stream_response(history=[], user_text="hello")),
            )
            self.assertIsNone(tpc.prepared_prefix_sha256)
        finally:
            tpc.shutdown()

    def test_prime_is_rejected_while_real_request_is_active(self):
        request_started = threading.Event()
        release = threading.Event()

        def request_function(**_kwargs):
            request_started.set()
            release.wait(timeout=1.0)
            yield "answer"

        tpc = self.make_tpc(request_function=request_function)

        try:
            tpc.prime_now(history=[])

            worker = threading.Thread(
                target=lambda: list(tpc.stream_response(history=[], user_text="hello")),
                daemon=True,
            )
            worker.start()
            self.assertTrue(request_started.wait(timeout=0.25))

            with self.assertRaisesRegex(RuntimeError, "real model request is active"):
                tpc.prime_async(history=[])

            release.set()
            worker.join(timeout=0.25)
        finally:
            release.set()
            tpc.shutdown()

    def test_prime_result_must_match_expected_fingerprint(self):
        def bad_prime(**_kwargs):
            return {"prefix_sha256": "wrong"}

        tpc = self.make_tpc(prime_function=bad_prime)

        try:
            with self.assertRaisesRegex(RuntimeError, "wrong prefix fingerprint"):
                tpc.prime_now(history=[])
        finally:
            tpc.shutdown()

    def test_request_failure_releases_active_state_for_recovery_prime(self):
        def request_function(**_kwargs):
            raise RuntimeError("request failed")
            yield "unreachable"

        tpc = self.make_tpc(request_function=request_function)

        try:
            tpc.prime_now(history=[])

            with self.assertRaisesRegex(RuntimeError, "request failed"):
                list(tpc.stream_response(history=[], user_text="hello"))

            self.assertFalse(tpc.request_active)
            tpc.prime_async(history=[], reason="request_recovery")
            tpc.wait_until_ready()
            self.assertEqual("", tpc.prepared_prefix_sha256)
        finally:
            tpc.shutdown()

    def test_shutdown_is_idempotent(self):
        tpc = self.make_tpc()
        tpc.shutdown()
        tpc.shutdown()


if __name__ == "__main__":
    unittest.main()
