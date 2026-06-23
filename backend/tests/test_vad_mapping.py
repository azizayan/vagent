import pytest

from app.pipeline.vad import map_interruptibility


def test_interruptibility_boundaries_and_midpoint() -> None:
    assert map_interruptibility(0) == {
        "confidence": 0.85,
        "start_secs": 0.30,
        "stop_secs": 0.80,
        "min_volume": 0.60,
    }
    assert map_interruptibility(50) == pytest.approx(
        {
            "confidence": 0.65,
            "start_secs": 0.175,
            "stop_secs": 0.475,
            "min_volume": 0.475,
        }
    )
    assert map_interruptibility(100) == {
        "confidence": 0.45,
        "start_secs": 0.05,
        "stop_secs": 0.15,
        "min_volume": 0.35,
    }


def test_interruptibility_clamps_and_is_monotonic() -> None:
    assert map_interruptibility(-1) == map_interruptibility(0)
    assert map_interruptibility(101) == map_interruptibility(100)

    values = [map_interruptibility(pct) for pct in range(101)]
    for parameter in ("confidence", "start_secs", "stop_secs", "min_volume"):
        series = [value[parameter] for value in values]
        assert series == sorted(series, reverse=True)
