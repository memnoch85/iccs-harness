#!/usr/bin/env python3

from __future__ import annotations

from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
)
from concurrent.futures import (
    TimeoutError as FutureTimeoutError,
)
from copy import deepcopy
from typing import Any, Callable


class ContextPrimeCoordinator:
    """
    Run an Ollama context prime in one background worker.

    The main conversation thread may continue listening and transcribing,
    but it must wait for the prime before starting another Ollama request.
    """

    def __init__(
        self,
        prime_function: Callable[..., dict[str, Any]],
    ) -> None:
        self._prime_function = prime_function
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="nancee-context-prime",
        )
        self._future: Future[dict[str, Any]] | None = None

    def is_running(self) -> bool:
        return self._future is not None and not self._future.done()

    def start(
        self,
        *,
        history: list[dict[str, str]],
        memory_context: str,
    ) -> None:
        if self.is_running():
            raise RuntimeError(
                "Cannot start a context prime while another prime is running."
            )

        # Do not let the worker read mutable memory while the main loop
        # continues operating.
        history_snapshot = deepcopy(history)
        memory_context_snapshot = str(memory_context)

        self._future = self._executor.submit(
            self._prime_function,
            history=history_snapshot,
            memory_context=memory_context_snapshot,
        )

    def wait_if_needed(
        self,
        *,
        grace_seconds: float,
        bridge_callback: Callable[[], None] | None = None,
    ) -> bool:
        """
        Wait for the current prime.

        Return True when the bridge callback was used.
        Return False when no prime existed or it completed during grace.
        """

        future = self._future

        if future is None:
            return False

        if grace_seconds < 0:
            raise ValueError("grace_seconds cannot be negative.")

        bridge_used = False

        try:
            future.result(timeout=grace_seconds)

        except FutureTimeoutError:
            if bridge_callback is not None:
                bridge_callback()
                bridge_used = True

            # The bridge audio plays while the prime continues.
            # Do not allow another Ollama request until this completes.
            future.result()

        finally:
            self._future = None

        return bridge_used

    def shutdown(self) -> None:
        self._executor.shutdown(
            wait=True,
            cancel_futures=False,
        )
