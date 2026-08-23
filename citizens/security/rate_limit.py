"""Small in-memory rate limiter for public endpoints (single-process app).

Not a substitute for infrastructure-level protection, but keeps token
brute-forcing and accidental client loops in check.
"""

import threading
import time

from fastapi import HTTPException, Request


class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_seconds: float):
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._events: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            events = [t for t in self._events.get(key, []) if now - t < self.window_seconds]
            if len(events) >= self.max_events:
                self._events[key] = events
                raise HTTPException(status_code=429, detail="Too many requests")
            events.append(now)
            self._events[key] = events
            # opportunistic cleanup so the dict cannot grow unbounded
            if len(self._events) > 10000:
                cutoff = now - self.window_seconds
                self._events = {
                    k: [t for t in v if t > cutoff] for k, v in self._events.items() if v and v[-1] > cutoff
                }


JOIN_LIMITER = SlidingWindowLimiter(max_events=10, window_seconds=60)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
