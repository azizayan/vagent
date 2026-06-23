from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app import bot
from app.core.settings import Settings


def test_daily_room_url_uses_configured_domain() -> None:
    settings = Settings(DAILY_DOMAIN="freya-test")

    assert bot._room_url(settings) == "https://freya-test.daily.co/freya-ch1"


@pytest.mark.asyncio
async def test_run_bot_wires_hardcoded_ch1_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_create_room_and_token(settings: Settings) -> tuple[str, str]:
        return "https://freya-test.daily.co/freya-ch1", "bot-token"

    class FakeDailyParams:
        def __init__(self, **kwargs: Any):
            captured["daily_params"] = kwargs

    class FakeTransport:
        def __init__(
            self,
            room_url: str,
            token: str,
            bot_name: str,
            params: FakeDailyParams,
        ):
            captured["transport"] = (room_url, token, bot_name, params)
            self.handlers: dict[str, Any] = {}

        def input(self) -> str:
            return "transport-input"

        def output(self) -> str:
            return "transport-output"

        def event_handler(self, name: str):
            def register(handler: Any) -> Any:
                self.handlers[name] = handler
                return handler

            return register

    class FakeSTT:
        def __init__(self, **kwargs: Any):
            captured["stt"] = self
            captured["stt_kwargs"] = kwargs

    class FakeLLM:
        class InputParams:
            def __init__(self, **kwargs: Any):
                self.values = kwargs

        def __init__(self, **kwargs: Any):
            captured["llm"] = self
            captured["llm_kwargs"] = kwargs

    class FakeTTS:
        @dataclass
        class Settings:
            voice: str

        def __init__(self, **kwargs: Any):
            captured["tts"] = self
            captured["tts_kwargs"] = kwargs

    class FakeVADParams:
        pass

    class FakeVAD:
        def __init__(self, **kwargs: Any):
            captured["vad"] = kwargs

    class FakeContext:
        def __init__(self, messages: list[dict[str, str]]):
            self.messages = list(messages)
            captured["context"] = self

        def add_message(self, message: dict[str, str]) -> None:
            self.messages.append(message)

    class FakeUserAggregatorParams:
        def __init__(self, **kwargs: Any):
            captured["user_aggregator_params"] = kwargs

    class FakeAggregatorPair:
        def __new__(cls, context: FakeContext, **kwargs: Any) -> tuple[str, str]:
            captured["aggregator_pair"] = (context, kwargs)
            return "user-aggregator", "assistant-aggregator"

    class FakePipeline:
        def __init__(self, processors: list[Any]):
            captured["processors"] = processors

    class FakePipelineParams:
        def __init__(self, **kwargs: Any):
            captured["pipeline_params"] = kwargs

    class FakeTask:
        def __init__(self, pipeline: FakePipeline, params: FakePipelineParams):
            captured["task"] = self
            self.queued: list[Any] = []

        async def queue_frames(self, frames: list[Any]) -> None:
            self.queued.extend(frames)

        async def queue_frame(self, frame: Any) -> None:
            self.queued.append(frame)

    class FakeRunner:
        async def run(self, task: FakeTask) -> None:
            fake_transport = captured["fake_transport"]
            await fake_transport.handlers["on_first_participant_joined"](
                fake_transport, {"id": "participant-1"}
            )

    original_transport = FakeTransport

    def create_transport(*args: Any, **kwargs: Any) -> FakeTransport:
        transport = original_transport(*args, **kwargs)
        captured["fake_transport"] = transport
        return transport

    monkeypatch.setattr(bot, "_create_room_and_token", fake_create_room_and_token)
    monkeypatch.setattr(bot, "DailyParams", FakeDailyParams)
    monkeypatch.setattr(bot, "DailyTransport", create_transport)
    monkeypatch.setattr(bot, "DeepgramSTTService", FakeSTT)
    monkeypatch.setattr(bot, "OpenAILLMService", FakeLLM)
    monkeypatch.setattr(bot, "CartesiaTTSService", FakeTTS)
    monkeypatch.setattr(bot, "VADParams", FakeVADParams)
    monkeypatch.setattr(bot, "SileroVADAnalyzer", FakeVAD)
    monkeypatch.setattr(bot, "LLMContext", FakeContext)
    monkeypatch.setattr(bot, "LLMUserAggregatorParams", FakeUserAggregatorParams)
    monkeypatch.setattr(bot, "LLMContextAggregatorPair", FakeAggregatorPair)
    monkeypatch.setattr(bot, "Pipeline", FakePipeline)
    monkeypatch.setattr(bot, "PipelineParams", FakePipelineParams)
    monkeypatch.setattr(bot, "PipelineTask", FakeTask)
    monkeypatch.setattr(bot, "PipelineRunner", FakeRunner)

    settings = Settings(
        OPENAI_API_KEY="openai",
        DEEPGRAM_API_KEY="deepgram",
        CARTESIA_API_KEY="cartesia",
        DAILY_API_KEY="daily",
        DAILY_DOMAIN="freya-test",
    )

    await bot.run_bot(settings)

    assert captured["daily_params"] == {
        "audio_in_enabled": True,
        "audio_out_enabled": True,
    }
    assert captured["transport"][:3] == (
        "https://freya-test.daily.co/freya-ch1",
        "bot-token",
        "Freya",
    )
    assert captured["llm_kwargs"]["model"] == "gpt-4o-mini"
    assert captured["llm_kwargs"]["params"].values == {
        "temperature": 0.7,
        "max_tokens": 120,
    }
    assert captured["tts_kwargs"]["settings"].voice == bot.CARTESIA_VOICE_ID
    assert captured["context"].messages == [
        {"role": "system", "content": bot.SYSTEM_PROMPT},
        {"role": "user", "content": bot.GREETING_INSTRUCTION},
    ]
    assert captured["processors"] == [
        "transport-input",
        captured["stt"],
        "user-aggregator",
        captured["llm"],
        captured["tts"],
        "transport-output",
        "assistant-aggregator",
    ]
    assert len(captured["task"].queued) == 1
