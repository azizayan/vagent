from __future__ import annotations


def map_interruptibility(pct: int) -> dict[str, float]:
    """Map interruptibility to Pipecat ``VADParams`` values.

    Let ``t = clamp(pct, 0, 100) / 100``. Each parameter uses linear
    interpolation ``low + (high - low) * t``:

    - ``confidence``: 0.85 → 0.45
    - ``start_secs``: 0.30 → 0.05
    - ``stop_secs``: 0.80 → 0.15
    - ``min_volume``: 0.60 → 0.35

    Higher percentages therefore recognize quieter speech sooner and end turns
    faster, making the bot more willing to yield.
    """

    t = min(max(pct, 0), 100) / 100

    def lerp(low: float, high: float) -> float:
        return round(low + (high - low) * t, 4)

    return {
        "confidence": lerp(0.85, 0.45),
        "start_secs": lerp(0.30, 0.05),
        "stop_secs": lerp(0.80, 0.15),
        "min_volume": lerp(0.60, 0.35),
    }
