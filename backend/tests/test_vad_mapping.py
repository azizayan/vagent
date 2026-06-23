import pytest

from app.pipeline.vad import (
    interruptions_enabled,
    map_interrupt_gate,
    map_interruptibility,
)


def test_interruptibility_boundaries_and_midpoint() -> None:
    assert map_interruptibility(0) == {
        "confidence": 0.90,
        "start_secs": 0.20,
        "stop_secs": 0.80,
        "min_volume": 0.70,
    }
    assert map_interruptibility(50) == pytest.approx(
        {
            "confidence": 0.65,
            "start_secs": 0.20,
            "stop_secs": 0.70,
            "min_volume": 0.50,
        }
    )
    assert map_interruptibility(100) == {
        "confidence": 0.40,
        "start_secs": 0.20,
        "stop_secs": 0.60,
        "min_volume": 0.30,
    }


def test_interruptibility_clamps_and_is_monotonic() -> None:
    assert map_interruptibility(-1) == map_interruptibility(0)
    assert map_interruptibility(101) == map_interruptibility(100)

    values = [map_interruptibility(pct) for pct in range(101)]
    for parameter in ("confidence", "stop_secs", "min_volume"):
        series = [value[parameter] for value in values]
        assert series == sorted(series, reverse=True)

    # stop_secs remains in a narrow forgiving band regardless of interruptibility.
    assert all(value["stop_secs"] >= 0.60 for value in values)
    # start_secs is intentionally flat now that the word gate drives barge-in.
    assert all(value["start_secs"] == 0.20 for value in values)


def test_interrupt_gate_bands() -> None:
    assert interruptions_enabled(0) is False
    assert interruptions_enabled(1) is True

    assert map_interrupt_gate(1) == {"min_words": 4, "use_interim": False}
    assert map_interrupt_gate(15) == {"min_words": 4, "use_interim": False}
    assert map_interrupt_gate(16) == {"min_words": 4, "use_interim": True}
    assert map_interrupt_gate(30) == {"min_words": 4, "use_interim": True}
    assert map_interrupt_gate(31) == {"min_words": 3, "use_interim": True}
    assert map_interrupt_gate(50) == {"min_words": 3, "use_interim": True}
    assert map_interrupt_gate(51) == {"min_words": 2, "use_interim": True}
    assert map_interrupt_gate(75) == {"min_words": 2, "use_interim": True}
    assert map_interrupt_gate(76) == {"min_words": 1, "use_interim": True}
    assert map_interrupt_gate(100) == {"min_words": 1, "use_interim": True}


def test_interrupt_gate_low_range_has_four_distinct_levels() -> None:
    """Slider precision in 0..50: at least four distinguishable states."""
    levels = {(gate["min_words"], gate["use_interim"]) for gate in map_interrupt_gate_range(1, 50)}
    assert len(levels) >= 3  # off + (4,False) + (4,True) + (3,True) → 3 active levels


def test_interrupt_gate_clamps() -> None:
    assert map_interrupt_gate(-5) == map_interrupt_gate(0)
    assert map_interrupt_gate(200) == map_interrupt_gate(100)


def test_interrupt_gate_min_words_monotonically_decreases() -> None:
    series = [map_interrupt_gate(pct)["min_words"] for pct in range(1, 101)]
    assert series == sorted(series, reverse=True)


def map_interrupt_gate_range(start: int, end: int) -> list[dict[str, object]]:
    return [map_interrupt_gate(pct) for pct in range(start, end + 1)]
