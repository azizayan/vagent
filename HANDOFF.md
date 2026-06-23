# HANDOFF — Freya Voice Agent

Read with [`AGENTS.md`](./AGENTS.md) and [`todo.md`](./todo.md) before changing
code.

Last updated: June 23, 2026 — Qdrant help-center RAG, data-channel dashboard,
two-panel UI, preset/custom Cartesia voice picker, default system prompt, and
state-reset-on-reconnect complete.

## Current status

| Phase | State |
| --- | --- |
| Repo + production Compose scaffold | done |
| CH1 voice pipeline | done |
| Session API + configurable agent startup | done |
| Two-panel config + dashboard UI | done |
| Preset/custom Cartesia voice picker | done |
| State/latency/interruption data-channel | done |
| Default system prompt + backend fallback | done |
| Backend tests (state, latency, interruption, VAD, config, output guard) | done |
| Frontend tests (Jest — reducer, dashboard, config-form) | done |
| Qdrant help-center RAG add-on | done |
| EC2 + Cloudflare deployment | existing deployment; needs `git pull && docker compose up -d --build` |
| DEPLOY.md finalization | pending |
| Submission package | pending |

## Implemented session flow

1. Frontend submits `SessionConfig` to `POST /api/session`.
2. Next.js rewrites `/api/*` → `http://backend:8000/*` (same-origin proxy).
3. Backend validates with Pydantic v2, sanitizes system prompt, resolves empty → DEFAULT.
4. `DailyService` creates a private per-session room and separate user/bot tokens.
5. `AgentRunner` spawns one Pipecat task for that room.
6. Frontend joins Daily with `{roomUrl, token, sessionId}`.
7. Backend pipeline pushes `state`/`latency`/`interruption` events over Daily data channel.
8. `useDataChannel` hook in the frontend receives them and drives the dashboard.

## Data channel contract

Events are pushed from backend → frontend only (write-only from backend).
Defined in `backend/app/schemas/events.py` and mirrored in `frontend/types/contract.ts`:

```typescript
type DataChannelEvent =
  | { type: "state";       state: "LISTENING" | "THINKING" | "SPEAKING"; at: number }
  | { type: "latency";     ms: number; at: number }
  | { type: "interruption"; at: number }
```

`at` is milliseconds since session start (monotonic clock on the backend).
Daily delivers these as `app-message` events; Daily also sends its own RTVI
metrics frames (`type: "metrics"`) which the frontend filter ignores.

## Bot state machine

Implemented in `backend/app/pipeline/processors/state_tracker.py`:

- `UserStoppedSpeakingFrame` → emit THINKING, start latency clock
- First `BotStartedSpeakingFrame` after THINKING → emit SPEAKING, stop clock, emit latency event
- `BotStoppedSpeakingFrame` → emit LISTENING
- `UserStartedSpeakingFrame` while SPEAKING → emit interruption event then LISTENING

`DataChannelSender` (`backend/app/pipeline/processors/data_channel_sender.py`) serialises
events via `DailyOutputTransportMessageUrgentFrame` and pushes them downstream to
`transport.output()`.

Pipeline order in `bot.py`:

```
transport.input() → StateTracker → STT → user_aggregator →
HelpCenterRetriever → LLM → LLMOutputGuard → TTS →
DataChannelSender → transport.output() → assistant_aggregator
```

## Help-center RAG

- Qdrant `v1.14.1` runs as an internal-only Compose service with a persistent
  volume and a 256 MB memory limit. It has no host-published port.
- `backend/app/data/help_center.json` contains 18 small fake Q&A entries.
- Planted fact: Freya's return window is **37 days**.
- `HelpCenterService` uses OpenAI `text-embedding-3-small` with 1536 dimensions.
  API embeddings were chosen instead of a local model to protect RAM on the
  shared t3.medium.
- Backend startup creates `freya_help_center` and seeds deterministic point IDs
  only when needed. Subsequent boots log `help_center.seed_already_present`.
- `HelpCenterRetriever` queries Qdrant with `k=3`, logs the question and results,
  clones the Pipecat 1.0.0 `LLMContextFrame`, and inserts retrieved help-center
  text before the latest user message. The shared conversation history is not
  mutated.
- Retrieval failures are fail-open: the original context continues to the LLM.
- The synthetic first-join greeting is excluded from retrieval.

## System prompt

Default defined in `backend/app/pipeline/prompts.py` (`DEFAULT_SYSTEM_PROMPT`) and
mirrored in `frontend/lib/defaults.ts`. Rules baked into the default:

- General conversation, questions, explanations, and casual assistance
- No coding, debugging, architecture, file generation, or claimed real-world actions
- No claims of access to systems, accounts, devices, or data
- Natural speech in one to four sentences, avoiding lists and markdown
- One clarifying question when needed
- Out-of-scope requests receive a brief limitation and redirect

`resolve_system_prompt(raw)` returns `(prompt, used_default: bool)`. If `raw`
is empty after strip, it returns the default and logs `system_prompt_used_default=True`.

`config.py` field: `max_length=4000` (rejects with 422 if exceeded), no `min_length`
(empty → default via resolver, not a validation error).

Backend logs at every `bot.starting`:

```text
system_prompt_used_default=True/False
system_prompt_length=<n>
system_prompt_preview=<first 120 chars>
```

## Runtime configuration

All fields in `SessionConfig` (`backend/app/schemas/config.py`):

