"""Domain exception types.

Route handlers map these to HTTP responses in one place
(see ``app.main.register_exception_handlers``). Services raise these — never
raw ``HTTPException`` — so the HTTP boundary stays in the API layer.
"""

from __future__ import annotations


class FreyaError(Exception):
    """Base class for application errors."""

    status_code: int = 500


class ConfigError(FreyaError):
    """Required configuration is missing or invalid."""

    status_code = 500


class ConfigValidationError(FreyaError):
    """User-submitted session config failed validation."""

    status_code = 422


class UpstreamServiceError(FreyaError):
    """A third-party service (Daily/OpenAI/Deepgram/Cartesia) failed."""

    status_code = 502
