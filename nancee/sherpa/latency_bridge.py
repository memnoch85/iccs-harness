from __future__ import annotations

import threading
from collections.abc import Callable


class LatencyBridge:
    """Fire one callback unless the first-token event resolves in time."""

    def __init__(
        self,
        *,
        delay_seconds: float,
        on_fire: Callable[[], None],
        enabled: bool = True,
    ) -> None:
        if delay_seconds <= 0:
            raise ValueError("delay_seconds must be greater than zero.")

        self._delay_seconds = float(delay_seconds)
        self._on_fire = on_fire
        self._enabled = bool(enabled)
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._resolved = False
        self._fired = False

    @property
    def fired(self) -> bool:
        with self._lock:
            return self._fired

    def start(self) -> None:
        if not self._enabled:
            return

        with self._lock:
            if self._timer is not None:
                raise RuntimeError("LatencyBridge may only be started once.")

            self._timer = threading.Timer(
                self._delay_seconds,
                self._fire,
            )
            self._timer.daemon = True
            self._timer.start()

    def resolve(self) -> bool:
        """Cancel the pending bridge. Return True if it already fired."""
        with self._lock:
            self._resolved = True
            timer = self._timer
            already_fired = self._fired

        if timer is not None:
            timer.cancel()

        return already_fired

    def _fire(self) -> None:
        with self._lock:
            if self._resolved or self._fired:
                return

            self._fired = True

            # Keep bridge audio insertion serialized with
            # resolve(). If the bridge wins the deadline race,
            # its audio must enter the queue before real answer
            # audio is allowed to follow it.
            self._on_fire()
