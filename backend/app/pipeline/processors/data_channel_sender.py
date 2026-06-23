from __future__ import annotations

from pipecat.frames.frames import Frame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.transports.daily.transport import DailyOutputTransportMessageUrgentFrame

from app.core.logging import get_logger
from app.schemas.events import DataChannelEvent

logger = get_logger(__name__)


class DataChannelSender(FrameProcessor):
    """Serialises DataChannelEvents to JSON and sends them over the Daily data channel.

    Passes every pipeline frame through unchanged. Events are pushed as
    DailyOutputTransportMessageUrgentFrame so they bypass the audio queue and
    are dispatched immediately.
    """

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)

    async def send_event(self, event: DataChannelEvent) -> None:
        payload = event.model_dump()
        msg = DailyOutputTransportMessageUrgentFrame(message=payload)
        await self.push_frame(msg, FrameDirection.DOWNSTREAM)
        logger.debug("data_channel.sent", event_type=event.type)
