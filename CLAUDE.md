# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: Freya — An Interruptible Voice Agent

Real-time, interruptible voice agent. Browser captures mic → Daily WebRTC → Pipecat pipeline (VAD → Deepgram STT → OpenAI LLM → Cartesia TTS) → Daily WebRTC → browser speaker. The UI configures the agent before each session and displays live bot state, round-trip latency, and interruption events streamed back over a Daily data channel.

---

## Commands

### Stack
```bash
docker compose up -d --build     # Start everything (production mode)
docker compose logs -f backend   # Tail backend logs
docker compose logs -f frontend  # Tail frontend logs
docker compose down              # Stop
```

### Backend
```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload    # Dev
uv run pytest                           # All tests
uv run pytest tests/test_vad_mapping.py # Single test file
uv run ruff check . && uv run ruff format --check .
uv run mypy app
```

### Frontend
```bash
cd frontend
npm ci
npm run dev          # Local only
npm run build        # Required before `npm start`
npm start            # Production server (what Docker runs)
npm test             # Jest
npm run lint
npm run typecheck    # tsc --noEmit
```

---

## Actual Repository Layout

```
backend/
├── app/
│   ├── main.py                  # FastAPI entrypoint with lifespan (HelpCenterService, AgentRunner, DailyService)
│   ├── bot.py                   # run_bot() — builds and runs the full Pipecat pipeline
│   ├── core/
│   │   ├── settings.py          # pydantic-settings; credentials are optional at load, use settings.require(name) to fail fast
│   │   ├── logging.py
│   │   └── errors.py            # FreyaError, ConfigError — mapped to HTTP by one exception handler in main.py
│   ├── api/
│   │   ├── health.py            # GET /health
│   │   └── session.py           # POST /session → Daily room + token + bot task spawn
│   ├── schemas/
│   │   ├── config.py            # SessionConfig (Pydantic v2) + SessionResponse
│   │   └── events.py            # DataChannelEvent discriminated union (state|latency|interruption|session_ended)
│   ├── services/
│   │   ├── daily.py             # Daily REST client (httpx.AsyncClient)
│   │   ├── agent_runner.py      # spawn/track asyncio tasks for bot sessions
│   │   └── help_center.py       # Qdrant + OpenAI embeddings (text-embedding-3-small)
│   ├── data/
│   │   └── help_center.json     # 18 fake Q&A entries; planted fact: return window is 37 days
│   └── pipeline/
│       ├── idle_session.py      # IdleSessionCoordinator: one reminder → graceful shutdown
│       ├── prompts.py           # DEFAULT_SYSTEM_PROMPT + resolve_system_prompt(raw) → (str, bool)
│       ├── vad.py               # map_interruptibility(pct) → dict[str, float] for VADParams
│       └── processors/
│           ├── state_tracker.py         # FSM + latency timer; emits all bot-state + latency events
│           ├── output_guard.py          # LLMOutputGuard between LLM and TTS; rejects bad responses
│           ├── help_center_retriever.py # Qdrant k=3 lookup; inserts context before user message
│           └── data_channel_sender.py   # serialises events → DailyOutputTransportMessageUrgentFrame
```

```
frontend/
├── app/
│   ├── page.tsx                 # Single page: two-panel layout (config left, live dashboard right)
│   ├── layout.tsx
│   ├── globals.css
│   └── providers.tsx            # QueryClientProvider
├── components/config/
│   └── VoicePicker.tsx          # 5 preset Cartesia voices + required custom voice ID input
├── hooks/
│   └── useDataChannel.ts        # Daily app-message subscriber; reducer drives dashboard state
├── lib/
│   ├── api.ts                   # typed fetch wrapper (reads NEXT_PUBLIC_API_URL)
│   ├── daily.ts                 # createDailyCall / destroyDailyCall wrappers
│   ├── defaults.ts              # DEFAULT_SYSTEM_PROMPT (mirrors backend prompts.py)
│   └── env.ts                   # validates NEXT_PUBLIC_API_URL at module load
└── types/
    └── contract.ts              # mirrors backend schemas (keep in sync with events.py and config.py)
```

---

## Architecture

### Pipeline order (in `bot.py`)
```
transport.input() → StateTracker → STT → user_aggregator →
HelpCenterRetriever → LLM → LLMOutputGuard → TTS →
DataChannelSender → transport.output() → assistant_aggregator
```

