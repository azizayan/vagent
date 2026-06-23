from __future__ import annotations

from typing import Any

import pytest
from pipecat.frames.frames import TTSSpeakFrame, UserIdleTimeoutUpdateFrame
from pydantic import ValidationError

from app.core.settings import Settings
from app.pipeline import idle_session as idle_module
from app.pipeline.idle_session import IDLE_PROMPT, IdleSessionCoordinator
from app.schemas.events import SessionEndedEvent


class FakeTask:
    def __init__(self, actions: list[str] | None = None) -> None:
        self.queued_batches: list[list[Any]] = []
        self.stop_calls = 0
        self.actions = actions

    async def queue_frames(self, frames: list[Any]) -> None:
        self.queued_batches.append(frames)

    async def stop_when_done(self) -> None:
        self.stop_calls += 1
        if self.actions is not None:
            self.actions.append("stop")


def test_idle_timeouts_allow_integration_overrides_and_require_ordering() -> None:
    settings = Settings(
        USER_IDLE_PROMPT_SECONDS=10,
        SESSION_IDLE_CLOSE_SECONDS=30,
    )

    assert settings.USER_IDLE_PROMPT_SECONDS == 10
    assert settings.SESSION_IDLE_CLOSE_SECONDS == 30

    with pytest.raises(ValidationError, match="must be greater"):
        Settings(
            USER_IDLE_PROMPT_SECONDS=30,
            SESSION_IDLE_CLOSE_SECONDS=30,
        )


def make_coordinator(
    task: FakeTask,
    events: list[SessionEndedEvent],
    actions: list[str] | None = None,
) -> IdleSessionCoordinator:
    async def collect(event: SessionEndedEvent) -> None:
        events.append(event)
        if actions is not None:
            actions.append("event")

    return IdleSessionCoordinator(
        task=task,
        on_event=collect,  # type: ignore[arg-type]
        session_start=100,
        prompt_seconds=60,
        close_seconds=300,
    )


@pytest.mark.asyncio
async def test_first_idle_queues_timeout_update_and_direct_tts_prompt() -> None:
    task = FakeTask()
    events: list[SessionEndedEvent] = []
    coordinator = make_coordinator(task, events)

    await coordinator.on_user_turn_idle()

    assert len(task.queued_batches) == 1
    timeout_frame, prompt_frame = task.queued_batches[0]
    assert isinstance(timeout_frame, UserIdleTimeoutUpdateFrame)
    assert timeout_frame.timeout == 240
    assert isinstance(prompt_frame, TTSSpeakFrame)
    assert prompt_frame.text == IDLE_PROMPT
    assert prompt_frame.append_to_context is False
    assert task.stop_calls == 0
    assert events == []


@pytest.mark.asyncio
async def test_second_idle_sends_event_before_graceful_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actions: list[str] = []
    task = FakeTask(actions)
    events: list[SessionEndedEvent] = []
    coordinator = make_coordinator(task, events, actions)
    monkeypatch.setattr(idle_module.time, "monotonic", lambda: 400)

    await coordinator.on_user_turn_idle()
    await coordinator.on_user_turn_idle()

    assert actions == ["event", "stop"]
    assert len(events) == 1
    assert events[0].reason == "inactivity"
    assert events[0].at == pytest.approx(300_000)
    assert task.stop_calls == 1


@pytest.mark.asyncio
async def test_user_turn_resets_idle_stages() -> None:
    task = FakeTask()
    events: list[SessionEndedEvent] = []
    coordinator = make_coordinator(task, events)

    await coordinator.on_user_turn_idle()
    await coordinator.on_user_turn_started()
    await coordinator.on_user_turn_idle()

    reset_batch = task.queued_batches[1]
    assert len(reset_batch) == 1
    assert isinstance(reset_batch[0], UserIdleTimeoutUpdateFrame)
    assert reset_batch[0].timeout == 60
    assert isinstance(task.queued_batches[2][1], TTSSpeakFrame)
    assert task.stop_calls == 0
    assert events == []
