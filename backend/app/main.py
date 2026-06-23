from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import health, session
from app.core.errors import FreyaError
from app.core.logging import configure_logging, get_logger
from app.core.settings import get_settings
from app.services.agent_runner import AgentRunner
from app.services.daily import DailyService
from app.services.help_center import HelpCenterService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    get_logger(__name__).info("backend.start", version=__version__)
    app.state.help_center = HelpCenterService(settings)
    await app.state.help_center.seed_if_needed()
    app.state.agent_runner = AgentRunner(settings, help_center=app.state.help_center)
    app.state.daily_service = DailyService(settings)
    yield
    await app.state.agent_runner.close()
    await app.state.daily_service.close()
    await app.state.help_center.close()
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
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Convert FastAPI's verbose Pydantic errors to our `{error, message, fields}`
        shape so the frontend has one error contract and can display per-field hints.
        """
        fields: dict[str, str] = {}
        for err in exc.errors():
            path = ".".join(str(part) for part in err.get("loc", ()) if part != "body")
            if not path:
                path = "request"
            # Keep only the first error per field — extra ones are usually noise
            # from cascading validators.
            fields.setdefault(path, err.get("msg", "invalid value"))

        # Build a short human summary: "tts_voice_id: required; max_tokens: must be ≤ 4096"
        summary = "; ".join(f"{name}: {msg}" for name, msg in fields.items())
        get_logger(__name__).info(
            "request.validation_failed",
            path=request.url.path,
            fields=fields,
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": "ValidationError",
                "message": summary or "Request body failed validation.",
                "fields": fields,
            },
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
