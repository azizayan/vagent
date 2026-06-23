from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import health, session
from app.core.errors import FreyaError
from app.core.logging import configure_logging, get_logger
from app.core.settings import get_settings
from app.services.agent_runner import AgentRunner
from app.services.daily import DailyService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    get_logger(__name__).info("backend.start", version=__version__)
    app.state.agent_runner = AgentRunner(settings)
    app.state.daily_service = DailyService(settings)
    yield
    await app.state.agent_runner.close()
    await app.state.daily_service.close()
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
    app.include_router(session.router)

    return app


app = create_app()
