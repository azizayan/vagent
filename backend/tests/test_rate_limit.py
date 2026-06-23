from __future__ import annotations

import pytest

from app.api.rate_limit import RateLimitError, SlidingWindowLimiter


def test_allows_burst_up_to_limit() -> None:
    limiter = SlidingWindowLimiter(limit=3, window_seconds=10.0)
    for _ in range(3):
        limiter.check("1.1.1.1", now=0.0)


def test_rejects_when_burst_exceeds_limit() -> None:
    limiter = SlidingWindowLimiter(limit=3, window_seconds=10.0)
    for _ in range(3):
        limiter.check("1.1.1.1", now=0.0)
    with pytest.raises(RateLimitError):
        limiter.check("1.1.1.1", now=0.0)


def test_window_slides_so_old_hits_expire() -> None:
    limiter = SlidingWindowLimiter(limit=2, window_seconds=10.0)
    limiter.check("1.1.1.1", now=0.0)
    limiter.check("1.1.1.1", now=1.0)
    # 11s later the first hit has dropped out — one slot is free again.
    limiter.check("1.1.1.1", now=11.0)


def test_per_key_isolation() -> None:
    limiter = SlidingWindowLimiter(limit=1, window_seconds=10.0)
    limiter.check("1.1.1.1", now=0.0)
    # A different IP must not be affected by 1.1.1.1's burst.
    limiter.check("2.2.2.2", now=0.0)


def test_invalid_construction_rejected() -> None:
    with pytest.raises(ValueError):
        SlidingWindowLimiter(limit=0, window_seconds=10.0)
    with pytest.raises(ValueError):
        SlidingWindowLimiter(limit=1, window_seconds=0)
