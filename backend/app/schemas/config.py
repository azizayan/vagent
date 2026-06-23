from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
ROLE_MARKERS = re.compile(r"(?im)^\s*(system|assistant|user|developer)\s*:")
MAX_SYSTEM_PROMPT_LENGTH = 4000


class SessionConfig(BaseModel):
    system_prompt: str = Field(default="", max_length=MAX_SYSTEM_PROMPT_LENGTH)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=120, ge=1, le=4096)
    stt_temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    tts_voice_id: str = Field(min_length=1)
    tts_speed: float = Field(default=1.0, ge=0.6, le=1.5)
    tts_temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    interruptibility_pct: int = Field(default=50, ge=0, le=100)

    @field_validator("system_prompt", mode="before")
    @classmethod
    def sanitize_system_prompt(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        prompt = CONTROL_CHARACTERS.sub("", value).strip()
        if ROLE_MARKERS.search(prompt):
            raise ValueError("system prompt must not contain role-injection markers")
        return prompt

    @field_validator("tts_voice_id", mode="before")
    @classmethod
    def strip_voice_id(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class SessionResponse(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)

    room_url: str = Field(serialization_alias="roomUrl")
    token: str
    session_id: str = Field(serialization_alias="sessionId")
