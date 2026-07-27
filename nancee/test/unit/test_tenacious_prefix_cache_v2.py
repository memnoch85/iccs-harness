from __future__ import annotations

import threading
import time
import unittest
from copy import deepcopy

from tenacious_prefix_cache import TenaciousPrefixCache


def build_prefix(*, history=None, memory_context=""):
    messages = [
        {
            "role": "system",
            "content": "base",
        }
    ]

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


def fingerprint(prefix_messages):
    return "|".join(
        f"{message['role']}:{message['content']}"
        for message in prefix_messages
    )


class TenaciousPrefixCacheV2Tests(unittest.TestCase):
    def make_tpc(
        self,
        *,
        prime_function=None,
        request_function=None,
        prefix_builder_function=build_prefix,
    ):
        if prime_function is None:
            def prime_function(*, prefix_messages):
                return {
                    "prefix_sha256": fingerprint(prefix_messages)
                }

        if request_function is None:
            def request_function(**_kwargs):
                yield "ok"

        return TenaciousPrefixCache(
            prime_function=prime_function,
            request_function=request_function,
            prefix_builder_function=prefix_builder_function,
            prefix_fingerprint_function=fingerprint,
        )

    def test_synchronous_startup_prime_records_prepared_prefix(self):
        tpc = self.make_tpc()
        expected_prefix = build_prefix(history=[], memory_context="")
        expected_sha256 = fingerprint(expected_prefix)

        try:
            result = tpc.prime_now(
                history=[],
                memory_context="",
            )

            self.assertEqual(expected_sha256, result["prefix_sha256"])
            self.assertEqual(expected_sha256, tpc.prepared_prefix_sha256)
            self.assertEqual(expected_prefix, tpc._prepared_prefix_messages)
        finally:
            tpc.shutdown()

    def test_background_prime_uses_frozen_history_snapshot(self):
        started = threading.Event()
        release = threading.Event()
        captured = {}

        def prime_function(*, prefix_messages):
            started.set()
            release.wait(timeout=1.0)
            captured["prefix_messages"] = prefix_messages
            return {
                "prefix_sha256": fingerprint(prefix_messages)
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

            expected_prefix = build_prefix(
                history=[{"role": "user", "content": "original"}],
                memory_context="stable",
            )

            self.assertEqual(
                expected_prefix,
                captured["prefix_messages"],
            )
            self.assertEqual(
                fingerprint(expected_prefix),
                tpc.prepared_prefix_sha256,
            )
            self.assertEqual(
                expected_prefix,
                tpc._prepared_prefix_messages,
            )
        finally:
            release.set()
            tpc.shutdown()

    def test_gateway_waits_for_pending_prime_before_request(self):
        release = threading.Event()
        request_started = threading.Event()
        request_calls = []

        def prime_function(*, prefix_messages):
            release.wait(timeout=1.0)
            return {
                "prefix_sha256": fingerprint(prefix_messages)
            }

        def request_function(**kwargs):
            request_calls.append(kwargs)
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

            self.assertEqual(
                "prepared_snapshot",
                request_calls[0]["prefix_source"],
            )
            self.assertEqual(
                build_prefix(history=history),
                request_calls[0]["prefix_messages"],
            )
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
            self.assertEqual(
                "fresh_snapshot",
                request_calls[0]["prefix_source"],
            )
            self.assertEqual(
                build_prefix(
                    history=[],
                    memory_context="dynamic profile",
                ),
                request_calls[0]["prefix_messages"],
            )
        finally:
            tpc.shutdown()

    def test_exact_match_consumes_prepared_snapshot(self):
        primed_prefixes = []
        request_calls = []

        def prime_function(*, prefix_messages):
            primed_prefixes.append(prefix_messages)
            return {
                "prefix_sha256": fingerprint(prefix_messages)
            }

        def request_function(**kwargs):
            request_calls.append(kwargs)
            yield "answer"

        history = [
            {"role": "user", "content": "Previous question."},
            {"role": "assistant", "content": "Previous answer."},
        ]
        tpc = self.make_tpc(
            prime_function=prime_function,
            request_function=request_function,
        )

        try:
            tpc.prime_now(
                history=history,
                memory_context="ACTIVE SPEAKER: Daniel.",
            )

            self.assertEqual(
                ["answer"],
                list(
                    tpc.stream_response(
                        history=history,
                        memory_context="ACTIVE SPEAKER: Daniel.",
                        user_text="hello",
                    )
                ),
            )

            self.assertEqual(
                "prepared_snapshot",
                request_calls[0]["prefix_source"],
            )
            self.assertEqual(
                primed_prefixes[0],
                request_calls[0]["prefix_messages"],
            )
            self.assertIsNot(
                primed_prefixes[0],
                request_calls[0]["prefix_messages"],
            )
        finally:
            tpc.shutdown()

    def test_real_request_invalidates_prepared_prefix(self):
        tpc = self.make_tpc()
        expected_sha256 = fingerprint(build_prefix(history=[]))

        try:
            tpc.prime_now(history=[])
            self.assertEqual(expected_sha256, tpc.prepared_prefix_sha256)

            self.assertEqual(
                ["ok"],
                list(tpc.stream_response(history=[], user_text="hello")),
            )
            self.assertIsNone(tpc.prepared_prefix_sha256)
            self.assertIsNone(tpc._prepared_prefix_messages)
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
                target=lambda: list(
                    tpc.stream_response(
                        history=[],
                        user_text="hello",
                    )
                ),
                daemon=True,
            )
            worker.start()
            self.assertTrue(request_started.wait(timeout=0.25))

            with self.assertRaisesRegex(
                RuntimeError,
                "real model request is active",
            ):
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
            with self.assertRaisesRegex(
                RuntimeError,
                "wrong prefix fingerprint",
            ):
                tpc.prime_now(history=[])
        finally:
            tpc.shutdown()

    def test_request_failure_releases_active_state_for_recovery_prime(self):
        def request_function(**_kwargs):
            raise RuntimeError("request failed")
            yield "unreachable"

        tpc = self.make_tpc(request_function=request_function)
        expected_sha256 = fingerprint(build_prefix(history=[]))

        try:
            tpc.prime_now(history=[])

            with self.assertRaisesRegex(RuntimeError, "request failed"):
                list(tpc.stream_response(history=[], user_text="hello"))

            self.assertFalse(tpc.request_active)
            tpc.prime_async(history=[], reason="request_recovery")
            tpc.wait_until_ready()
            self.assertEqual(expected_sha256, tpc.prepared_prefix_sha256)
        finally:
            tpc.shutdown()

    def test_shutdown_is_idempotent(self):
        tpc = self.make_tpc()
        tpc.shutdown()
        tpc.shutdown()


if __name__ == "__main__":
    unittest.main()
