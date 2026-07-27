from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from threading import RLock
from typing import Any


class TenaciousPrefixCache:
    """
    Own every real model request and keep the next stable prefix prepared.

    Stable prefix lifecycle:

        build one canonical prefix snapshot
        -> prime that snapshot
        -> publish that exact snapshot as prepared
        -> verify the next request still wants the same prefix
        -> pass the prepared snapshot into the real request

    A real request invalidates the previously prepared state. The caller must
    schedule either the next completed-turn prefix or a recovery prefix before
    returning to the normal waiting state.
    """

    def __init__(
        self,
        *,
        prime_function: Callable[..., dict[str, Any]],
        request_function: Callable[..., Iterator[str]],
        prefix_builder_function: Callable[..., list[dict[str, str]]],
        prefix_fingerprint_function: Callable[[Any], str],
    ) -> None:
        self._prime_function = prime_function
        self._request_function = request_function
        self._prefix_builder_function = prefix_builder_function
        self._prefix_fingerprint_function = prefix_fingerprint_function
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="nancee-tpc",
        )
        self._lock = RLock()
        self._future: Future[dict[str, Any]] | None = None
        self._scheduled_prefix_messages: list[dict[str, str]] | None = None
        self._scheduled_prefix_sha256: str | None = None
        self._prepared_prefix_messages: list[dict[str, str]] | None = None
        self._prepared_prefix_sha256: str | None = None
        self._request_active = False
        self._closed = False

    @property
    def prepared_prefix_sha256(self) -> str | None:
        with self._lock:
            return self._prepared_prefix_sha256

    @property
    def is_priming(self) -> bool:
        with self._lock:
            return self._future is not None and not self._future.done()

    @property
    def request_active(self) -> bool:
        with self._lock:
            return self._request_active

    def _assert_open(self) -> None:
        if self._closed:
            raise RuntimeError("TenaciousPrefixCache is closed.")

    def _assert_idle(self) -> None:
        if self._request_active:
            raise RuntimeError("Cannot prime while a real model request is active.")

        if self._future is not None:
            raise RuntimeError(
                "A TPC prime is already pending. Wait before scheduling another."
            )

    def _build_prefix_snapshot(
        self,
        *,
        history,
        memory_context,
    ) -> tuple[list[dict[str, str]], str]:
        prefix_messages = deepcopy(
            self._prefix_builder_function(
                history=deepcopy(list(history or [])),
                memory_context=str(memory_context),
            )
        )
        prefix_sha256 = self._prefix_fingerprint_function(
            prefix_messages
        )

        return prefix_messages, prefix_sha256

    def _prime_and_verify(
        self,
        *,
        prefix_messages,
        expected_prefix_sha256,
    ):
        result = self._prime_function(
            prefix_messages=deepcopy(prefix_messages),
        )
        actual_prefix_sha256 = str(
            result.get(
                "prefix_sha256",
                "",
            )
        )

        if actual_prefix_sha256 != expected_prefix_sha256:
            raise RuntimeError(
                "TPC prime produced the wrong prefix fingerprint: "
                f"expected={expected_prefix_sha256} "
                f"actual={actual_prefix_sha256}"
            )

        return result

    def prime_now(
        self,
        *,
        history,
        memory_context="",
        reason="startup",
    ):
        """Synchronously prime and publish one canonical prefix snapshot."""
        history_snapshot = deepcopy(list(history or []))
        memory_context_snapshot = str(memory_context)
        prefix_messages, expected_prefix_sha256 = (
            self._build_prefix_snapshot(
                history=history_snapshot,
                memory_context=memory_context_snapshot,
            )
        )

        with self._lock:
            self._assert_open()
            self._assert_idle()

        print(
            "[TPC PRIME] mode=sync "
            f"reason={reason} "
            f"history_messages={len(history_snapshot)} "
            f"prefix_messages={len(prefix_messages)} "
            f"memory_context_chars={len(memory_context_snapshot.strip())} "
            f"expected_prefix_sha256={expected_prefix_sha256}",
            flush=True,
        )

        result = self._prime_and_verify(
            prefix_messages=prefix_messages,
            expected_prefix_sha256=expected_prefix_sha256,
        )

        with self._lock:
            self._prepared_prefix_messages = prefix_messages
            self._prepared_prefix_sha256 = expected_prefix_sha256

        return result

    def prime_async(
        self,
        *,
        history,
        memory_context="",
        reason="post_turn",
    ) -> None:
        """Build once, then prime an immutable completed-turn snapshot."""
        history_snapshot = deepcopy(list(history or []))
        memory_context_snapshot = str(memory_context)
        prefix_messages, expected_prefix_sha256 = (
            self._build_prefix_snapshot(
                history=history_snapshot,
                memory_context=memory_context_snapshot,
            )
        )

        with self._lock:
            self._assert_open()
            self._assert_idle()
            self._scheduled_prefix_messages = prefix_messages
            self._scheduled_prefix_sha256 = expected_prefix_sha256
            self._prepared_prefix_messages = None
            self._prepared_prefix_sha256 = None
            self._future = self._executor.submit(
                self._prime_and_verify,
                prefix_messages=prefix_messages,
                expected_prefix_sha256=expected_prefix_sha256,
            )

        print(
            "[TPC PRIME] mode=async "
            f"reason={reason} "
            f"history_messages={len(history_snapshot)} "
            f"prefix_messages={len(prefix_messages)} "
            f"memory_context_chars={len(memory_context_snapshot.strip())} "
            f"expected_prefix_sha256={expected_prefix_sha256}",
            flush=True,
        )

    def wait_until_ready(self):
        """Wait for priming, then publish its exact prefix snapshot."""
        with self._lock:
            future = self._future
            scheduled_prefix_messages = self._scheduled_prefix_messages
            scheduled_prefix_sha256 = self._scheduled_prefix_sha256

        if future is None:
            return None

        waited = not future.done()

        try:
            result = future.result()

            with self._lock:
                self._prepared_prefix_messages = scheduled_prefix_messages
                self._prepared_prefix_sha256 = scheduled_prefix_sha256

            print(
                "[TPC PRIME] ready=true "
                f"waited={str(waited).lower()} "
                f"prepared_prefix_messages="
                f"{len(scheduled_prefix_messages or [])} "
                f"prepared_prefix_sha256={scheduled_prefix_sha256}",
                flush=True,
            )

            return result
        finally:
            with self._lock:
                self._future = None
                self._scheduled_prefix_messages = None
                self._scheduled_prefix_sha256 = None

    def stream_response(
        self,
        *,
        history=None,
        memory_context="",
        require_exact_prefix=True,
        **request_kwargs,
    ):
        """Verify request state, then consume the prepared prefix snapshot."""
        self.wait_until_ready()

        history_snapshot = deepcopy(list(history or []))
        memory_context_snapshot = str(memory_context)
        actual_prefix_messages, actual_prefix_sha256 = (
            self._build_prefix_snapshot(
                history=history_snapshot,
                memory_context=memory_context_snapshot,
            )
        )

        with self._lock:
            self._assert_open()

            if self._request_active:
                raise RuntimeError("A real model request is already active.")

            prepared_prefix_messages = self._prepared_prefix_messages
            prepared_prefix_sha256 = self._prepared_prefix_sha256
            prefix_match = (
                prepared_prefix_messages is not None
                and prepared_prefix_sha256 == actual_prefix_sha256
            )

            if prefix_match:
                request_prefix_messages = deepcopy(
                    prepared_prefix_messages
                )
                prefix_source = "prepared_snapshot"
            else:
                request_prefix_messages = actual_prefix_messages
                prefix_source = "fresh_snapshot"

            print(
                "[TPC PREFIX] "
                f"match={str(prefix_match).lower()} "
                f"required={str(bool(require_exact_prefix)).lower()} "
                f"source={prefix_source} "
                f"prepared={prepared_prefix_sha256 or '<none>'} "
                f"actual={actual_prefix_sha256}",
                flush=True,
            )

            if require_exact_prefix and not prefix_match:
                raise RuntimeError(
                    "TPC exact-prefix contract failed before the real model request. "
                    f"prepared={prepared_prefix_sha256 or '<none>'} "
                    f"actual={actual_prefix_sha256}"
                )

            self._request_active = True
            self._prepared_prefix_messages = None
            self._prepared_prefix_sha256 = None

        try:
            yield from self._request_function(
                prefix_messages=request_prefix_messages,
                prefix_source=prefix_source,
                history=history_snapshot,
                memory_context=memory_context_snapshot,
                **request_kwargs,
            )
        finally:
            with self._lock:
                self._request_active = False

    def shutdown(self) -> None:
        """Finish pending preparation and stop the worker exactly once."""
        with self._lock:
            if self._closed:
                return

        try:
            self.wait_until_ready()
        finally:
            with self._lock:
                self._closed = True
                self._scheduled_prefix_messages = None
                self._scheduled_prefix_sha256 = None
                self._prepared_prefix_messages = None
                self._prepared_prefix_sha256 = None

            self._executor.shutdown(
                wait=True,
                cancel_futures=False,
            )
