# ruff: noqa: RUF001

from __future__ import annotations

from typing import Any

import pytest
from pipecat.frames.frames import (
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.processors.frame_processor import FrameDirection

from app.pipeline.processors.output_guard import (
    SAFE_FALLBACK,
    LLMOutputGuard,
    rejection_reason,
)

TOKEN_SOUP = (
    "ప్రSTEMdelta 답합니다екса wordenty refusKer széals сондай sz olmaq_CONNECTED "
    'marquebreak_DSTamped assuming alternесті Rpc사 драмusteોખ្ធ"use convencional '
    "메Margin decidedly motionsуч profondeur"
)


def test_rejection_reason_accepts_normal_multilingual_text() -> None:
    assert rejection_reason("Hello! How can I help you today?") is None
    assert rejection_reason("Merhaba! Bugün size nasıl yardımcı olabilirim?") is None
    assert rejection_reason("こんにちは。今日はどうしましたか？") is None


def test_rejection_reason_rejects_token_soup() -> None:
    assert rejection_reason(TOKEN_SOUP) is not None


@pytest.mark.asyncio
async def test_guard_streams_valid_sentences() -> None:
    frames = await run_guard(
        LLMFullResponseStartFrame(),
        LLMTextFrame("Hello! "),
        LLMTextFrame("How can I help?"),
        LLMFullResponseEndFrame(),
    )

    assert text_values(frames) == ["Hello! ", "How can I help? "]


@pytest.mark.asyncio
async def test_guard_replaces_entire_invalid_response() -> None:
    frames = await run_guard(
        LLMFullResponseStartFrame(),
        LLMTextFrame(TOKEN_SOUP),
        LLMFullResponseEndFrame(),
    )

    assert text_values(frames) == [SAFE_FALLBACK]


@pytest.mark.asyncio
async def test_guard_drops_invalid_tail_after_valid_sentence() -> None:
    frames = await run_guard(
        LLMFullResponseStartFrame(),
        LLMTextFrame("Hello there! "),
        LLMTextFrame(TOKEN_SOUP),
        LLMFullResponseEndFrame(),
    )

    assert text_values(frames) == ["Hello there! "]


async def run_guard(*input_frames: Frame) -> list[Frame]:
    guard = LLMOutputGuard()
    output: list[Frame] = []

    async def capture(frame: Frame, direction: FrameDirection = FrameDirection.DOWNSTREAM) -> None:
        output.append(frame)

    guard.push_frame = capture  # type: ignore[method-assign]
    for frame in input_frames:
        await guard.process_frame(frame, FrameDirection.DOWNSTREAM)
    return output


def text_values(frames: list[Any]) -> list[str]:
    return [frame.text for frame in frames if isinstance(frame, LLMTextFrame)]
