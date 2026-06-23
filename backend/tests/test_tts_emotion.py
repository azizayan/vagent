from __future__ import annotations

import pytest

from app.pipeline.tts_emotion import temperature_to_emotion


@pytest.mark.parametrize(
    "temperature,expected",
    [
        (0.0, "neutral"),
        (0.1, "neutral"),
        (0.33, "neutral"),
        (0.34, None),
        (0.5, None),
        (0.66, None),
        (0.67, "excited"),
        (0.9, "excited"),
        (1.0, "excited"),
    ],
)
def test_temperature_to_emotion_maps_into_three_bands(
    temperature: float, expected: str | None
) -> None:
    assert temperature_to_emotion(temperature) == expected


def test_temperature_to_emotion_is_monotonic() -> None:
    """Increasing temperature must not move toward a flatter emotion."""
    order = {"neutral": 0, None: 1, "excited": 2}
    previous = -1
    for t in [i / 100 for i in range(0, 101)]:
        current = order[temperature_to_emotion(t)]
        assert current >= previous
        previous = current