| Field | Wired | Notes |
| --- | --- | --- |
| `system_prompt` | ✅ | injected via `OpenAILLMService.Settings(system_instruction=...)` |
| `temperature` | ✅ | OpenAI LLM |
| `max_tokens` | ✅ | OpenAI LLM |
| `tts_voice_id` | ✅ | Cartesia voice |
| `tts_speed` | ✅ | Cartesia `GenerationConfig(speed=...)` |
| `stt_temperature` | ❌ | no param in Pipecat 1.0.0 `DeepgramSTTSettings`; logged as received |
| `tts_temperature` | ❌ | no param in Pipecat 1.0.0 `CartesiaTTSSettings`/`GenerationConfig`; logged as received |
| `interruptibility_pct` | ✅ | mapped to `VADParams` via `pipeline/vad.py` |

## Interruptibility mapping

`backend/app/pipeline/vad.py` linearly maps `[0, 100]` to `VADParams`:

| Percentage | confidence | start_secs | stop_secs | min_volume |
| --- | ---: | ---: | ---: | ---: |
| 0 | 0.85 | 0.30 | 0.80 | 0.60 |
| 50 | 0.65 | 0.175 | 0.475 | 0.475 |
| 100 | 0.45 | 0.05 | 0.15 | 0.35 |

## Frontend architecture

Single page (`frontend/app/page.tsx`), two-panel dark layout:

- **Left panel** — config form, preset/custom Cartesia voice picker, Start button.
  All controls are disabled while connected. The system-prompt textarea is expanded
  vertically to use the available panel space.
- **Right panel** — bot state pill (LISTENING=slate, THINKING=amber+pulse, SPEAKING=green+glow),
  round-trip latency metric labeled "user silence → first bot audio", interruption log, Disconnect.

Key files:

```text
frontend/app/page.tsx          — main page, wires everything
frontend/components/config/VoicePicker.tsx — five presets + required named custom voice ID
frontend/hooks/useDataChannel.ts — subscribes to Daily app-message, reducer-based state
frontend/lib/defaults.ts       — DEFAULT_SYSTEM_PROMPT constant
frontend/lib/api.ts            — typed fetch wrapper (reads NEXT_PUBLIC_API_URL)
frontend/lib/daily.ts          — Daily.js thin wrapper
frontend/lib/env.ts            — validates NEXT_PUBLIC_API_URL at module load
frontend/types/contract.ts     — mirrors backend schemas (SessionConfig, DataChannelEvent)
frontend/app/providers.tsx     — QueryClientProvider wrapper
```

State reset: `useDataChannel` dispatches `{ type: "__reset__" }` every time the
`call` ref changes, so reconnecting always starts with zeroed state.

RTVI metrics frames from Daily (`type: "metrics"`) are filtered by a `KNOWN_TYPES`
set before dispatching to the reducer; the reducer also has a `default: return state`
guard.

## LLM output guard

`backend/app/pipeline/processors/output_guard.py` sits between OpenAI and Cartesia.
Blocks: control characters, whitespace runs, code-like tokens, excessive script
switching, excessive symbols, overlong responses (>800 chars). Invalid responses
replaced with a safe fallback. Logged as `llm.output_rejected`.

## Test coverage

Backend (`uv run pytest`):

```text
tests/test_health.py
tests/test_session.py
tests/test_vad_mapping.py
tests/test_config_injection.py
tests/test_output_guard.py
tests/test_help_center.py
tests/test_state_transitions.py
tests/test_latency.py
tests/test_interruption.py
```

Frontend (`npm test` via Jest/`next/jest`):

```text
tests/useDataChannel.test.ts   — reducer: state transitions, latency, interruption sequence
tests/dashboard.test.tsx       — badge per state, latency formatting, interruption list
tests/config-form.test.tsx     — required fields, slider bounds, textarea and voice picker
```

## Deployment decisions to preserve

1. One `docker-compose.yml` — identical local and EC2.
2. Frontend runs production mode (`next build && next start`) in Compose.
3. `restart: unless-stopped` on every service.
4. Backend stays internal; browser uses same-origin `/api` proxy (Next.js rewrite).
5. `NEXT_PUBLIC_API_URL=/api` in `.env` — baked at `next build` time; rebuild after changing.
6. Secrets only in untracked `.env`.
7. Cloudflare Tunnel publishes frontend at port 3000; only SSH (22) open inbound on EC2.
8. Mic requires HTTPS — always test through the tunnel URL, not raw IP.

## Important implementation notes

- Pipecat pinned to `pipecat-ai==1.0.0`. Verify parameter names against installed
  source before adding new integrations.
- `DailyOutputTransportMessageUrgentFrame` is what broadcasts over the Daily data
  channel; must be pushed DOWNSTREAM and arrive before `transport.output()`.
- `NEXT_PUBLIC_API_URL` is baked during `next build`; rebuild the frontend image
  after changing it in `.env`.
- Changing `.env` does not update running containers; recreate the affected service.
- Backend source mounted from `/srv/app` in container. If rebuilt code appears stale,
  use `docker compose build --no-cache backend`.

## Next work

1. EC2: `git pull && docker compose up -d --build` to deploy current changes.
2. Verify Qdrant seed logs and mic through HTTPS tunnel after redeploy.
3. DEPLOY.md — finalize one-page deployment guide.
4. Demo video + submission package.
