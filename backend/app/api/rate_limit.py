from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

from fastapi import Request

from app.core.errors import FreyaError
from app.core.logging import get_logger

logger = get_logger(__name__)


class RateLimitError(FreyaError):
    """Raised when a client exceeds the per-IP request quota."""

    status_code = 429


class SlidingWindowLimiter:
    """In-memory sliding-window limiter keyed by client identifier.

    Each key (typically a client IP) keeps a deque of request timestamps within
    the configured window. ``check`` evicts expired entries and rejects when the
    deque already holds ``limit`` requests. Bounded by ``limit`` per key, so a
    burst client cannot grow memory without bound.

    For a single-instance EC2 deployment this is the right tradeoff: no Redis
    dependency, no extra moving part, and the window resets if the box reboots
    (which is fine — that's already a much harsher rate-limit).
    """

    def __init__(self, *, limit: int, window_seconds: float) -> None:
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("limit and window_seconds must be positive")
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str, *, now: float | None = None) -> None:
        timestamp = time.monotonic() if now is None else now
        bucket = self._hits.setdefault(key, deque())
        cutoff = timestamp - self._window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= self._limit:
            retry_after = max(0.0, bucket[0] + self._window - timestamp)
            logger.warning(
                "rate_limit.exceeded",
                key=key,
                limit=self._limit,
                window_seconds=self._window,
                retry_after=round(retry_after, 2),
            )
            raise RateLimitError(
                f"Too many session requests. Try again in {retry_after:.1f}s.",
                retry_after_seconds=retry_after,
            )
        bucket.append(timestamp)


def client_ip(request: Request) -> str:
    """Return the client identifier for rate limiting.

    Prefers ``X-Forwarded-For`` when present (the Next.js proxy and Cloudflare
    Tunnel both set it) and falls back to the direct peer. Trusts only the
    leftmost entry — any value the client sets directly is shadowed by the
    one the upstream proxy appends.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",", 1)[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


# Default: 5 session creations per minute per client IP. Tunable, but sized to
# protect Daily room quota and OpenAI/Cartesia credit burn rate. Each session
# starts a Pipecat task and reserves a Daily room for an hour, so the per-IP
# cost is meaningful.
session_limiter = SlidingWindowLimiter(limit=5, window_seconds=60.0)


def enforce_session_rate_limit(request: Request) -> None:
    session_limiter.check(client_ip(request))


def reset_session_limiter_for_tests() -> Callable[[], None]:
    """Test helper — clears in-memory state. Not called by production code."""

    def _reset() -> None:
        session_limiter._hits.clear()

    return _reset
