from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from enum import Enum, auto

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from app.core.logging import get_logger
from app.schemas.events import DataChannelEvent, InterruptionEvent, LatencyEvent, StateEvent

logger = get_logger(__name__)


class _BotState(Enum):
    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()


EventCallback = Callable[[DataChannelEvent], Awaitable[None]]


class StateTracker(FrameProcessor):
    """Observes pipeline frames and emits state/latency/interruption events.

    Passes every frame through unchanged. The latency clock uses the same two
    anchors as the THINKING→SPEAKING transition so there is one shared measurement.

    FSM transitions:
        UserStoppedSpeakingFrame  → THINKING  (start latency clock)
        BotStartedSpeakingFrame   → SPEAKING  (stop clock, emit LatencyEvent) [only from THINKING]
        BotStoppedSpeakingFrame   → LISTENING
        UserStartedSpeakingFrame  → LISTENING + InterruptionEvent [only from SPEAKING]
    """

    def __init__(
        self,
        *,
        session_start: float,
        on_event: EventCallback,
    ) -> None:
        super().__init__()
        self._session_start = session_start
        self._on_event = on_event
        self._state = _BotState.IDLE
        self._latency_start: float | None = None

    def _now_ms(self) -> float:
        return (time.monotonic() - self._session_start) * 1000

    async def _emit(self, event: DataChannelEvent) -> None:
        await self._on_event(event)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, UserStoppedSpeakingFrame):
            self._state = _BotState.THINKING
            self._latency_start = time.monotonic()
            await self._emit(StateEvent(state="THINKING", at=self._now_ms()))
            logger.debug("state_tracker.thinking")

        elif isinstance(frame, BotStartedSpeakingFrame):
            if self._state == _BotState.THINKING and self._latency_start is not None:
                latency_ms = (time.monotonic() - self._latency_start) * 1000
                self._latency_start = None
                self._state = _BotState.SPEAKING
                now = self._now_ms()
                await self._emit(StateEvent(state="SPEAKING", at=now))
                await self._emit(LatencyEvent(ms=latency_ms, at=now))
                logger.debug("state_tracker.speaking", latency_ms=latency_ms)
            else:
                # Greeting or bot started speaking without a prior UserStoppedSpeakingFrame
                self._state = _BotState.SPEAKING

        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._state = _BotState.LISTENING
            await self._emit(StateEvent(state="LISTENING", at=self._now_ms()))
            logger.debug("state_tracker.listening")

        elif isinstance(frame, UserStartedSpeakingFrame):
            if self._state == _BotState.SPEAKING:
                now = self._now_ms()
                await self._emit(InterruptionEvent(at=now))
                self._state = _BotState.LISTENING
                await self._emit(StateEvent(state="LISTENING", at=now))
                logger.debug("state_tracker.interruption")

        await self.push_frame(frame, direction)
