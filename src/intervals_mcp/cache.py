"""A small TTL cache for GET responses.

A coaching conversation re-reads the same window repeatedly -- an agent that
checks wellness, then activities, then wellness again for a different
comparison hits the same intervals.icu endpoint several times a minute.
Caching those responses briefly cuts both latency and exposure to the rate
limit, without risking data staled across a whole session.
"""

import time
from collections.abc import Callable, Hashable
from typing import Any

_MISS = object()


class TTLCache:
    def __init__(self, ttl: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl
        self._clock = clock
        self._store: dict[Hashable, tuple[float, Any]] = {}

    def get(self, key: Hashable) -> Any:
        """Return the cached value for ``key``, or the sentinel ``_MISS``."""
        entry = self._store.get(key)
        if entry is None:
            return _MISS
        expires_at, value = entry
        if self._clock() >= expires_at:
            del self._store[key]
            return _MISS
        return value

    def set(self, key: Hashable, value: Any) -> None:
        if self._ttl <= 0:
            return
        self._store[key] = (self._clock() + self._ttl, value)


MISS = _MISS
