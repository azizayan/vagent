from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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
from pipecat.services.cartesia.tts import CartesiaTTSService, GenerationConfig
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.core.logging import get_logger
from app.core.settings import Settings, get_settings
from app.pipeline.processors.output_guard import LLMOutputGuard
from app.pipeline.vad import map_interruptibility
from app.schemas.config import SessionConfig

BOT_NAME = "Freya"
GREETING_INSTRUCTION = (
    "Greet the participant in one short sentence under 20 words. Use plain text only."
)

logger = get_logger(__name__)


def _secret(settings: Settings, name: str) -> str:
    value = settings.require(name)
    return value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)


async def run_bot(
    *,
    room_url: str,
    token: str,
    config: SessionConfig,
    session_id: str,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    bind_contextvars(session_id=session_id)
    logger.info("bot.starting", room_url=room_url)

    transport = DailyTransport(
        room_url,
        token,
        BOT_NAME,
        params=DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    )
    stt = DeepgramSTTService(
        api_key=_secret(settings, "DEEPGRAM_API_KEY"),
    )
    llm = OpenAILLMService(
        api_key=_secret(settings, "OPENAI_API_KEY"),
        settings=OpenAILLMService.Settings(
            model=settings.OPENAI_MODEL,
            system_instruction=config.system_prompt,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        ),
    )
    tts = CartesiaTTSService(
        api_key=_secret(settings, "CARTESIA_API_KEY"),
        settings=CartesiaTTSService.Settings(
            voice=config.tts_voice_id,
            generation_config=GenerationConfig(speed=config.tts_speed),
        ),
    )

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(**map_interruptibility(config.interruptibility_pct))
            ),
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            LLMOutputGuard(),
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
    try:
        await runner.run(task)
    finally:
        clear_contextvars()
