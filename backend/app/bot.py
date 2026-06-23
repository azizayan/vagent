from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import suppress
from typing import Any

import aiohttp
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.transports.daily.utils import DailyRESTHelper, DailyRoomParams

from app.core.logging import configure_logging, get_logger
from app.core.settings import Settings, get_settings

ROOM_NAME = "freya-ch1"
BOT_NAME = "Freya"
SYSTEM_PROMPT = "You are a terse, slightly grumpy pirate. Keep replies under two sentences."
GREETING_INSTRUCTION = "Greet the participant now in character."
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_TEMPERATURE = 0.7
OPENAI_MAX_TOKENS = 120
CARTESIA_VOICE_ID = "71a7ad14-091c-4e8e-a314-022ece01c121"

logger = get_logger(__name__)


def _secret(settings: Settings, name: str) -> str:
    value = settings.require(name)
    return value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)


def _room_url(settings: Settings) -> str:
    domain = str(settings.require("DAILY_DOMAIN")).strip()
    domain = domain.removeprefix("https://").removeprefix("http://").rstrip("/")
    if not domain.endswith(".daily.co"):
        domain = f"{domain}.daily.co"
    return f"https://{domain}/{ROOM_NAME}"


async def _create_room_and_token(settings: Settings) -> tuple[str, str]:
    expected_url = _room_url(settings)
    async with aiohttp.ClientSession() as session:
        helper = DailyRESTHelper(
            daily_api_key=_secret(settings, "DAILY_API_KEY"),
            daily_api_url="https://api.daily.co/v1",
            aiohttp_session=session,
        )
        try:
            room = await helper.get_room_from_url(expected_url)
        except Exception:
            room = await helper.create_room(DailyRoomParams(name=ROOM_NAME, privacy="public"))

        token = await helper.get_token(room.url, owner=True)
        return room.url, token


async def run_bot(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    room_url, token = await _create_room_and_token(settings)

    logger.info("bot.room_ready", room_url=room_url)

    transport = DailyTransport(
        room_url,
        token,
        BOT_NAME,
        params=DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    )
    stt = DeepgramSTTService(api_key=_secret(settings, "DEEPGRAM_API_KEY"))
    llm = OpenAILLMService(
        api_key=_secret(settings, "OPENAI_API_KEY"),
        model=OPENAI_MODEL,
        params=OpenAILLMService.InputParams(
            temperature=OPENAI_TEMPERATURE,
            max_tokens=OPENAI_MAX_TOKENS,
        ),
    )
    tts = CartesiaTTSService(
        api_key=_secret(settings, "CARTESIA_API_KEY"),
        settings=CartesiaTTSService.Settings(
            voice=CARTESIA_VOICE_ID,
        ),
    )

    context = LLMContext([{"role": "system", "content": SYSTEM_PROMPT}])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams()),
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )
    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
    )

    @transport.event_handler("on_first_participant_joined")  # type: ignore[untyped-decorator]
    async def on_first_participant_joined(
        transport: DailyTransport, participant: Mapping[str, Any]
    ) -> None:
        logger.info("bot.participant_joined", participant_id=participant.get("id"))
        context.add_message({"role": "user", "content": GREETING_INSTRUCTION})
        await task.queue_frames([LLMRunFrame()])

    runner = PipelineRunner()
    await runner.run(task)


async def _main() -> None:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    await run_bot(settings)


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        asyncio.run(_main())
