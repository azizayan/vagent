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
from app.pipeline.idle_session import IdleSessionCoordinator
from app.pipeline.processors.data_channel_sender import DataChannelSender
from app.pipeline.processors.help_center_retriever import HelpCenterRetriever
from app.pipeline.processors.output_guard import LLMOutputGuard
from app.pipeline.processors.state_tracker import StateTracker
from app.pipeline.prompts import resolve_system_prompt
from app.pipeline.tts_emotion import temperature_to_emotion
from app.pipeline.vad import map_interruptibility
from app.schemas.config import SessionConfig
from app.services.help_center import HelpCenterService

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
    help_center: HelpCenterService | None = None,
) -> None:
    import time

    settings = settings or get_settings()
    bind_contextvars(session_id=session_id)
    system_prompt, used_default = resolve_system_prompt(config.system_prompt)
    tts_emotion = temperature_to_emotion(config.tts_temperature)
    logger.info(
        "bot.starting",
        room_url=room_url,
        system_prompt_used_default=used_default,
        system_prompt_length=len(system_prompt),
        system_prompt_preview=system_prompt[:120],
        llm_temperature=config.temperature,
        llm_max_tokens=config.max_tokens,
        tts_voice=config.tts_voice_id,
        tts_speed=config.tts_speed,
        tts_temperature=config.tts_temperature,
        tts_emotion_applied=tts_emotion,
        # Deepgram streaming STT has no temperature parameter in its API. We
        # surface the user's value here for traceability — it is intentionally
        # not forwarded to Deepgram, where it would be silently dropped.
        stt_temperature=config.stt_temperature,
        stt_temperature_applied=False,
        interruptibility_pct=config.interruptibility_pct,
    )
    session_start = time.monotonic()

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
            system_instruction=system_prompt,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        ),
    )
    tts = CartesiaTTSService(
        api_key=_secret(settings, "CARTESIA_API_KEY"),
        settings=CartesiaTTSService.Settings(
            voice=config.tts_voice_id,
            generation_config=GenerationConfig(
                speed=config.tts_speed,
                emotion=tts_emotion,
            ),
        ),
    )

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_idle_timeout=settings.USER_IDLE_PROMPT_SECONDS,
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(**map_interruptibility(config.interruptibility_pct))
            ),
        ),
    )

    sender = DataChannelSender()
    tracker = StateTracker(session_start=session_start, on_event=sender.send_event)
    retrieval_processors = (
        [HelpCenterRetriever(help_center, ignored_questions={GREETING_INSTRUCTION})]
        if help_center
        else []
    )

    pipeline = Pipeline(
        [
            transport.input(),
            tracker,
            stt,
            user_aggregator,
            *retrieval_processors,
            llm,
            LLMOutputGuard(),
            tts,
            sender,
            transport.output(),
            assistant_aggregator,
        ]
    )
    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
    )
    idle_session = IdleSessionCoordinator(
        task=task,
        on_event=sender.send_event,
        session_start=session_start,
        prompt_seconds=settings.USER_IDLE_PROMPT_SECONDS,
        close_seconds=settings.SESSION_IDLE_CLOSE_SECONDS,
    )

    @user_aggregator.event_handler("on_user_turn_idle")  # type: ignore[untyped-decorator]
    async def on_user_turn_idle(user_aggregator: object) -> None:
        await idle_session.on_user_turn_idle()

    @user_aggregator.event_handler("on_user_turn_started")  # type: ignore[untyped-decorator]
    async def on_user_turn_started(user_aggregator: object, strategy: object) -> None:
        await idle_session.on_user_turn_started()

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
