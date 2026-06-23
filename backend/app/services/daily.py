from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.errors import UpstreamServiceError
from app.core.settings import Settings


class _RetryableDailyError(Exception):
    pass


@dataclass(frozen=True)
class DailySession:
    room_url: str
    user_token: str
    bot_token: str


class DailyService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client and self._client:
            await self._client.aclose()

    async def create_session(self, session_id: str) -> DailySession:
        if self._client is None:
            api_key = self._settings.require("DAILY_API_KEY")
            secret = (
                api_key.get_secret_value() if hasattr(api_key, "get_secret_value") else str(api_key)
            )
            self._client = httpx.AsyncClient(
                base_url="https://api.daily.co/v1",
                headers={"Authorization": f"Bearer {secret}"},
                timeout=10.0,
            )
        room_name = f"freya-{session_id}"
        room = await self._request(
            "POST",
            "/rooms",
            json={
                "name": room_name,
                "privacy": "private",
                "properties": {"exp": int(time.time()) + 3600},
            },
        )
        room_url = room.get("url")
        if not isinstance(room_url, str) or not room_url:
            raise UpstreamServiceError("Daily room response did not include a URL")

        user_token = await self._create_token(room_name, owner=False)
        bot_token = await self._create_token(room_name, owner=True)
        return DailySession(room_url=room_url, user_token=user_token, bot_token=bot_token)

    async def _create_token(self, room_name: str, *, owner: bool) -> str:
        body = await self._request(
            "POST",
            "/meeting-tokens",
            json={
                "properties": {
                    "room_name": room_name,
                    "is_owner": owner,
                    "exp": int(time.time()) + 3600,
                    "eject_at_token_exp": True,
                }
            },
        )
        token = body.get("token")
        if not isinstance(token, str) or not token:
            raise UpstreamServiceError("Daily token response did not include a token")
        return token

    async def _request(
        self, method: str, path: str, *, json: dict[str, object]
    ) -> dict[str, object]:
        try:
            return await self._request_with_retries(method, path, json=json)
        except (httpx.TransportError, _RetryableDailyError) as exc:
            raise UpstreamServiceError(f"Daily request failed after retries: {exc}") from exc

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, _RetryableDailyError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.25, min=0.25, max=1),
        reraise=True,
    )
    async def _request_with_retries(
        self, method: str, path: str, *, json: dict[str, object]
    ) -> dict[str, object]:
        if self._client is None:
            raise RuntimeError("Daily client was not initialized")
        try:
            response = await self._client.request(method, path, json=json)
            if response.status_code >= 500:
                raise _RetryableDailyError(f"Daily returned HTTP {response.status_code}")
            response.raise_for_status()
            body = response.json()
        except (httpx.TransportError, _RetryableDailyError):
            raise
        except (httpx.HTTPStatusError, ValueError) as exc:
            raise UpstreamServiceError(f"Daily request failed: {exc}") from exc

        if not isinstance(body, dict):
            raise UpstreamServiceError("Daily returned an invalid JSON response")
        return body
