"""Domain exception types.

Route handlers map these to HTTP responses in one place
(see ``app.main.register_exception_handlers``). Services raise these — never
raw ``HTTPException`` — so the HTTP boundary stays in the API layer.

All errors render to the same JSON contract::

    {"error": "<ErrorClassName>", "message": "<human-readable>", "fields": {...}, "retry_after_seconds": ...}

``fields`` and ``retry_after_seconds`` are optional — only the keys the
caller actually needs to act on are sent. This keeps the frontend's
``ApiError`` handling a single code path.
"""

from __future__ import annotations

from typing import Any


class FreyaError(Exception):
    """Base class for application errors."""

    status_code: int = 500

    def __init__(
        self,
        message: str = "",
        *,
        fields: dict[str, str] | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.fields = fields
        self.retry_after_seconds = retry_after_seconds

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error": type(self).__name__,
            "message": str(self),
        }
        if self.fields:
            payload["fields"] = self.fields
        if self.retry_after_seconds is not None:
            payload["retry_after_seconds"] = round(self.retry_after_seconds, 2)
        return payload


class ConfigError(FreyaError):
    """Required configuration is missing or invalid."""

    status_code = 500


class ConfigValidationError(FreyaError):
    """User-submitted session config failed validation."""

    status_code = 422


class UpstreamServiceError(FreyaError):
    """A third-party service (Daily/OpenAI/Deepgram/Cartesia) failed."""

    status_code = 502
