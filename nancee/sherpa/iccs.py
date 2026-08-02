from __future__ import annotations

import time
from collections.abc import Iterator, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Any, Protocol

Message = dict[str, str]
PrimeResult = Mapping[str, Any] | Any


class IccsBackend(Protocol):
    """Backend operations required by the ICCS lifecycle controller."""

    def build_prefix(
        self,
        *,
        history: Sequence[Message],
        memory_context: str,
    ) -> list[Message]: ...

    def fingerprint(
        self,
        prefix_messages: Sequence[Message],
    ) -> str: ...

    def prime(
        self,
        *,
        prefix_messages: Sequence[Message],
    ) -> PrimeResult: ...

    def stream(
        self,
        *,
        prefix_messages: Sequence[Message],
        prefix_source: str,
        history: Sequence[Message],
        memory_context: str,
        **request_kwargs: Any,
    ) -> Iterator[str]: ...


@dataclass(frozen=True)
class PrefixSnapshot:
    """One frozen stable-prefix shape prepared for the next request."""

    _messages: tuple[Message, ...]
    sha256: str
    reason: str
    history_messages: int
    memory_context_chars: int

    @classmethod
    def freeze(
        cls,
        *,
        prefix_messages: Sequence[Message],
        sha256: str,
        reason: str,
        history_messages: int,
        memory_context_chars: int,
    ) -> PrefixSnapshot:
        return cls(
            _messages=tuple(deepcopy(list(prefix_messages))),
            sha256=str(sha256),
            reason=str(reason),
            history_messages=int(history_messages),
            memory_context_chars=int(memory_context_chars),
        )

    @property
    def prefix_messages(self) -> int:
        return len(self._messages)

    def as_messages(self) -> list[Message]:
        """Return a defensive copy so no caller can mutate prepared state."""
        return deepcopy(list(self._messages))


@dataclass(frozen=True)
class PrimeWait:
    """Observable result of waiting for a background prime."""

    result: PrimeResult | None
    wait_seconds: float
    waited: bool


