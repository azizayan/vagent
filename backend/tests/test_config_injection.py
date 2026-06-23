from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app import bot
from app.core.settings import Settings
from app.schemas.config import SessionConfig


@pytest.mark.asyncio
async def test_run_bot_injects_session_config(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeDailyParams:
        def __init__(self, **kwargs: Any):
            captured["daily_params"] = kwargs

    class FakeTransport:
        def __init__(self, room_url: str, token: str, bot_name: str, params: FakeDailyParams):
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
        @dataclass
        class Settings:
            model: str
            system_instruction: str
            temperature: float
            max_tokens: int

        def __init__(self, **kwargs: Any):
            captured["llm"] = self
            captured["llm_kwargs"] = kwargs

    class FakeGenerationConfig:
        def __init__(self, **kwargs: Any):
            self.values = kwargs

    class FakeTTS:
        @dataclass
        class Settings:
            voice: str
            generation_config: FakeGenerationConfig

        def __init__(self, **kwargs: Any):
            captured["tts"] = self
            captured["tts_kwargs"] = kwargs

    class FakeVADParams:
        def __init__(self, **kwargs: Any):
            captured["vad_params"] = kwargs

    class FakeVAD:
        def __init__(self, **kwargs: Any):
            captured["vad"] = kwargs

    class FakeContext:
        def __init__(self):
            self.messages: list[dict[str, str]] = []
            captured["context"] = self

        def add_message(self, message: dict[str, str]) -> None:
            self.messages.append(message)

    class FakeUserAggregatorParams:
        def __init__(self, **kwargs: Any):
            captured["user_aggregator_params"] = kwargs

    class FakeUserAggregator:
        def __init__(self) -> None:
            self.handlers: dict[str, Any] = {}

        def event_handler(self, name: str):
            def register(handler: Any) -> Any:
                self.handlers[name] = handler
                return handler

            return register

    class FakeAggregatorPair:
        def __new__(cls, context: FakeContext, **kwargs: Any) -> tuple[FakeUserAggregator, str]:
            aggregator = FakeUserAggregator()
            captured["user_aggregator"] = aggregator
            return aggregator, "assistant-aggregator"

    class FakePipeline:
        def __init__(self, processors: list[Any]):
            captured["processors"] = processors

    class FakeRetriever:
        def __init__(self, service: object, **kwargs: Any):
            captured["retriever"] = (service, kwargs)

    class FakePipelineParams:
        def __init__(self, **kwargs: Any):
            captured["pipeline_params"] = kwargs

    class FakeTask:
        def __init__(self, pipeline: FakePipeline, params: FakePipelineParams):
            captured["task"] = self
            self.queued: list[Any] = []

        async def queue_frames(self, frames: list[Any]) -> None:
            self.queued.extend(frames)

        async def stop_when_done(self) -> None:
            captured["stopped"] = True

    class FakeRunner:
        async def run(self, task: FakeTask) -> None:
            transport = captured["fake_transport"]
            await transport.handlers["on_first_participant_joined"](
                transport, {"id": "participant-1"}
            )

    def create_transport(*args: Any, **kwargs: Any) -> FakeTransport:
        transport = FakeTransport(*args, **kwargs)
        captured["fake_transport"] = transport
        return transport

    monkeypatch.setattr(bot, "DailyParams", FakeDailyParams)
    monkeypatch.setattr(bot, "DailyTransport", create_transport)
    monkeypatch.setattr(bot, "DeepgramSTTService", FakeSTT)
    monkeypatch.setattr(bot, "OpenAILLMService", FakeLLM)
    monkeypatch.setattr(bot, "GenerationConfig", FakeGenerationConfig)
    monkeypatch.setattr(bot, "CartesiaTTSService", FakeTTS)
    monkeypatch.setattr(bot, "VADParams", FakeVADParams)
    monkeypatch.setattr(bot, "SileroVADAnalyzer", FakeVAD)
    monkeypatch.setattr(bot, "LLMContext", FakeContext)
    monkeypatch.setattr(bot, "LLMUserAggregatorParams", FakeUserAggregatorParams)
    monkeypatch.setattr(bot, "LLMContextAggregatorPair", FakeAggregatorPair)
    monkeypatch.setattr(bot, "HelpCenterRetriever", FakeRetriever)
    monkeypatch.setattr(bot, "Pipeline", FakePipeline)
    monkeypatch.setattr(bot, "PipelineParams", FakePipelineParams)
    monkeypatch.setattr(bot, "PipelineTask", FakeTask)
    monkeypatch.setattr(bot, "PipelineRunner", FakeRunner)

    settings = Settings(
        OPENAI_API_KEY="openai",
        OPENAI_MODEL="gpt-test",
        DEEPGRAM_API_KEY="deepgram",
        CARTESIA_API_KEY="cartesia",
    )
    config = SessionConfig(
        system_prompt="Be concise.",
        temperature=0.3,
        max_tokens=88,
        stt_temperature=0.2,
        tts_voice_id="voice-123",
        tts_speed=1.2,
        tts_temperature=0.4,
        interruptibility_pct=70,
    )
    help_center = object()

    await bot.run_bot(
        settings=settings,
        room_url="https://test.daily.co/freya-session",
        token="bot-token",
        config=config,
        session_id="session-1",
        help_center=help_center,  # type: ignore[arg-type]
    )

    assert captured["transport"][:3] == (
        "https://test.daily.co/freya-session",
        "bot-token",
        "Freya",
    )
    assert captured["llm_kwargs"]["settings"] == FakeLLM.Settings(
        model="gpt-test",
        system_instruction="Be concise.",
        temperature=0.3,
        max_tokens=88,
    )
    assert captured["tts_kwargs"]["settings"].voice == "voice-123"
    assert captured["tts_kwargs"]["settings"].generation_config.values == {"speed": 1.2}
    assert captured["user_aggregator_params"]["user_idle_timeout"] == 60
    assert captured["context"].messages == [{"role": "user", "content": bot.GREETING_INSTRUCTION}]
    assert captured["retriever"] == (
        help_center,
        {"ignored_questions": {bot.GREETING_INSTRUCTION}},
    )
    assert captured["processors"][4].__class__ is FakeRetriever
    assert len(captured["task"].queued) == 1
    assert set(captured["user_aggregator"].handlers) == {
        "on_user_turn_idle",
        "on_user_turn_started",
    }
