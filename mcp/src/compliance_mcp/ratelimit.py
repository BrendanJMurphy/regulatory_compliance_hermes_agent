"""Per-requester rate limiting.

A token bucket per requester identity, refilled continuously. This is a safety net against
a runaway agent loop or a misbehaving client hammering the systems of record, not a fairness
scheduler. Limits are generous for human-paced work and tight enough that a loop is cut off
within seconds. Denials are audited like any other refusal.
"""

from __future__ import annotations

import threading
import time


class RateLimited(PermissionError):
    """The requester exceeded the per-minute call budget. Safe to show."""


class TokenBucketLimiter:
    def __init__(self, *, per_minute: int, burst: int | None = None, clock=time.monotonic) -> None:
        self._rate = per_minute / 60.0
        self._capacity = float(burst or per_minute)
        self._clock = clock
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_refill)

    def check(self, key: str) -> None:
        """Consume one token for ``key`` or raise ``RateLimited``."""
        now = self._clock()
        with self._lock:
            tokens, last = self._buckets.get(key, (self._capacity, now))
            tokens = min(self._capacity, tokens + (now - last) * self._rate)
            if tokens < 1.0:
                self._buckets[key] = (tokens, now)
                raise RateLimited(f"rate limit exceeded for '{key}': more than {int(self._capacity)} calls per minute")
            self._buckets[key] = (tokens - 1.0, now)
