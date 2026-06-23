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

## Layout

```
frontend/              Next.js App Router (standalone build)
backend/               FastAPI + Pipecat
docker-compose.yml     Single file used locally and on EC2
.env.example           Required environment variables
DEPLOY.md              EC2 + Cloudflare Tunnel runbook
```

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
