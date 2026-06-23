from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.logging import get_logger
from app.core.settings import Settings

logger = get_logger(__name__)

DATASET_PATH = Path(__file__).parents[1] / "data" / "help_center.json"
VECTOR_SIZE = 1536


@dataclass(frozen=True)
class HelpCenterEntry:
    id: int
    question: str
    answer: str
    score: float | None = None

    @property
    def embedding_text(self) -> str:
        return f"Question: {self.question}\nAnswer: {self.answer}"


class HelpCenterService:
    """Small Qdrant-backed help center using OpenAI API embeddings.

    API embeddings keep RAM usage low on the shared t3.medium; no local model is
    loaded into the backend or Qdrant containers.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        qdrant_client: httpx.AsyncClient | None = None,
        openai_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._qdrant = qdrant_client or httpx.AsyncClient(
            base_url=settings.QDRANT_URL, timeout=10.0
        )
        self._openai = openai_client or httpx.AsyncClient(
            base_url="https://api.openai.com/v1", timeout=30.0
        )

    async def close(self) -> None:
        await self._qdrant.aclose()
        await self._openai.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        stop=stop_after_attempt(8),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        reraise=True,
    )
    async def seed_if_needed(self) -> None:
        entries = self._load_entries()
        collection_exists = await self._collection_exists()
        if not collection_exists:
            await self._create_collection()

        count = await self._point_count()
        if count >= len(entries):
            logger.info(
                "help_center.seed_already_present",
                collection=self._settings.QDRANT_COLLECTION,
                points=count,
            )
            return

        embeddings = await self._embed([entry.embedding_text for entry in entries])
        points = [
            {
                "id": entry.id,
                "vector": vector,
                "payload": {
                    "question": entry.question,
                    "answer": entry.answer,
                },
            }
            for entry, vector in zip(entries, embeddings, strict=True)
        ]
        response = await self._qdrant.put(
            f"/collections/{self._settings.QDRANT_COLLECTION}/points",
            params={"wait": "true"},
            json={"points": points},
        )
        response.raise_for_status()
        logger.info(
            "help_center.seed_completed",
            collection=self._settings.QDRANT_COLLECTION,
            points=len(points),
            previous_points=count,
        )

    async def retrieve(self, question: str, *, limit: int = 3) -> list[HelpCenterEntry]:
        vector = (await self._embed([question]))[0]
        response = await self._qdrant.post(
            f"/collections/{self._settings.QDRANT_COLLECTION}/points/query",
            json={
                "query": vector,
                "limit": limit,
                "with_payload": True,
            },
        )
        response.raise_for_status()
        points = response.json()["result"]["points"]
        entries = [
            HelpCenterEntry(
                id=int(point["id"]),
                question=str(point["payload"]["question"]),
                answer=str(point["payload"]["answer"]),
                score=float(point["score"]),
            )
            for point in points
        ]
        logger.info(
            "help_center.retrieved",
            question=question,
            top_k=[
                {
                    "id": entry.id,
                    "question": entry.question,
                    "answer": entry.answer,
                    "score": round(entry.score or 0.0, 4),
                }
                for entry in entries
            ],
        )
        return entries

    def _load_entries(self) -> list[HelpCenterEntry]:
        raw: list[dict[str, Any]] = json.loads(DATASET_PATH.read_text())
        return [HelpCenterEntry(**item) for item in raw]

    async def _collection_exists(self) -> bool:
        response = await self._qdrant.get(f"/collections/{self._settings.QDRANT_COLLECTION}")
        if response.status_code == httpx.codes.NOT_FOUND:
            return False
        response.raise_for_status()
        return True

    async def _create_collection(self) -> None:
        response = await self._qdrant.put(
            f"/collections/{self._settings.QDRANT_COLLECTION}",
            json={"vectors": {"size": VECTOR_SIZE, "distance": "Cosine"}},
        )
        response.raise_for_status()
        logger.info(
            "help_center.collection_created",
            collection=self._settings.QDRANT_COLLECTION,
            vector_size=VECTOR_SIZE,
        )

    async def _point_count(self) -> int:
        response = await self._qdrant.post(
            f"/collections/{self._settings.QDRANT_COLLECTION}/points/count",
            json={"exact": True},
        )
        response.raise_for_status()
        return int(response.json()["result"]["count"])

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._openai.post(
            "/embeddings",
            headers={"Authorization": f"Bearer {self._secret('OPENAI_API_KEY')}"},
            json={
                "model": self._settings.OPENAI_EMBEDDING_MODEL,
                "input": texts,
                "encoding_format": "float",
                "dimensions": VECTOR_SIZE,
            },
        )
        response.raise_for_status()
        data = sorted(response.json()["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in data]

    def _secret(self, name: str) -> str:
        value = self._settings.require(name)
        return value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)