- `StateTracker` must be first after transport.input() to observe all frames (including VAD frames).
- `DataChannelSender` must be upstream of `transport.output()` so it can push `DailyOutputTransportMessageUrgentFrame` downstream.
- `LLMOutputGuard` blocks control characters, code tokens, excessive length (>800 chars) — replaced with safe fallback, logged as `llm.output_rejected`.

### HTTP / proxy contract
- Browser calls `/api/*` (same-origin). Next.js rewrites `/api/:path*` → `http://backend:8000/:path*` using `BACKEND_INTERNAL_URL` env var.
- `NEXT_PUBLIC_API_URL` defaults to `/api` and is baked at `next build` time. Rebuild the frontend image after changing it.
- `POST /session` body is `SessionConfig`; returns `{roomUrl, token, sessionId}`.

### Data channel contract
Backend → frontend only (read-only from browser). Defined in `app/schemas/events.py` and **must be kept in sync** with `frontend/types/contract.ts`:
```typescript
type DataChannelEvent =
  | { type: "state";         state: "LISTENING" | "THINKING" | "SPEAKING"; at: number }
  | { type: "latency";       ms: number; at: number }
  | { type: "interruption";  at: number }
  | { type: "session_ended"; reason: "inactivity"; at: number }
```
`at` is ms since session start (monotonic clock on backend). Daily delivers these as `app-message` events. Daily's own RTVI metrics frames (`type: "metrics"`) are filtered by the `KNOWN_TYPES` set in `useDataChannel.ts`.

### Bot state machine (in `state_tracker.py`)
- `UserStoppedSpeakingFrame` → emit THINKING, start latency timer
- First `BotStartedSpeakingFrame` after THINKING → emit SPEAKING, stop timer, emit latency event
- `BotStoppedSpeakingFrame` → emit LISTENING
- `UserStartedSpeakingFrame` while SPEAKING → emit interruption event, then LISTENING

### Inactivity handling (`pipeline/idle_session.py`)
`IdleSessionCoordinator` hooks into `user_aggregator` events:
- After `USER_IDLE_PROMPT_SECONDS` of silence → plays one reminder prompt
- After `SESSION_IDLE_CLOSE_SECONDS` total → emits `session_ended` event and calls `task.stop_when_done()`
- Any user speech resets the coordinator

### Interruptibility mapping (`pipeline/vad.py`)
`map_interruptibility(pct)` linearly interpolates `VADParams` over `[0, 100]`:

| pct | confidence | start_secs | stop_secs | min_volume |
|-----|-----------|------------|-----------|------------|
| 0   | 0.85      | 0.30       | 0.80      | 0.60       |
| 100 | 0.45      | 0.05       | 0.60      | 0.35       |

(`stop_secs` uses a narrow band: 0.80→0.60, intentionally not aggressive.)

### Help-center RAG
- Qdrant `v1.14.1` runs as an internal-only Compose service (no host port). Collection: `freya_help_center`.
- Seeded from `backend/app/data/help_center.json` on startup; subsequent boots log `help_center.seed_already_present`.
- `HelpCenterRetriever` queries with `k=3`, clones the Pipecat `LLMContextFrame`, inserts retrieved text before the latest user message. Does NOT mutate shared conversation history.
- Retrieval failures are fail-open (original context continues to LLM).
- The synthetic greeting instruction is excluded from retrieval via `ignored_questions`.

### Configuration fields (`SessionConfig`)
| Field | Applied | Notes |
|-------|---------|-------|
| `system_prompt` | ✅ | `OpenAILLMService.Settings(system_instruction=...)` |
| `temperature` | ✅ | OpenAI LLM |
| `max_tokens` | ✅ | OpenAI LLM |
| `tts_voice_id` | ✅ | Cartesia voice |
| `tts_speed` | ✅ | `GenerationConfig(speed=...)` |
| `stt_temperature` | ❌ | No param in Pipecat 1.0.0 `DeepgramSTTService`; logged as received |
| `tts_temperature` | ❌ | No param in Pipecat 1.0.0 Cartesia; logged as received |
| `interruptibility_pct` | ✅ | `map_interruptibility()` → `VADParams` |

