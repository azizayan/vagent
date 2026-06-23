import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import health
from app.bot import run_bot
from app.core.errors import FreyaError
from app.core.logging import configure_logging, get_logger
from app.core.settings import get_settings

BOT_ENV_VARS = (
    "OPENAI_API_KEY",
    "DEEPGRAM_API_KEY",
    "CARTESIA_API_KEY",
    "DAILY_API_KEY",
    "DAILY_DOMAIN",
)


def _log_bot_result(task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return
    error = task.exception()
    if error:
        get_logger(__name__).error(
            "bot.failed",
            error_type=type(error).__name__,
            message=str(error),
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    get_logger(__name__).info("backend.start", version=__version__)
    bot_task: asyncio.Task[None] | None = None
    if all(getattr(settings, name) for name in BOT_ENV_VARS):
        bot_task = asyncio.create_task(run_bot(settings), name="freya-voice-bot")
        bot_task.add_done_callback(_log_bot_result)
    else:
        get_logger(__name__).warning("bot.disabled", reason="vendor credentials are incomplete")
    yield
    if bot_task:
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
    get_logger(__name__).info("backend.stop")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(FreyaError)
    async def handle_freya_error(request: Request, exc: FreyaError) -> JSONResponse:
        get_logger(__name__).warning(
            "request.error",
            error_type=type(exc).__name__,
            message=str(exc),
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": type(exc).__name__, "message": str(exc)},
        )


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Freya Voice Agent",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(health.router)

    return app


app = create_app()
