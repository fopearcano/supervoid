"""In-process per-user rate + concurrency limiting for the Brain Gateway.

A token bucket caps the request *rate*; an asyncio semaphore caps *concurrency*.
Both are keyed by user id and live in module-level dicts, so the limits are
**per uvicorn worker / process** (not shared across workers or replicas — the
effective limit is multiplied by the worker count). That is acceptable for a
local-first studio gateway; document it rather than reaching for Redis.

The per-key dicts are never evicted, so they grow with the number of *distinct
users* seen by the worker (a bucket/semaphore is a few dozen bytes). For a
single-studio deployment that set is small and bounded; a multi-tenant SaaS
would want an LRU/TTL eviction pass here.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class _Bucket:
    capacity: float
    refill_per_sec: float
    tokens: float = field(default=0.0)
    updated: float = field(default=0.0)


class RateLimiter:
    """A per-key token bucket. ``allow(key)`` consumes one token if available."""

    def __init__(self, *, rate_per_min: int, burst: int, clock=time.monotonic) -> None:
        self._capacity = float(burst)
        self._refill = rate_per_min / 60.0
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}

    def _bucket(self, key: str) -> _Bucket:
        b = self._buckets.get(key)
        if b is None:
            b = _Bucket(capacity=self._capacity, refill_per_sec=self._refill,
                        tokens=self._capacity, updated=self._clock())
            self._buckets[key] = b
        return b

    def allow(self, key: str) -> bool:
        b = self._bucket(key)
        now = self._clock()
        elapsed = max(0.0, now - b.updated)
        b.tokens = min(b.capacity, b.tokens + elapsed * b.refill_per_sec)
        b.updated = now
        if b.tokens >= 1.0:
            b.tokens -= 1.0
            return True
        return False

    def retry_after(self, key: str) -> int:
        """Whole seconds until at least one token is available (>= 1)."""
        b = self._bucket(key)
        if b.tokens >= 1.0 or b.refill_per_sec <= 0:
            return 1
        return max(1, int((1.0 - b.tokens) / b.refill_per_sec) + 1)


class ConcurrencyLimiter:
    """Per-key concurrency cap. Semaphores are created lazily under a lock so two
    concurrent first-requests for a key don't race two different semaphores."""

    def __init__(self, *, max_concurrency: int) -> None:
        self._max = max_concurrency
        self._sems: dict[str, asyncio.Semaphore] = {}
        self._lock = asyncio.Lock()

    async def _sem(self, key: str) -> asyncio.Semaphore:
        async with self._lock:
            sem = self._sems.get(key)
            if sem is None:
                sem = asyncio.Semaphore(self._max)
                self._sems[key] = sem
            return sem

    def guard(self, key: str):
        limiter = self

        class _Guard:
            async def __aenter__(self):
                self._sem = await limiter._sem(key)
                # Acquire without an indefinite wait so an over-subscribed user
                # gets a clean 429 rather than hanging.
                try:
                    await asyncio.wait_for(self._sem.acquire(), timeout=30.0)
                except asyncio.TimeoutError as exc:  # pragma: no cover - timing
                    raise ConcurrencyExceeded() from exc
                return self

            async def __aexit__(self, *exc):
                self._sem.release()
                return False

        return _Guard()


class ConcurrencyExceeded(Exception):
    """Raised when a user's concurrent-request slot could not be acquired."""
