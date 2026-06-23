from __future__ import annotations

import re
import unicodedata

from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from app.core.logging import get_logger

SAFE_FALLBACK = "Sorry, I generated an invalid response. Please try again."
MAX_RESPONSE_CHARACTERS = 800
MAX_PENDING_CHARACTERS = 500
MAX_WHITESPACE_RUN = 8
MAX_SCRIPT_FAMILIES = 3

SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])(?:\s+|$)|\n+")
SUSPICIOUS_TOKEN = re.compile(
    r"(?:_[A-Z]{3,}|[A-Za-z]+_[A-Za-z_]+|(?:CGFloat|MpAsync|marquebreak|Stacksocumented))"
)

logger = get_logger(__name__)


def _script_families(text: str) -> set[str]:
    families: set[str] = set()
    for character in text:
        if not character.isalpha():
            continue
        name = unicodedata.name(character, "")
        for family in (
            "LATIN",
            "CYRILLIC",
            "GREEK",
            "ARABIC",
            "HEBREW",
            "DEVANAGARI",
            "BENGALI",
            "TELUGU",
            "KANNADA",
            "THAI",
            "HIRAGANA",
            "KATAKANA",
            "HANGUL",
            "CJK",
        ):
            if family in name:
                families.add(family)
                break
    return families


def rejection_reason(text: str) -> str | None:
    """Return why text is unsafe for speech, or ``None`` when it is acceptable."""

    if not text.strip():
        return None
    if any(unicodedata.category(character) == "Cc" for character in text):
        return "control_characters"
    if re.search(rf"\s{{{MAX_WHITESPACE_RUN + 1},}}", text):
        return "excessive_whitespace"
    if SUSPICIOUS_TOKEN.search(text):
        return "code_like_tokens"
    if len(_script_families(text)) > MAX_SCRIPT_FAMILIES:
        return "excessive_script_switching"

    visible = [character for character in text if not character.isspace()]
    if visible:
        symbols = sum(
            unicodedata.category(character).startswith(("S", "P")) for character in visible
        )
        if symbols / len(visible) > 0.25:
            return "excessive_symbols"
    return None


class LLMOutputGuard(FrameProcessor):
    """Validate complete streamed sentences before allowing them to reach TTS."""

    def __init__(self) -> None:
        super().__init__()
        self._pending = ""
        self._emitted_characters = 0
        self._emitted_text = False
        self._rejected = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMFullResponseStartFrame):
            self._reset()
            await self.push_frame(frame, direction)
        elif isinstance(frame, LLMTextFrame):
            await self._consume(frame.text)
        elif isinstance(frame, LLMFullResponseEndFrame):
            await self._flush()
            if self._rejected and not self._emitted_text:
                await self.push_frame(LLMTextFrame(SAFE_FALLBACK))
            await self.push_frame(frame, direction)
            self._reset()
        elif isinstance(frame, InterruptionFrame):
            self._reset()
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)

    async def _consume(self, text: str) -> None:
        if self._rejected:
            return
        self._pending += text
        if len(self._pending) > MAX_PENDING_CHARACTERS:
            self._reject("unterminated_long_segment")
            return

        start = 0
        for match in SENTENCE_BOUNDARY.finditer(self._pending):
            segment = self._pending[start : match.start()].strip()
            if segment and not await self._emit_if_safe(segment):
                return
            start = match.end()
        self._pending = self._pending[start:]

    async def _flush(self) -> None:
        if self._rejected:
            return
        segment = self._pending.strip()
        self._pending = ""
        if segment:
            await self._emit_if_safe(segment)

    async def _emit_if_safe(self, text: str) -> bool:
        reason = rejection_reason(text)
        if reason:
            self._reject(reason)
            return False
        if self._emitted_characters + len(text) > MAX_RESPONSE_CHARACTERS:
            self._reject("response_too_long")
            return False

        suffix = " " if text[-1] in ".!?" else ""
        await self.push_frame(LLMTextFrame(f"{text}{suffix}"))
        self._emitted_characters += len(text)
        self._emitted_text = True
        return True

    def _reject(self, reason: str) -> None:
        self._rejected = True
        logger.warning(
            "llm.output_rejected",
            reason=reason,
            pending_characters=len(self._pending),
            emitted_characters=self._emitted_characters,
        )
        self._pending = ""

    def _reset(self) -> None:
        self._pending = ""
        self._emitted_characters = 0
        self._emitted_text = False
        self._rejected = False
