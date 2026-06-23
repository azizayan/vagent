from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Request, status
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.schemas.config import SessionConfig, SessionResponse
from app.services.agent_runner import AgentRunner
from app.services.daily import DailyService

router = APIRouter(tags=["session"])


@router.post("/session", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(config: SessionConfig, request: Request) -> SessionResponse:
    session_id = uuid4().hex
    bind_contextvars(session_id=session_id)
    try:
        daily: DailyService = request.app.state.daily_service
        agent_runner: AgentRunner = request.app.state.agent_runner
        agent_runner.ensure_ready()
        session = await daily.create_session(session_id)
        agent_runner.start(
            session_id=session_id,
            room_url=session.room_url,
            token=session.bot_token,
            config=config,
        )
        return SessionResponse(
            room_url=session.room_url,
            token=session.user_token,
            session_id=session_id,
        )
    finally:
        clear_contextvars()
