from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Protocol

from pipecat.frames.frames import Frame, TTSSpeakFrame, UserIdleTimeoutUpdateFrame

from app.schemas.events import DataChannelEvent, SessionEndedEvent

IDLE_PROMPT = "Are you still there? Is there anything I can help with?"

EventCallback = Callable[[DataChannelEvent], Awaitable[None]]


class IdleTask(Protocol):
    async def queue_frames(self, frames: list[Frame]) -> None: ...

    async def stop_when_done(self) -> None: ...


class IdleSessionCoordinator:
    """Coordinates one reminder and graceful closure for each idle period."""

    def __init__(
        self,
        *,
        task: IdleTask,
        on_event: EventCallback,
        session_start: float,
        prompt_seconds: float,
        close_seconds: float,
    ) -> None:
        self._task = task
        self._on_event = on_event
        self._session_start = session_start
        self._prompt_seconds = prompt_seconds
        self._remaining_seconds = close_seconds - prompt_seconds
        self._prompted = False

    def _now_ms(self) -> float:
        return (time.monotonic() - self._session_start) * 1000

    async def on_user_turn_idle(self) -> None:
        if not self._prompted:
            self._prompted = True
            await self._task.queue_frames(
                [
                    UserIdleTimeoutUpdateFrame(timeout=self._remaining_seconds),
                    TTSSpeakFrame(text=IDLE_PROMPT, append_to_context=False),
                ]
            )
            return

        await self._on_event(SessionEndedEvent(reason="inactivity", at=self._now_ms()))
        await self._task.stop_when_done()

    async def on_user_turn_started(self) -> None:
        self._prompted = False
        await self._task.queue_frames([UserIdleTimeoutUpdateFrame(timeout=self._prompt_seconds)])
