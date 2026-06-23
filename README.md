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

```bash
git clone <repo>
cd voice_agent
cp .env.example .env       # fill in API keys
docker compose up -d --build
open http://localhost:3000
```

The frontend runs in production mode (`next build && next start`) — the same
mode that ships to EC2. There is intentionally no `docker-compose.dev.yml`.

Health checks: `curl http://localhost:3000/api/health` (proxied through the
Next.js rewrite to the backend container).

## Layout

```
frontend/              Next.js App Router (standalone build)
backend/               FastAPI + Pipecat
docker-compose.yml     Single file used locally and on EC2
.env.example           Required environment variables
DEPLOY.md              EC2 + Cloudflare Tunnel runbook
```

## Phase status

- [x] Phase 1 — repo + compose scaffold (this commit)
- [ ] Phase 2 — Pipecat pipeline, session API, state/latency processors
- [ ] Phase 3 — Next.js config UI + live dashboard
- [ ] Phase 4 — Add-on (Qdrant RAG or OpenTelemetry)
- [ ] Phase 5 — Security pass
- [ ] Phase 6 — EC2 deployment + tunnel
