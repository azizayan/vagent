from __future__ import annotations

import asyncio

from app.bot import run_bot
from app.core.logging import get_logger
from app.core.settings import Settings
from app.schemas.config import SessionConfig

logger = get_logger(__name__)


class AgentRunner:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def ensure_ready(self) -> None:
        for name in ("OPENAI_API_KEY", "DEEPGRAM_API_KEY", "CARTESIA_API_KEY"):
            self._settings.require(name)

    def start(
        self,
        *,
        session_id: str,
        room_url: str,
        token: str,
        config: SessionConfig,
    ) -> None:
        self.ensure_ready()
        task = asyncio.create_task(
            run_bot(
                settings=self._settings,
                room_url=room_url,
                token=token,
                config=config,
                session_id=session_id,
            ),
            name=f"freya-agent-{session_id}",
        )
        self._tasks[session_id] = task
        task.add_done_callback(lambda completed: self._on_done(session_id, completed))

    async def close(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    def _on_done(self, session_id: str, task: asyncio.Task[None]) -> None:
        self._tasks.pop(session_id, None)
        if task.cancelled():
            return
        error = task.exception()
        if error:
            logger.error(
                "agent.failed",
                session_id=session_id,
                error_type=type(error).__name__,
                message=str(error),
            )
