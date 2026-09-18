from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: float = 0.0


class WebullOrderRateLimiter:
    """Process-wide throttle shared by every paper account worker."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._attempts: deque[float] = deque()
        self._last_attempt: float | None = None
        self._cooldown_until = 0.0

    def acquire(
        self,
        *,
        min_interval_seconds: float,
        max_orders_per_minute: int,
    ) -> RateLimitResult:
        now = self._clock()
        with self._lock:
            while self._attempts and now - self._attempts[0] >= 60:
                self._attempts.popleft()

            retry_at = self._cooldown_until
            if self._last_attempt is not None:
                retry_at = max(retry_at, self._last_attempt + min_interval_seconds)
            if len(self._attempts) >= max_orders_per_minute:
                retry_at = max(retry_at, self._attempts[0] + 60)
            if retry_at > now:
                return RateLimitResult(False, retry_at - now)

            self._attempts.append(now)
            self._last_attempt = now
            return RateLimitResult(True)

    def cool_down(self, seconds: float) -> None:
        with self._lock:
            self._cooldown_until = max(self._cooldown_until, self._clock() + seconds)
