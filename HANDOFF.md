# HANDOFF — Freya Voice Agent

Read with [`AGENTS.md`](./AGENTS.md) and [`todo.md`](./todo.md) before changing
code.

Last updated: June 23, 2026 — frontend/backend session integration complete and
verified locally with real vendor credentials.

## Current status

| Phase | State |
| --- | --- |
| Repo + production Compose scaffold | done |
| CH1 voice pipeline | done |
| Session API + configurable agent startup | done |
| Basic Next.js session configuration UI | done |
| State/latency/interruption data-channel dashboard | pending |
| Qdrant RAG or OpenTelemetry add-on | pending |
| Security pass | pending |
| EC2 + Cloudflare deployment | existing deployment; redeploy current changes |
| DEPLOY.md finalization | pending |
| Submission package | pending |

The local stack boots with:

```bash
docker compose up -d --build
```

Both services are healthy, and the same-origin backend proxy responds at:

```text
http://localhost:3000/api/health
```

## Implemented session flow

The old hardcoded public Daily room has been removed.

1. The frontend submits `SessionConfig` to `POST /api/session`.
2. Next.js rewrites `/api/*` to `http://backend:8000/*`.
3. The backend validates and sanitizes the config.
4. `DailyService` creates a private per-session room and separate user/bot
   meeting tokens.
5. `AgentRunner` starts one Pipecat task for that room.
6. The frontend joins Daily with the returned `{roomUrl, token, sessionId}`.

Relevant files:

```text
backend/app/api/session.py
backend/app/schemas/config.py
backend/app/services/daily.py
backend/app/services/agent_runner.py
backend/app/bot.py
frontend/app/page.tsx
frontend/types/contract.ts
frontend/lib/api.ts
frontend/lib/daily.ts
```

Missing vendor credentials are checked before Daily room creation. Daily calls
use bounded exponential retries through `tenacity`.

## Runtime configuration

The current UI controls:

- system prompt
- OpenAI temperature
- OpenAI max tokens
- Cartesia voice ID
- Cartesia speed
- interruptibility percentage

`stt_temperature` and `tts_temperature` remain in the shared contract, but
Pipecat 1.0.0 does not expose corresponding Deepgram/Cartesia settings. Do not
claim those two values are applied unless the pinned SDK changes.

The system prompt is injected through
`OpenAILLMService.Settings(system_instruction=...)`, not appended as a system
message. The automatic greeting is constrained to one short plain-text
sentence.

## Interruptibility semantics

`interruptibility_pct` always means sensitivity, including at `0%`.

- `0%`: least sensitive, but still interruptible by clear sustained speech.
- `100%`: most sensitive.

There is no special zero-percent mute, queue, or interruption-disable behavior.
That experiment was reverted.

`backend/app/pipeline/vad.py` linearly maps the clamped percentage to Pipecat
`VADParams`:

| Percentage | confidence | start_secs | stop_secs | min_volume |
| --- | ---: | ---: | ---: | ---: |
| 0 | 0.85 | 0.30 | 0.80 | 0.60 |
| 50 | 0.65 | 0.175 | 0.475 | 0.475 |
| 100 | 0.45 | 0.05 | 0.15 | 0.35 |

Pipecat logs the resulting values as:

```text
Setting VAD params to: confidence=... start_secs=... stop_secs=... min_volume=...
```

Use:

```bash
docker compose logs -f backend
```

## LLM output guard

`backend/app/pipeline/processors/output_guard.py` sits between OpenAI and
Cartesia:

```text
OpenAILLMService → LLMOutputGuard → CartesiaTTSService
```

It buffers complete streamed sentences and blocks malformed output before TTS,
including excessive script switching, code-like token soup, excessive symbols,
control characters, whitespace runs, and overlong responses. A completely
invalid response is replaced with a short safe fallback. If valid speech was
already emitted, a corrupt tail is dropped.

Rejected output is logged as:

```text
llm.output_rejected
```

Monitor it with:

```bash
docker compose logs -f backend | grep llm.output_rejected
```

## Verification completed

```text
backend pytest: 12 passed
backend ruff check: passed
backend ruff format --check: passed
backend mypy app: passed
frontend lint: passed
frontend typecheck: passed
frontend production build: passed
docker compose backend/frontend: healthy
same-origin /api/health: HTTP 200
real POST /session: HTTP 201
private Daily room + separate tokens: verified
bot Daily join: verified
Deepgram and Cartesia connections: verified
session system prompt and VAD values: verified in runtime logs
```

## Deployment decisions to preserve

1. Keep one `docker-compose.yml` for local and EC2.
2. Keep the frontend in production mode in Compose.
3. Keep `restart: unless-stopped` on every service.
4. Keep the backend internal; browsers use the same-origin `/api` proxy.
5. Keep `NEXT_PUBLIC_API_URL` configurable at frontend build time.
6. Keep secrets only in untracked `.env` files.
7. Cloudflare Tunnel publishes the frontend at `http://localhost:3000`; only
   SSH needs to be open inbound on EC2.
8. Test microphone behavior through HTTPS on EC2.

## Important implementation notes

- Pipecat is pinned to `pipecat-ai==1.0.0`.
- Daily.js is pinned to `@daily-co/daily-js==0.91.0`.
- Backend source is imported from `/srv/app` in the container. If rebuilt code
  appears stale, use `docker compose build --no-cache backend`.
- Changing `.env` does not update existing containers; recreate the affected
  service.
- `NEXT_PUBLIC_API_URL` is baked during `next build`; rebuild the frontend
  after changing it.

## Next work

Implement the remaining observability/dashboard seam:

1. Add `backend/app/schemas/events.py`.
2. Add deterministic state, latency, and interruption processors with a shared
   fake-clock-friendly state model.
3. Send the discriminated event union over the Daily data channel.
4. Mirror the event contract in `frontend/types/contract.ts`.
5. Add `useDataChannel` and the LISTENING/THINKING/SPEAKING dashboard.
6. Add the rubric-required backend and frontend tests.
7. Redeploy current session-integration changes to EC2 and verify through the
   Cloudflare HTTPS hostname.

Open product decision: choose Qdrant RAG or OpenTelemetry for the required
add-on phase.
