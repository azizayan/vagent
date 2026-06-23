# AGENTS.md

This file provides guidance to coding agents when working with code in this repository.

## Project: Freya — An Interruptible Voice Agent

Real-time, interruptible voice agent. Browser captures mic → Daily WebRTC → Pipecat pipeline (VAD → Deepgram STT → OpenAI LLM → Cartesia TTS) → Daily WebRTC → browser speaker. The UI configures the agent before each session and displays live bot state, round-trip latency, and interruption events streamed back over a Daily data channel.

This codebase is being built from scratch. Treat the structure below as the target architecture — implement it as you go; do not retrofit a different layout.

---

## Repository Layout

```
/
├── frontend/                    # Next.js App Router (TypeScript)
├── backend/                     # Python + Pipecat
├── docker-compose.yml           # Single file — identical local and EC2
├── .env.example                 # All required vars, no secrets
├── DEPLOY.md                    # One-page deployment guide
└── README.md                    # Top-level overview + quickstart
```

### Backend layout (`backend/`)

```
backend/
├── app/
│   ├── main.py                  # FastAPI entrypoint, lifespan, route mounting
│   ├── core/
│   │   ├── settings.py          # pydantic-settings: env-driven config
│   │   ├── logging.py           # structlog / JSON logging setup
│   │   └── errors.py            # exception types + handlers
│   ├── api/
│   │   ├── health.py            # GET /health
│   │   └── session.py           # POST /session → Daily room + token + agent spawn
│   ├── schemas/
│   │   ├── config.py            # SessionConfig (LLM/STT/TTS/interruptibility)
│   │   └── events.py            # DataChannelEvent union (state/latency/interruption)
│   ├── services/
│   │   ├── daily.py             # Daily REST client (rooms, tokens)
│   │   └── agent_runner.py      # spawn/track Pipecat agent processes/tasks
│   └── pipeline/
│       ├── factory.py           # build_pipeline(config) → Pipeline
│       ├── vad.py               # interruptibility% → VAD params mapping
│       ├── processors/
│       │   ├── state_tracker.py        # LISTENING/THINKING/SPEAKING FSM
│       │   ├── latency_tracker.py      # VAD-stop → first bot audio (ms)
│       │   ├── interruption_detector.py
│       │   └── data_channel_sender.py  # serialize events → Daily data channel
│       └── prompts.py           # default system prompt, sanitization
├── tests/
│   ├── test_config_injection.py
│   ├── test_vad_mapping.py
│   ├── test_state_transitions.py
│   ├── test_latency.py
│   └── test_interruption.py
├── pyproject.toml               # uv or poetry; pinned versions
├── Dockerfile
└── .dockerignore
```

### Frontend layout (`frontend/`)

```
frontend/
├── app/
│   ├── layout.tsx
│   ├── page.tsx                 # Config form + "Start session" CTA
│   └── session/[id]/page.tsx    # Live voice + dashboard
├── components/
│   ├── config/                  # SystemPromptTextarea, SliderField, VoicePicker
│   ├── voice/                   # DailyProvider, AudioStage, MicButton
│   └── dashboard/               # BotStateBadge, LatencyMeter, InterruptionLog
├── hooks/
│   ├── useDailyCall.ts          # join/leave, track state
│   ├── useDataChannel.ts        # subscribe to backend events, expose typed state
│   └── useSessionConfig.ts      # form state + zod validation
├── lib/
│   ├── api.ts                   # typed fetch wrapper around NEXT_PUBLIC_API_URL
│   ├── daily.ts                 # Daily.js thin wrapper
│   └── env.ts                   # client-side env access, throws on missing
├── types/
│   └── contract.ts              # mirrors backend schemas (kept in sync manually)
├── tests/                       # Vitest + React Testing Library
├── next.config.ts
├── tsconfig.json
├── package.json
└── Dockerfile
```

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
uv sync                                 # or: pip install -e .
uv run uvicorn app.main:app --reload    # Dev
uv run pytest                           # All tests
uv run pytest tests/test_latency.py -k "vad_stop"   # Single test
uv run ruff check . && uv run ruff format --check . # Lint + format
uv run mypy app                         # Type-check
```

### Frontend

```bash
cd frontend
npm ci
npm run dev          # Local only
npm run build        # Required before `npm start`
npm start            # Production server (this is what Docker runs)
npm test             # Vitest
npm run lint
npm run typecheck    # tsc --noEmit
```

---

## Architecture

### Pipeline

```
Daily transport → VAD → Deepgram STT → OpenAI LLM → Cartesia TTS → Daily transport
                  └────── observed by: StateTracker, LatencyTracker, InterruptionDetector ──┘
                                              │
                                              └→ DataChannelSender → Daily data channel