class ICCS:
    """Iterative Cache Control and Shaping.

    ICCS owns the complete stable-prefix lifecycle:

        shape -> freeze -> prime -> publish -> wait -> verify -> consume

    The application supplies a backend for prompt construction, fingerprinting,
    priming, and real response streaming. ICCS owns concurrency, prepared-state
    identity, exact-prefix enforcement, dynamic fallback, and shutdown.
    """

    def __init__(self, *, backend: IccsBackend) -> None:
        self._backend = backend
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="iccs",
        )
        self._lock = RLock()
        self._future: Future[PrimeResult] | None = None
        self._scheduled_snapshot: PrefixSnapshot | None = None
        self._prepared_snapshot: PrefixSnapshot | None = None
        self._request_active = False
        self._closed = False

    @property
    def prepared_prefix_sha256(self) -> str | None:
        with self._lock:
            if self._prepared_snapshot is None:
                return None
            return self._prepared_snapshot.sha256

    @property
    def is_priming(self) -> bool:
        with self._lock:
            return self._future is not None and not self._future.done()

    @property
    def request_active(self) -> bool:
        with self._lock:
            return self._request_active

    def shape_prefix(
        self,
        *,
        history: Sequence[Message] | None = None,
        memory_context: str = "",
        reason: str,
    ) -> PrefixSnapshot:
        """Build and freeze the exact stable prefix expected next."""
        history_snapshot = deepcopy(list(history or []))
        memory_context_snapshot = str(memory_context)
        prefix_messages = deepcopy(
            self._backend.build_prefix(
                history=history_snapshot,
                memory_context=memory_context_snapshot,
            )
        )
        prefix_sha256 = str(
            self._backend.fingerprint(prefix_messages)
        )

        if not prefix_sha256:
            raise RuntimeError("ICCS backend returned an empty prefix fingerprint.")

        return PrefixSnapshot.freeze(
            prefix_messages=prefix_messages,
            sha256=prefix_sha256,
            reason=reason,
            history_messages=len(history_snapshot),
            memory_context_chars=len(memory_context_snapshot.strip()),
        )

    def _prime_and_verify(
        self,
        snapshot: PrefixSnapshot,
    ) -> PrimeResult:
        result = self._backend.prime(
            prefix_messages=snapshot.as_messages(),
        )
        actual_prefix_sha256 = _prime_result_prefix_sha256(result)

        if actual_prefix_sha256 != snapshot.sha256:
            raise RuntimeError(
                "ICCS prime produced the wrong prefix fingerprint: "
                f"expected={snapshot.sha256} "
                f"actual={actual_prefix_sha256 or '<missing>'}"
            )

        return result

    def prime_startup(
        self,
        *,
        history: Sequence[Message] | None = None,
        memory_context: str = "",
        reason: str = "startup",
    ) -> PrimeResult:
        """Synchronously prepare and publish the startup prefix."""
        snapshot = self.shape_prefix(
            history=history,
            memory_context=memory_context,
            reason=reason,
        )

        with self._lock:
            self._assert_open()
            self._assert_idle()

        self._log_prime(mode="sync", snapshot=snapshot)
        result = self._prime_and_verify(snapshot)

        with self._lock:
            self._prepared_snapshot = snapshot

        return result

    def prime_next(
        self,
        *,
        history: Sequence[Message] | None = None,
        memory_context: str = "",
        reason: str = "completed_turn",
    ) -> None:
        """Prepare the next exact stable prefix on the background worker."""
        snapshot = self.shape_prefix(
            history=history,
            memory_context=memory_context,
            reason=reason,
        )

        with self._lock:
            self._assert_open()
            self._assert_idle()
            self._scheduled_snapshot = snapshot
            self._prepared_snapshot = None
            self._future = self._executor.submit(
                self._prime_and_verify,
                snapshot,
            )

        self._log_prime(mode="async", snapshot=snapshot)

    def wait_for_prepared_prefix(self) -> PrimeWait:
        """Publish a completed background prime and report foreground wait."""
        with self._lock:
            future = self._future
            scheduled_snapshot = self._scheduled_snapshot

        if future is None:
            return PrimeWait(
                result=None,
                wait_seconds=0.0,
                waited=False,
            )

        waited = not future.done()
        started = time.perf_counter()

        try:
            result = future.result()
            wait_seconds = time.perf_counter() - started

            if scheduled_snapshot is None:
                raise RuntimeError(
                    "ICCS background prime completed without a scheduled snapshot."
                )

            with self._lock:
                self._prepared_snapshot = scheduled_snapshot

            print(
                "[ICCS PRIME] ready=true "
                f"waited={str(waited).lower()} "
                f"wait_seconds={wait_seconds:.6f} "
                f"prefix_messages={scheduled_snapshot.prefix_messages} "
                f"sha256={scheduled_snapshot.sha256}",
                flush=True,
            )

            return PrimeWait(
                result=result,
                wait_seconds=wait_seconds,
                waited=waited,
            )
        finally:
            with self._lock:
                self._future = None
                self._scheduled_snapshot = None

    def respond(
        self,
        *,
        history: Sequence[Message] | None = None,
        memory_context: str = "",
        require_exact_prefix: bool = True,
        **request_kwargs: Any,
    ) -> Iterator[str]:
        """Verify and consume the prepared prefix, then stream one response."""
        prime_wait = self.wait_for_prepared_prefix()
        history_snapshot = deepcopy(list(history or []))
        memory_context_snapshot = str(memory_context)
        actual_snapshot = self.shape_prefix(
            history=history_snapshot,
            memory_context=memory_context_snapshot,
            reason="real_request",
        )

        with self._lock:
            self._assert_open()

            if self._request_active:
                raise RuntimeError("A real model request is already active.")

            prepared_snapshot = self._prepared_snapshot
            prefix_match = (
                prepared_snapshot is not None
                and prepared_snapshot.sha256 == actual_snapshot.sha256
            )

            if prefix_match:
                request_snapshot = prepared_snapshot
                prefix_source = "prepared_snapshot"
            else:
                request_snapshot = actual_snapshot
                prefix_source = "fresh_snapshot"

            print(
                "[ICCS PREFIX] "
                f"match={str(prefix_match).lower()} "
                f"required={str(bool(require_exact_prefix)).lower()} "
                f"source={prefix_source} "
                f"prepared="
                f"{prepared_snapshot.sha256 if prepared_snapshot else '<none>'} "
                f"actual={actual_snapshot.sha256}",
                flush=True,
            )

            if require_exact_prefix and not prefix_match:
                raise RuntimeError(
                    "ICCS exact-prefix contract failed before the real model request. "
                    f"prepared="
                    f"{prepared_snapshot.sha256 if prepared_snapshot else '<none>'} "
                    f"actual={actual_snapshot.sha256}"
                )

            self._request_active = True
            self._prepared_snapshot = None

        completion_state = request_kwargs.get("completion_state")
        iccs_metrics = {
            "iccs_wait_seconds": prime_wait.wait_seconds,
            "iccs_prefix_match": prefix_match,
            "iccs_prefix_source": prefix_source,
            "iccs_prefix_sha256": request_snapshot.sha256,
        }

        if isinstance(completion_state, dict):
            completion_state.update(iccs_metrics)

        try:
            yield from self._backend.stream(
                prefix_messages=request_snapshot.as_messages(),
                prefix_source=prefix_source,
                history=history_snapshot,
                memory_context=memory_context_snapshot,
                **request_kwargs,
            )
        finally:
            # The concrete request backend may initialize/clear completion_state.
            # Re-publish ICCS metrics after streaming so downstream timing and
            # completion guards see both the backend and ICCS measurements.
            if isinstance(completion_state, dict):
                completion_state.update(iccs_metrics)

            with self._lock:
                self._request_active = False

    def close(self) -> None:
        """Finish pending work and release the background worker once."""
        with self._lock:
            if self._closed:
                return

        try:
            self.wait_for_prepared_prefix()
        finally:
            with self._lock:
                self._closed = True
                self._scheduled_snapshot = None
                self._prepared_snapshot = None

            self._executor.shutdown(
                wait=True,
                cancel_futures=False,
            )

    def _assert_open(self) -> None:
        if self._closed:
            raise RuntimeError("ICCS is closed.")

    def _assert_idle(self) -> None:
        if self._request_active:
            raise RuntimeError("Cannot prime while a real model request is active.")

        if self._future is not None:
            raise RuntimeError(
                "An ICCS prime is already pending. Wait before scheduling another."
            )

    @staticmethod
    def _log_prime(
        *,
        mode: str,
        snapshot: PrefixSnapshot,
    ) -> None:
        print(
            "[ICCS PRIME] "
            f"mode={mode} "
            f"reason={snapshot.reason} "
            f"history_messages={snapshot.history_messages} "
            f"prefix_messages={snapshot.prefix_messages} "
            f"memory_context_chars={snapshot.memory_context_chars} "
            f"expected_prefix_sha256={snapshot.sha256}",
            flush=True,
        )


def _prime_result_prefix_sha256(result: PrimeResult) -> str:
    if isinstance(result, Mapping):
        return str(result.get("prefix_sha256", ""))

    return str(getattr(result, "prefix_sha256", ""))
