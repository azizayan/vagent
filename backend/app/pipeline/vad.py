from __future__ import annotations

from typing import TypedDict


def interruptions_enabled(pct: int) -> bool:
    """Whether barge-in is allowed at all.

    At ``pct == 0`` interruption broadcasting is hard-disabled via
    ``enable_interruptions=False`` on the user-turn start strategy. The bot
    keeps the floor regardless of what is detected — the semantically correct
    meaning of "0% interruptibility."
    """
    return pct > 0


def map_interruptibility(pct: int) -> dict[str, float]:
    """Map interruptibility to Pipecat ``VADParams`` values.

    With ``MinWordsUserTurnStartStrategy`` driving barge-in, ``start_secs`` no
    longer gates interruptions (the strategy ignores VAD-started frames). The
    VAD still runs inside the user aggregator for **turn-stop** detection, so
    ``stop_secs``, ``confidence``, and ``min_volume`` continue to matter:

    - ``confidence``: 0.90 → 0.40  — how certain the VAD must be that audio is
      speech vs. noise.
    - ``start_secs``: held flat at 0.20 — small enough that turn aggregation
      starts promptly, but not used as the interruption gate.
    - ``stop_secs``: 0.80 → 0.60   — turn-end patience, kept generous.
    - ``min_volume``: 0.70 → 0.30  — quiet utterances register only at high
      sensitivity.
    """

    t = min(max(pct, 0), 100) / 100

    def lerp(low: float, high: float) -> float:
        return round(low + (high - low) * t, 4)

    return {
        "confidence": lerp(0.90, 0.40),
        "start_secs": 0.20,
        "stop_secs": lerp(0.80, 0.60),
        "min_volume": lerp(0.70, 0.30),
    }


class InterruptGateParams(TypedDict):
    """Knobs for ``MinWordsUserTurnStartStrategy`` while the bot is speaking."""

    min_words: int
    use_interim: bool


def map_interrupt_gate(pct: int) -> InterruptGateParams:
    """Map interruptibility to word-gate parameters.

    ``pct == 0`` is handled separately via ``interruptions_enabled``; the
    returned params here are only consulted when interruptions are allowed.

    The 0..50 band is given four distinct levels so users feel the slider:

    | pct    | min_words | use_interim | feel                              |
    |--------|-----------|-------------|-----------------------------------|
    |  1..15 | 4         | False       | very hard — must wait for final   |
    | 16..30 | 4         | True        | hard — 4 words via interim        |
    | 31..50 | 3         | True        | medium-hard                       |
    | 51..75 | 2         | True        | medium                            |
    | 76..100| 1         | True        | hair-trigger                      |

    ``use_interim=False`` defers the trigger until Deepgram emits a final
    transcript (~1 s after the user pauses), which is the main reason the
    low-end levels feel meaningfully different from each other rather than
    only differing by one word.
    """
    p = min(max(pct, 0), 100)
    if p <= 15:
        return {"min_words": 4, "use_interim": False}
    if p <= 30:
        return {"min_words": 4, "use_interim": True}
    if p <= 50:
        return {"min_words": 3, "use_interim": True}
    if p <= 75:
        return {"min_words": 2, "use_interim": True}
    return {"min_words": 1, "use_interim": True}