```

### HTTP contract

- `GET /health` — liveness; returns `{status, version}`. Cheap, no upstream calls.
- `POST /session` — body is `SessionConfig`; returns `{roomUrl, token, sessionId}`. Side effect: spawns a Pipecat agent bound to that room.

The frontend **never** speaks to OpenAI/Deepgram/Cartesia directly. All third-party credentials live in the backend only.

### Data channel contract (Daily)

The backend pushes typed JSON messages. Mirror the discriminated union in both `app/schemas/events.py` and `types/contract.ts`:

```ts
type DataChannelEvent =
  | { type: "state"; state: "LISTENING" | "THINKING" | "SPEAKING"; at: number }
  | { type: "latency"; ms: number; at: number }
  | { type: "interruption"; at: number };
```

`at` is `performance.now()`-style ms since session start, set by the backend. Keep the channel write-only from backend → frontend.

### Bot state machine

THINKING is **not** a native Pipecat state. Implement it explicitly:

- `UserStoppedSpeakingFrame` → emit `THINKING` (start latency timer).
- First `BotStartedSpeakingFrame` after that → emit `SPEAKING` (stop latency timer, send `latency` event).
- `BotStoppedSpeakingFrame` → emit `LISTENING`.
- `UserStartedSpeakingFrame` while `SPEAKING` → emit `interruption` event, then `LISTENING`.

The latency anchors (`UserStoppedSpeakingFrame` → first `BotStartedSpeakingFrame`) are the same anchors as start-of-THINKING / end-of-THINKING. Use one shared clock — do not measure them twice.

### Configuration injection

1. Frontend submits `SessionConfig` to `POST /session`.
2. Backend validates with Pydantic, sanitizes the system prompt (strip control chars, length cap, no role-injection markers).
3. `pipeline.factory.build_pipeline(config)` constructs services with config baked in — system prompt and temperature go through Pipecat `InputParams` on the LLM service, not appended to messages.
4. The interruptibility percentage flows through `pipeline.vad.map_interruptibility(pct)` which returns concrete VAD parameters. Document the mapping formula in a docstring inside that function — this is graded.

### Interruptibility mapping

Express it as a pure function with a clear, monotonic mapping. Example shape (verify exact Pipecat parameter names against the installed version before committing):

- 0% → conservative: longer VAD stop window, higher confidence floor — bot rarely yields.
- 100% → aggressive: short stop window, low confidence floor — bot yields on the slightest user speech.
  Use linear interpolation between two well-chosen endpoints and clamp inputs to `[0, 100]`. The docstring must state the formula and the parameter names it sets.

---

## Code conventions

### Backend

- **FastAPI + Pydantic v2** for the HTTP surface. Route handlers stay thin; all logic lives in `services/` or `pipeline/`.
- **pydantic-settings** for config. No `os.getenv` outside `core/settings.py`. Settings are injected, not imported globally.
- **Structured logging** via `structlog` with JSON output. Every log line carries `session_id` when one is in scope; use `structlog.contextvars` to bind it at session entry. No `print`.
- **Async everywhere.** Pipecat is async; mixing sync I/O blocks the event loop. Use `httpx.AsyncClient` for the Daily REST API.
- **Custom frame processors** subclass Pipecat's `FrameProcessor`. Keep each processor single-purpose; observability processors must `push_frame` everything they receive unchanged.
- **Errors:** define domain exceptions in `core/errors.py` (`ConfigValidationError`, `UpstreamServiceError`, …) and map them to HTTP responses in one exception handler. Don't raise raw `HTTPException` from services.
- **Retries** belong in `services/` (e.g., Daily room creation) using `tenacity` with bounded exponential backoff. Do not retry inside route handlers.
- **Tests:** pytest + pytest-asyncio. Mock the Daily / OpenAI / Deepgram / Cartesia SDKs at the service boundary, not deeper. The latency, state-machine, and VAD-mapping tests must be deterministic — drive them with synthesized frame sequences and a fake clock, not real audio.

### Frontend

- **App Router only.** No `pages/`. Server Components by default; mark interactive leaves `"use client"`.
- **TanStack Query** owns server state (`/session` POST, `/health` checks). Component state is local `useState`/`useReducer`. No Redux/Zustand unless a concrete need emerges — document it if added.
- **Daily.js lives behind `lib/daily.ts` and `hooks/useDailyCall.ts`.** Components never import `@daily-co/daily-js` directly.
- **Forms with `react-hook-form` + `zod`.** The zod schema for `SessionConfig` is the single source of truth for client-side validation and must structurally match the backend Pydantic model.
- **Env access via `lib/env.ts`** which validates `NEXT_PUBLIC_API_URL` at module load and throws with a clear message if missing. No bare `process.env` reads in components.
- **No hardcoded URLs.** All API calls go through `lib/api.ts` which reads the base URL once.
- **Strict TypeScript.** `strict: true`, `noUncheckedIndexedAccess: true`. Don't use `any`; prefer `unknown` + narrowing.

---

## Critical constraints (rubric-graded; do not violate)

1. **One `docker-compose.yml`.** The file that boots locally is the same file that boots on EC2. No `docker-compose.prod.yml`, no override files for the demo path.
2. **Frontend runs production mode.** The compose service runs `next build` then `next start` (or uses a multi-stage Dockerfile that ships only the standalone build). Never `next dev` in compose.
3. **`restart: unless-stopped`** on every service. The stack must come back after `sudo reboot`.
4. **`NEXT_PUBLIC_API_URL` is configurable.** Frontend reads it at build time; never hardcode `http://localhost:8000`. Behind the Cloudflare tunnel it dies silently.
5. **Mic requires HTTPS.** Test through the tunnel URL. `http://<EC2-IP>:3000` will fail to acquire the microphone and the bug is invisible in the JS console.
6. **Secrets only on EC2.** `.env.example` lists every variable with empty values. Real `.env` is created on the box and never committed.
7. **Clean-boot test passes:** `git clone … && cd … && cp .env.example .env && $EDITOR .env && docker compose up -d` brings the stack up with no other manual steps.
8. **Cloudflare Tunnel is outbound** — only port 22 needs to be open inbound on the EC2 security group. Document this reasoning in DEPLOY.md rather than opening 80/443.

