from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection

from app.pipeline.processors import state_tracker as st_module
from app.pipeline.processors.state_tracker import StateTracker
from app.schemas.events import InterruptionEvent, LatencyEvent, StateEvent


def _make_tracker(events: list, monkeypatch: pytest.MonkeyPatch) -> StateTracker:
    monkeypatch.setattr(st_module.time, "monotonic", lambda: 0.0)

    async def collect(event):
        events.append(event)

    tracker = StateTracker(session_start=0.0, on_event=collect)
    tracker.push_frame = AsyncMock()
    return tracker


@pytest.mark.asyncio
async def test_user_stopped_speaking_emits_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list = []
    tracker = _make_tracker(events, monkeypatch)

    await tracker.process_frame(UserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    assert len(events) == 1
    assert isinstance(events[0], StateEvent)
    assert events[0].state == "THINKING"
    tracker.push_frame.assert_called_once()


@pytest.mark.asyncio
async def test_bot_started_after_thinking_emits_speaking_and_latency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list = []
    tracker = _make_tracker(events, monkeypatch)

    await tracker.process_frame(UserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await tracker.process_frame(BotStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    state_events = [e for e in events if isinstance(e, StateEvent)]
    latency_events = [e for e in events if isinstance(e, LatencyEvent)]

    assert len(state_events) == 2
    assert state_events[0].state == "THINKING"
    assert state_events[1].state == "SPEAKING"
    assert len(latency_events) == 1
    assert tracker.push_frame.call_count == 2


@pytest.mark.asyncio
async def test_bot_stopped_speaking_emits_listening(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list = []
    tracker = _make_tracker(events, monkeypatch)

    await tracker.process_frame(BotStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    assert len(events) == 1
    assert isinstance(events[0], StateEvent)
    assert events[0].state == "LISTENING"
    tracker.push_frame.assert_called_once()


@pytest.mark.asyncio
async def test_proactive_bot_started_emits_speaking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Greeting case: BotStartedSpeakingFrame arrives before any user speech."""
    events: list = []
    tracker = _make_tracker(events, monkeypatch)

    await tracker.process_frame(BotStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    assert len(events) == 1
    assert isinstance(events[0], StateEvent)
    assert events[0].state == "SPEAKING"
    tracker.push_frame.assert_called_once()


@pytest.mark.asyncio
async def test_user_started_while_listening_no_interruption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list = []
    tracker = _make_tracker(events, monkeypatch)

    # Drive to LISTENING
    await tracker.process_frame(BotStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    events.clear()

    await tracker.process_frame(UserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    assert not any(isinstance(e, InterruptionEvent) for e in events)
    tracker.push_frame.assert_called()


@pytest.mark.asyncio
async def test_all_frames_are_pushed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list = []
    tracker = _make_tracker(events, monkeypatch)

    frames = [
        UserStoppedSpeakingFrame(),
        BotStartedSpeakingFrame(),
        BotStoppedSpeakingFrame(),
        UserStartedSpeakingFrame(),
    ]
    for frame in frames:
        tracker.push_frame.reset_mock()
        await tracker.process_frame(frame, FrameDirection.DOWNSTREAM)
        tracker.push_frame.assert_called_once()
