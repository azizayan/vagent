from functools import lru_cache
from typing import Annotated, cast

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.errors import ConfigError


class Settings(BaseSettings):
    """Environment-driven configuration.

    Upstream-service credentials are optional at load time so the stack can boot
    before keys are provisioned. Each service must call :meth:`require` before
    using its key, which raises :class:`ConfigError` with the missing variable
    name — matching the "fail fast with the variable name in the error" rule
    from CLAUDE.md.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ---- OpenAI ----
    OPENAI_API_KEY: SecretStr | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # ---- Deepgram ----
    DEEPGRAM_API_KEY: SecretStr | None = None

    # ---- Cartesia ----
    CARTESIA_API_KEY: SecretStr | None = None
    CARTESIA_DEFAULT_VOICE_ID: str | None = None

    # ---- Daily ----
    DAILY_API_KEY: SecretStr | None = None
    DAILY_DOMAIN: str | None = None

    # ---- Qdrant help center ----
    QDRANT_URL: str = "http://qdrant:6333"
    QDRANT_COLLECTION: str = "freya_help_center"

    # ---- Runtime ----
    # NoDecode bypasses pydantic-settings' built-in JSON parse so the env value
    # arrives as a raw string and our field_validator below handles it.
    BACKEND_CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    LOG_LEVEL: str = "INFO"
    USER_IDLE_PROMPT_SECONDS: float = Field(default=60, gt=0)
    SESSION_IDLE_CLOSE_SECONDS: float = Field(default=300, gt=0)

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        """Accept either comma-separated (`a,b`) or JSON array (`["a","b"]`).

        pydantic-settings defaults to JSON-only for complex types, which makes
        the env file awkward to author. Allow the common comma form too and
        leave JSON / native lists untouched.
        """
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return stripped  # JSON — let pydantic decode
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _validate_idle_timeouts(self) -> "Settings":
        if self.SESSION_IDLE_CLOSE_SECONDS <= self.USER_IDLE_PROMPT_SECONDS:
            raise ValueError(
                "SESSION_IDLE_CLOSE_SECONDS must be greater than USER_IDLE_PROMPT_SECONDS"
            )
        return self

    def require(self, name: str) -> SecretStr | str:
        value = getattr(self, name, None)
        if value is None or (isinstance(value, SecretStr) and not value.get_secret_value()):
            raise ConfigError(f"Required environment variable {name} is not set")
        return cast(SecretStr | str, value)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
