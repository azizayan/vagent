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


def _tracker_in_speaking_state(events: list, monkeypatch: pytest.MonkeyPatch) -> StateTracker:
    monkeypatch.setattr(st_module.time, "monotonic", lambda: 0.0)

    async def collect(event):
        events.append(event)

    tracker = StateTracker(session_start=0.0, on_event=collect)
    tracker.push_frame = AsyncMock()
    return tracker


@pytest.mark.asyncio
async def test_interruption_while_speaking_emits_one_interruption_then_listening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list = []
    tracker = _tracker_in_speaking_state(events, monkeypatch)

    # Drive FSM to SPEAKING
    await tracker.process_frame(UserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await tracker.process_frame(BotStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    events.clear()

    # Interruption
    await tracker.process_frame(UserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    interruption_events = [e for e in events if isinstance(e, InterruptionEvent)]
    state_events = [e for e in events if isinstance(e, StateEvent)]

    assert len(interruption_events) == 1
    assert len(state_events) == 1
    assert state_events[0].state == "LISTENING"
    # InterruptionEvent must come before the LISTENING state event
    assert events.index(interruption_events[0]) < events.index(state_events[0])
    # Frame must not be swallowed
    tracker.push_frame.assert_called()


@pytest.mark.asyncio
async def test_interruption_frame_is_pushed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list = []
    tracker = _tracker_in_speaking_state(events, monkeypatch)

    await tracker.process_frame(UserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await tracker.process_frame(BotStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    tracker.push_frame.reset_mock()

    frame = UserStartedSpeakingFrame()
    await tracker.process_frame(frame, FrameDirection.DOWNSTREAM)

    # push_frame must have been called with the original frame
    pushed_frames = [call.args[0] for call in tracker.push_frame.call_args_list]
    assert frame in pushed_frames


@pytest.mark.asyncio
async def test_no_interruption_while_listening(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list = []
    tracker = _tracker_in_speaking_state(events, monkeypatch)

    # Drive to LISTENING (via bot speaking then stopping)
    await tracker.process_frame(BotStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    events.clear()

    await tracker.process_frame(UserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    assert not any(isinstance(e, InterruptionEvent) for e in events)


@pytest.mark.asyncio
async def test_interruption_while_thinking_emits_one_interruption_then_listening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list = []
    tracker = _tracker_in_speaking_state(events, monkeypatch)

    # Drive to THINKING
    await tracker.process_frame(UserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    events.clear()

    await tracker.process_frame(UserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    interruption_events = [e for e in events if isinstance(e, InterruptionEvent)]
    state_events = [e for e in events if isinstance(e, StateEvent)]

    assert len(interruption_events) == 1
    assert len(state_events) == 1
    assert state_events[0].state == "LISTENING"
    assert events.index(interruption_events[0]) < events.index(state_events[0])
    tracker.push_frame.assert_called()


@pytest.mark.asyncio
async def test_interruption_while_thinking_clears_latency_timer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a THINKING interruption, a stray BotStartedSpeakingFrame must not
    emit a LatencyEvent measured against the abandoned turn."""
    events: list = []
    tracker = _tracker_in_speaking_state(events, monkeypatch)

    # Drive to THINKING, then interrupt
    await tracker.process_frame(UserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await tracker.process_frame(UserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    events.clear()

    # If a late BotStartedSpeakingFrame leaks through from the cancelled LLM,
    # no LatencyEvent must be emitted (timer was abandoned).
    await tracker.process_frame(BotStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    assert not any(isinstance(e, LatencyEvent) for e in events)


@pytest.mark.asyncio
async def test_no_interruption_while_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list = []
    tracker = _tracker_in_speaking_state(events, monkeypatch)

    await tracker.process_frame(UserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    assert not any(isinstance(e, InterruptionEvent) for e in events)
