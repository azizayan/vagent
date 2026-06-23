from __future__ import annotations

import asyncio

import pytest

from app.core.settings import Settings
from app.schemas.config import SessionConfig
from app.services.agent_runner import AgentRunner


def config() -> SessionConfig:
    return SessionConfig(tts_voice_id="voice-1")


def settings() -> Settings:
    return Settings(
        OPENAI_API_KEY="openai",
        DEEPGRAM_API_KEY="deepgram",
        CARTESIA_API_KEY="cartesia",
    )


@pytest.mark.asyncio
async def test_agent_runner_removes_completed_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = asyncio.Event()

    async def fake_run_bot(**kwargs: object) -> None:
        completed.set()

    monkeypatch.setattr("app.services.agent_runner.run_bot", fake_run_bot)
    runner = AgentRunner(settings())

    runner.start(
        session_id="session-1",
        room_url="https://test.daily.co/room",
        token="token",
        config=config(),
    )
    await completed.wait()
    await asyncio.sleep(0)

    assert runner._tasks == {}


@pytest.mark.asyncio
async def test_agent_runner_close_cancels_active_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def fake_run_bot(**kwargs: object) -> None:
        started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr("app.services.agent_runner.run_bot", fake_run_bot)
    runner = AgentRunner(settings())
    runner.start(
        session_id="session-1",
        room_url="https://test.daily.co/room",
        token="token",
        config=config(),
    )
    await started.wait()

    await runner.close()

    assert cancelled.is_set()
    assert runner._tasks == {}