---

## Required environment variables

Define every variable in `.env.example` with an empty value and a comment. At minimum:

```
# OpenAI (LLM)
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini

# Deepgram (STT)
DEEPGRAM_API_KEY=

# Cartesia (TTS)
CARTESIA_API_KEY=
CARTESIA_DEFAULT_VOICE_ID=

# Daily (WebRTC)
DAILY_API_KEY=
DAILY_DOMAIN=

# Frontend
NEXT_PUBLIC_API_URL=
```

`core/settings.py` must fail fast on startup if a required variable is missing, with the variable name in the error.

---

## Testing requirements

These tests are explicitly graded — they must exist and pass:

**Backend**

- `test_config_injection.py` — verifies `SessionConfig` → `InputParams` plumbing for system prompt, temperature, max tokens, TTS voice/speed, STT temperature.
- `test_vad_mapping.py` — boundary tests (0%, 50%, 100%) and monotonicity of `map_interruptibility`.
- `test_state_transitions.py` — feeds synthetic frame sequences and asserts the FSM emits the right state changes.
- `test_latency.py` — fake clock, asserts `latency` event ms equals the gap between `UserStoppedSpeakingFrame` and first `BotStartedSpeakingFrame`.
- `test_interruption.py` — `UserStartedSpeakingFrame` while `SPEAKING` produces one `interruption` event and transitions to `LISTENING`.

**Frontend**

- Config form: required field validation, slider bounds, system-prompt textarea round-trip.
- Dashboard: renders correct badge for each state, formats latency, shows interruption entries.
- `useDataChannel` reducer: feeding event sequences yields the expected derived state.

---

## When in doubt

- **Match the architecture above before reaching for a different one.** If a real constraint forces a deviation, leave a short note in the affected file's docstring explaining why.
- **Verify Pipecat API names against the installed version** before writing frame-processor or VAD code — Pipecat's API surface shifts between minor versions. Read the installed source, don't trust prior assumptions.
- **The data-channel contract is the integration seam.** Changing it requires updating `app/schemas/events.py`, `types/contract.ts`, the sender processor, and the frontend hook in one commit.
