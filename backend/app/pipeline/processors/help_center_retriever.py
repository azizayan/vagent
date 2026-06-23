from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from pipecat.frames.frames import Frame, LLMContextFrame
from pipecat.processors.aggregators.llm_context import LLMContext, LLMContextMessage
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from app.core.logging import get_logger
from app.services.help_center import HelpCenterEntry, HelpCenterService

HELP_CENTER_PREFIX = (
    "Use this help-center information if it is relevant to the user's question. "
    "Treat it as the authoritative source. If it is not relevant, ignore it.\n\n"
)
logger = get_logger(__name__)


class HelpCenterRetriever(FrameProcessor):
    """Enrich each user LLMContextFrame without mutating conversation history."""

    def __init__(
        self,
        service: HelpCenterService,
        *,
        ignored_questions: set[str] | None = None,
    ) -> None:
        super().__init__()
        self._service = service
        self._ignored_questions = ignored_questions or set()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if not isinstance(frame, LLMContextFrame):
            await self.push_frame(frame, direction)
            return

        messages = list(frame.context.messages)
        question = self._latest_user_text(messages)
        if not question or question in self._ignored_questions:
            await self.push_frame(frame, direction)
            return

        try:
            entries = await self._service.retrieve(question, limit=3)
        except Exception as error:
            logger.warning(
                "help_center.retrieval_failed",
                question=question,
                error_type=type(error).__name__,
                message=str(error),
            )
            await self.push_frame(frame, direction)
            return
        if not entries:
            await self.push_frame(frame, direction)
            return

        injection = cast(
            LLMContextMessage,
            {
                "role": "system",
                "content": HELP_CENTER_PREFIX + self._format_entries(entries),
            },
        )
        messages.insert(len(messages) - 1, injection)
        enriched = LLMContext(
            messages=messages,
            tools=frame.context.tools,
            tool_choice=frame.context.tool_choice,
        )
        await self.push_frame(LLMContextFrame(context=enriched), direction)

    @staticmethod
    def _latest_user_text(messages: Sequence[object]) -> str | None:
        if not messages:
            return None
        message = messages[-1]
        if not isinstance(message, dict) or message.get("role") != "user":
            return None
        content = message.get("content")
        return content.strip() if isinstance(content, str) and content.strip() else None

    @staticmethod
    def _format_entries(entries: list[HelpCenterEntry]) -> str:
        return "\n\n".join(
            f"Help-center question: {entry.question}\nHelp-center answer: {entry.answer}"
            for entry in entries
        )