`system_prompt` empty → `resolve_system_prompt()` returns `DEFAULT_SYSTEM_PROMPT`, logs `system_prompt_used_default=True`. Empty is valid (falls back to default); >4000 chars is a 422 error.

---

## Code conventions

### Backend
- **pydantic-settings**: no `os.getenv` outside `core/settings.py`. Use `settings.require(name)` to fail fast with variable name in error.
- **Structured logging**: `structlog` with JSON output. Bind `session_id` via `structlog.contextvars`. No `print`.
- **Async everywhere**: `httpx.AsyncClient` for Daily REST, never blocking I/O on the event loop.
- **Frame processors** subclass Pipecat's `FrameProcessor`. Observability processors must `push_frame` everything unchanged.
- **Errors**: `core/errors.py` domain exceptions → one `exception_handler` in `main.py`. No raw `HTTPException` from services.
- **Pipecat is pinned to `pipecat-ai==1.0.0`**. Verify parameter names against installed source before adding integrations.
- `DailyOutputTransportMessageUrgentFrame` must be pushed **downstream** (not upstream) to broadcast over the data channel.

### Frontend
- **App Router only**. Server Components by default; interactive leaves are `"use client"`.
- **TanStack Query** for the `/session` POST. Component state is `useState`/`useReducer`.
- **Daily.js** only via `lib/daily.ts` and `hooks/useDataChannel.ts`. Components never import `@daily-co/daily-js` directly.
- **Env access** only via `lib/env.ts`. No bare `process.env` in components.
- **TypeScript strict**: `strict: true`, `noUncheckedIndexedAccess: true`. No `any`.
- Frontend tests use **Jest** (via `next/jest`), not Vitest.

### Changing the data-channel contract
Update all four in one commit: `app/schemas/events.py`, `frontend/types/contract.ts`, `data_channel_sender.py`, and `hooks/useDataChannel.ts`.

---

## Deployment constraints

1. **One `docker-compose.yml`** — same file for local and EC2. No override files.
2. Frontend runs **production mode** (`next build` + `next start` via standalone output). Never `next dev` in Compose.
3. **`restart: unless-stopped`** on every service.
4. **`NEXT_PUBLIC_API_URL=/api`** default — baked at build time; rebuild frontend image after changing.
5. Backend is internal-only (`expose`, not `ports`). Browser reaches it via the Next.js `/api` rewrite.
6. **Mic requires HTTPS** — always test through the Cloudflare tunnel URL, not raw `http://<EC2-IP>:3000`.
7. Clean-boot: `git clone && cp .env.example .env && $EDITOR .env && docker compose up -d` — no other steps.

---

## Required environment variables

See `.env.example`. Key vars:

```
OPENAI_API_KEY=          OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
DEEPGRAM_API_KEY=
CARTESIA_API_KEY=        CARTESIA_DEFAULT_VOICE_ID=
DAILY_API_KEY=           DAILY_DOMAIN=
NEXT_PUBLIC_API_URL=     # Default /api works with docker-compose; override for separate tunnel
QDRANT_URL=              # Default http://qdrant:6333
USER_IDLE_PROMPT_SECONDS=60    SESSION_IDLE_CLOSE_SECONDS=300
```

SESSION_IDLE_CLOSE_SECONDS must be > USER_IDLE_PROMPT_SECONDS (validated at startup).

---

## Test files

**Backend** (`uv run pytest`):
- `test_health.py`, `test_session.py` — HTTP surface
- `test_vad_mapping.py` — boundary (0/50/100%) + monotonicity
- `test_config_injection.py` — SessionConfig → service params plumbing
- `test_output_guard.py` — LLMOutputGuard rejection cases
- `test_help_center.py` — Qdrant retrieval (mocked)
- `test_state_transitions.py` — synthetic frame sequences → FSM assertions
- `test_latency.py` — fake clock, ms between UserStopped → BotStarted
- `test_interruption.py` — UserStarted while SPEAKING → one interruption + LISTENING
- `test_idle_session.py` — IdleSessionCoordinator timing

**Frontend** (`npm test`):
- `tests/useDataChannel.test.ts` — reducer: state/latency/interruption/session_ended sequences
- `tests/dashboard.test.tsx` — state badge, latency formatting, interruption list
- `tests/config-form.test.tsx` — required fields, slider bounds, voice picker
- `tests/session-inactivity.test.tsx` — inactivity notice display
