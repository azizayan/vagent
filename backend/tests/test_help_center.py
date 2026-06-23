from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from pipecat.frames.frames import LLMContextFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection

from app.core.settings import Settings
from app.pipeline.processors.help_center_retriever import HelpCenterRetriever
from app.services.help_center import HelpCenterEntry, HelpCenterService


@pytest.mark.asyncio
async def test_seed_is_idempotent_and_uses_deterministic_points() -> None:
    collection_exists = False
    points: dict[int, dict[str, Any]] = {}
    embedding_calls = 0

    def qdrant_handler(request: httpx.Request) -> httpx.Response:
        nonlocal collection_exists
        if request.method == "GET" and request.url.path.endswith("/freya_help_center"):
            return httpx.Response(200 if collection_exists else 404, json={})
        if request.method == "PUT" and request.url.path.endswith("/freya_help_center"):
            collection_exists = True
            return httpx.Response(200, json={"result": True})
        if request.url.path.endswith("/points/count"):
            return httpx.Response(200, json={"result": {"count": len(points)}})
        if request.method == "PUT" and request.url.path.endswith("/points"):
            for point in request.extensions["json"]["points"]:
                points[point["id"]] = point
            return httpx.Response(200, json={"result": {"status": "completed"}})
        raise AssertionError(f"Unexpected Qdrant request: {request.method} {request.url}")

    def openai_handler(request: httpx.Request) -> httpx.Response:
        nonlocal embedding_calls
        embedding_calls += 1
        inputs = request.extensions["json"]["input"]
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": index, "embedding": [float(index)] * 1536}
                    for index, _ in enumerate(inputs)
                ]
            },
        )

    qdrant = _json_client("http://qdrant:6333", qdrant_handler)
    openai = _json_client("https://api.openai.com/v1", openai_handler)
    service = HelpCenterService(
        Settings(OPENAI_API_KEY="test"),
        qdrant_client=qdrant,
        openai_client=openai,
    )

    await service.seed_if_needed()
    first_ids = set(points)
    await service.seed_if_needed()

    assert len(points) == 18
    assert set(points) == first_ids
    assert points[1]["payload"]["answer"] == "Freya accepts returns within 37 days of delivery."
    assert embedding_calls == 1
    await service.close()


@pytest.mark.asyncio
async def test_retriever_injects_top_three_before_latest_user_without_mutating_history() -> None:
    service = AsyncMock(spec=HelpCenterService)
    service.retrieve.return_value = [
        HelpCenterEntry(
            id=1,
            question="How long is Freya's return window?",
            answer="Freya accepts returns within 37 days of delivery.",
            score=0.98,
        ),
        HelpCenterEntry(id=2, question="Refund timing?", answer="4 business days.", score=0.7),
        HelpCenterEntry(
            id=3, question="Start a return?", answer="Use the Returns page.", score=0.6
        ),
    ]
    original = LLMContext(
        messages=[
            {"role": "assistant", "content": "How can I help?"},
            {"role": "user", "content": "What is the return window?"},
        ]
    )
    retriever = HelpCenterRetriever(service)
    output: list[LLMContextFrame] = []

    async def capture(frame: object, direction: FrameDirection) -> None:
        assert isinstance(frame, LLMContextFrame)
        output.append(frame)

    retriever.push_frame = capture  # type: ignore[method-assign]
    await retriever.process_frame(LLMContextFrame(original), FrameDirection.DOWNSTREAM)

    service.retrieve.assert_awaited_once_with("What is the return window?", limit=3)
    assert len(original.messages) == 2
    assert len(output[0].context.messages) == 3
    assert output[0].context.messages[-2]["role"] == "system"
    assert "37 days" in str(output[0].context.messages[-2]["content"])
    assert output[0].context.messages[-1]["content"] == "What is the return window?"


def _json_client(base_url: str, handler: Any) -> httpx.AsyncClient:
    async def add_json_extension(request: httpx.Request) -> httpx.Response:
        request.extensions["json"] = json.loads(request.content) if request.content else None
        return handler(request)

    return httpx.AsyncClient(
        base_url=base_url,
        transport=httpx.MockTransport(add_json_extension),
    )
