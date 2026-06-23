from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class StateEvent(BaseModel):
    type: Literal["state"] = "state"
    state: Literal["LISTENING", "THINKING", "SPEAKING"]
    at: float  # ms since session start (monotonic clock)


class LatencyEvent(BaseModel):
    type: Literal["latency"] = "latency"
    ms: float
    at: float


class InterruptionEvent(BaseModel):
    type: Literal["interruption"] = "interruption"
    at: float


DataChannelEvent = Annotated[
    StateEvent | LatencyEvent | InterruptionEvent,
    Field(discriminator="type"),
]
