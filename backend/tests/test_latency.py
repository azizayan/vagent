from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection

from app.pipeline.processors import state_tracker as st_module
from app.pipeline.processors.state_tracker import StateTracker
from app.schemas.events import LatencyEvent, StateEvent


@pytest.mark.asyncio
async def test_latency_ms_equals_gap_between_anchors(monkeypatch: pytest.MonkeyPatch) -> None:
    """latency.ms must equal the time between UserStoppedSpeakingFrame and BotStartedSpeakingFrame."""
    # Values: THINKING _latency_start anchor, _now_ms(), BotStarted latency calc, _now_ms()
    # Extra trailing value absorbs any additional calls during pytest teardown.
    _times = [100.0, 100.0, 100.250, 100.250]
    _calls = [0]

    def _fake_monotonic() -> float:
        v = _times[min(_calls[0], len(_times) - 1)]
        _calls[0] += 1
        return v

    monkeypatch.setattr(st_module.time, "monotonic", _fake_monotonic)

    events: list = []

    async def collect(event):
        events.append(event)

    tracker = StateTracker(session_start=100.0, on_event=collect)
    tracker.push_frame = AsyncMock()

    await tracker.process_frame(UserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await tracker.process_frame(BotStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    latency_events = [e for e in events if isinstance(e, LatencyEvent)]
    assert len(latency_events) == 1
    assert abs(latency_events[0].ms - 250.0) < 0.1


@pytest.mark.asyncio
async def test_second_bot_started_while_speaking_no_extra_latency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A BotStartedSpeakingFrame that arrives while already SPEAKING must not emit another latency."""
    monkeypatch.setattr(st_module.time, "monotonic", lambda: 0.0)

    events: list = []

    async def collect(event):
        events.append(event)

    tracker = StateTracker(session_start=0.0, on_event=collect)
    tracker.push_frame = AsyncMock()

    # Drive to SPEAKING
    await tracker.process_frame(UserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await tracker.process_frame(BotStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    events.clear()

    # Second BotStartedSpeakingFrame while already SPEAKING
    await tracker.process_frame(BotStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    assert not any(isinstance(e, LatencyEvent) for e in events)


@pytest.mark.asyncio
async def test_latency_at_field_is_ms_since_session_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LatencyEvent.at should be ms elapsed since session_start, not an absolute timestamp."""
    # session starts at t=50s; THINKING at t=50s; SPEAKING at t=50.1s
    _times = [50.0, 50.0, 50.1, 50.1]
    _calls = [0]

    def _fake_monotonic() -> float:
        v = _times[min(_calls[0], len(_times) - 1)]
        _calls[0] += 1
        return v

    monkeypatch.setattr(st_module.time, "monotonic", _fake_monotonic)

    events: list = []

    async def collect(event):
        events.append(event)

    tracker = StateTracker(session_start=50.0, on_event=collect)
    tracker.push_frame = AsyncMock()

    await tracker.process_frame(UserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await tracker.process_frame(BotStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    state_events = [e for e in events if isinstance(e, StateEvent)]
    latency_events = [e for e in events if isinstance(e, LatencyEvent)]

    # at values should be relative to session_start=50.0, not absolute
    assert state_events[0].at == pytest.approx(0.0, abs=1.0)  # THINKING at t=0ms
    assert latency_events[0].at == pytest.approx(100.0, abs=1.0)  # SPEAKING at t=100ms
    assert latency_events[0].ms == pytest.approx(100.0, abs=1.0)  # gap = 100ms
