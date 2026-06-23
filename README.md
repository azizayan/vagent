# Freya — Interruptible Voice Agent

Real-time voice agent. Browser captures the user's mic over Daily WebRTC, a
Pipecat pipeline (Deepgram STT → OpenAI LLM → Cartesia TTS) responds, and the
user can interrupt the bot mid-response with configurable aggressiveness. Live
bot state, round-trip latency, and interruption events stream back to the UI
over a Daily data channel.

## Stack

- **Frontend:** Next.js (App Router, TypeScript), Daily.js, TanStack Query
- **Backend:** Python, FastAPI, Pipecat
- **Realtime:** Daily.co WebRTC + data channel
- **Vendors:** Deepgram (STT), OpenAI (LLM), Cartesia (TTS)
- **Infra:** Docker Compose, AWS EC2, Cloudflare Tunnel (HTTPS)

See [`CLAUDE.md`](./CLAUDE.md) for the target architecture and code
conventions, and [`DEPLOY.md`](./DEPLOY.md) for the EC2 deployment runbook.

## Local quickstart

The application cannot have a functional voice session without vendor credentials.
Provisioning `.env` is therefore the one required precondition to the PDF's clean-box
`docker compose up -d` command:

```bash
git clone <repo>
cd voice_agent
cp .env.example .env
$EDITOR .env               # fill in OpenAI, Deepgram, Cartesia, and Daily keys
docker compose up -d --build
open http://localhost:3000
```

After `.env` has been provisioned on an EC2 host, every later boot or deployment is
one command:

```bash
docker compose up -d
```

Secrets cannot be included in the repository to make the unmodified three-part
`git clone && cd && docker compose up -d` command sufficient. The source checkout
and Compose file need no other modification.

The frontend runs in production mode (`next build && next start`) — the same
mode that ships to EC2. There is intentionally no `docker-compose.dev.yml`.

Health checks: `curl http://localhost:3000/api/health` (proxied through the
Next.js rewrite to the backend container).

## Demo verification

After pulling changes on EC2, rebuild both app containers so the browser is not
served an old Next.js bundle:

```bash
docker compose up -d --build --force-recreate backend frontend
docker compose logs -f backend frontend
```

When a session starts successfully, backend logs should show Daily room creation
with `200 OK`, `POST /session` with `201 Created`, a `bot.starting` config log,
and `Joined https://...daily.co/...`. Test the browser through the HTTPS
Cloudflare URL, not the raw EC2 HTTP address, because microphone capture requires
a secure origin.

## Repository structure

```
backend/
├── app/
│   ├── main.py                  FastAPI entrypoint, lifespan wires HelpCenterService + AgentRunner + DailyService
│   ├── bot.py                   run_bot() builds the full Pipecat pipeline per session
│   ├── api/
│   │   ├── health.py            GET /health
│   │   └── session.py           POST /session — creates a Daily room, returns token, spawns the bot task
│   ├── core/
│   │   ├── settings.py          pydantic-settings, single source of truth for env
│   │   ├── logging.py           structlog JSON setup
│   │   └── errors.py            Domain exceptions mapped to HTTP responses
│   ├── schemas/
│   │   ├── config.py            SessionConfig (frontend → backend contract)
│   │   └── events.py            DataChannelEvent union (backend → frontend over Daily)
│   ├── services/
│   │   ├── daily.py             Daily REST client (httpx.AsyncClient + tenacity retries)
│   │   ├── agent_runner.py      Tracks per-session asyncio tasks
│   │   └── help_center.py       Qdrant + OpenAI embeddings (RAG add-on)
│   ├── data/
│   │   └── help_center.json     Seed Q&A entries for the help-center collection
│   └── pipeline/
│       ├── idle_session.py      Reminder prompt + graceful shutdown on user inactivity
│       ├── prompts.py           Default system prompt + resolver
│       ├── vad.py               Maps interruptibility % → Silero VADParams
│       └── processors/
│           ├── state_tracker.py         FSM emitting state + latency events
│           ├── output_guard.py          LLMOutputGuard between LLM and TTS
│           ├── help_center_retriever.py k=3 Qdrant lookup, fail-open
│           └── data_channel_sender.py   Serialises events onto the Daily data channel
└── tests/                       Pytest suite (VAD, FSM, latency, interruption, RAG, idle, output guard…)

frontend/
├── app/                         Next.js App Router (page.tsx is the single dashboard)
├── components/config/           Config form (voice picker, sliders, prompt area)
├── hooks/useDataChannel.ts      Daily app-message subscriber + reducer driving the dashboard
├── lib/                         api / daily / env wrappers (no bare process.env in components)
├── types/contract.ts            Mirrors backend schemas — must stay in sync
└── tests/                       Jest (reducer, dashboard, config form, inactivity notice)

docker-compose.yml               Single file used both locally and on EC2
.env.example                     Required environment variables
DEPLOY.md                        EC2 + Cloudflare Tunnel runbook
CLAUDE.md                        Architecture + code conventions
```

## Add-ons implemented

The PDF lists two optional add-ons; this submission ships the first one:

- **Help-center RAG (Qdrant)** — a third Compose service (`qdrant:v1.14.1`) runs
  internally on the Docker network. On startup the backend embeds
  `backend/app/data/help_center.json` with `text-embedding-3-small` and seeds
  the `freya_help_center` collection (idempotent — subsequent boots log
  `help_center.seed_already_present`). A `HelpCenterRetriever` processor sits
  between the user aggregator and the LLM, runs `k=3` retrieval on each user
  turn, and inserts the retrieved snippets into a cloned `LLMContextFrame`
  *before* the latest user message so shared conversation history is never
  mutated. Retrieval failures are fail-open: the original context still
  reaches the LLM. To verify in a session, ask the bot a question whose answer
  is planted in `help_center.json` (e.g. "what is the return window?" — the
  seeded fact is 37 days).

## Features

- Configurable system prompt, LLM temperature / max-tokens, TTS voice / speed /
  temperature, STT temperature (accepted for contract parity; see note below),
  and an **interruptibility percentage** that maps to concrete Silero VAD
  parameters in `backend/app/pipeline/vad.py`.
- Real-time **bot state** dashboard (LISTENING / THINKING / SPEAKING) and
  **round-trip latency** measured from end-of-user-speech to first bot audio.
- **Mid-thinking interruption**: the user can cut the bot off while the LLM is
  still generating, not just while audio is playing.
- **Qdrant help-center RAG** add-on with `text-embedding-3-small` and a
  fail-open retriever that enriches the LLM context without mutating the
  shared conversation history.
- Per-IP rate limiting on `POST /session`, structured JSON logs with
  `session_id` binding, tenacity retries on Daily REST calls, and an
  `LLMOutputGuard` between OpenAI and Cartesia.
- Single `docker-compose.yml` used locally and on EC2 — frontend runs in
  production mode (`output: standalone`), backend is internal-only, and the
  browser reaches it via a same-origin `/api` rewrite so only one port is
  tunneled.

### Note on temperatures

`tts_temperature` maps to Cartesia Sonic-3's `emotion` field
(`< 0.34` → "neutral", `> 0.66` → "excited", middle band → Cartesia default)
because Sonic-3 dropped the raw temperature parameter from its API.
`stt_temperature` is validated and logged but **not applied** — Deepgram's
streaming STT API has no temperature parameter to wire it to. Both fields
remain in the `SessionConfig` contract for forward compatibility.
