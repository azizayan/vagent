from __future__ import annotations

import re
from pathlib import Path

from app.pipeline.prompts import DEFAULT_SYSTEM_PROMPT
from app.schemas.config import SessionConfig
from app.schemas.events import (
    InterruptionEvent,
    LatencyEvent,
    SessionEndedEvent,
    StateEvent,
)

REPOSITORY_ROOT = Path(__file__).parents[2]
FRONTEND_CONTRACT = REPOSITORY_ROOT / "frontend" / "types" / "contract.ts"
FRONTEND_DEFAULTS = REPOSITORY_ROOT / "frontend" / "lib" / "defaults.ts"


def test_session_config_fields_match_frontend_contract() -> None:
    source = FRONTEND_CONTRACT.read_text()
    match = re.search(r"export type SessionConfig = \{(?P<body>.*?)\n\};", source, re.DOTALL)
    assert match is not None

    frontend_fields = set(re.findall(r"^\s+([a-z_]+):", match.group("body"), re.MULTILINE))
    assert frontend_fields == set(SessionConfig.model_fields)


def test_data_channel_event_types_match_frontend_contract() -> None:
    source = FRONTEND_CONTRACT.read_text()
    frontend_types = set(re.findall(r'type: "([a-z_]+)"', source))
    backend_types = {
        StateEvent(state="LISTENING", at=0).type,
        LatencyEvent(ms=0, at=0).type,
        InterruptionEvent(at=0).type,
        SessionEndedEvent(reason="inactivity", at=0).type,
    }

    assert frontend_types == backend_types


def test_default_system_prompt_matches_frontend() -> None:
    source = FRONTEND_DEFAULTS.read_text()
    match = re.search(
        r"export const DEFAULT_SYSTEM_PROMPT = `(?P<prompt>.*?)`;",
        source,
        re.DOTALL,
    )
    assert match is not None
    assert match.group("prompt") == DEFAULT_SYSTEM_PROMPT
