# HANDOFF — Freya Voice Agent

Working notes for the next session. Pairs with [`CLAUDE.md`](./CLAUDE.md) (target
architecture) and [`todo.md`](./todo.md) (rubric checklist). This file captures
**state, decisions, and what to do next** — read it before touching code.

Last updated: June 23, 2026 — CH1 hello-world voice bot complete.

---

## Status

| Phase                                             | State         |
| ------------------------------------------------- | ------------- |
| 0 — SSH key prep                                  | skipped (user) |
| **1 — Repo + Docker scaffold**                    | **done** ✅    |
| **CH1 — Hello-world voice bot**                   | **done** ✅    |
| 2 — Pipecat backend (`/session`, processors, VAD) | next          |
| 3 — Next.js config UI + dashboard                 | pending       |
| 4 — Add-on (Qdrant RAG **or** OpenTelemetry)      | pending       |
| 5 — Security pass                                 | pending       |
| 6 — EC2 deploy + Cloudflare Tunnel                | pending       |
| 7 — DEPLOY.md finalization                        | skeleton only |
| 8 — Submission package                            | pending       |

The stack boots with `docker compose up -d --build`. Both containers report
`healthy`. `curl http://localhost:3000/api/health` returns
`{"status":"ok","version":"0.1.0"}`.

## CH1 verified runtime

The hello-world voice path is working end to end:

```text
Daily transport → Silero VAD → Deepgram STT → OpenAI LLM
  → Cartesia TTS → Daily transport
```

- Pipecat is pinned exactly to `pipecat-ai==1.0.0`.
- Daily.js is pinned exactly to `@daily-co/daily-js==0.91.0`.
- Daily room: `https://vagent.daily.co/freya-ch1`
- The backend container created/reused the room, generated a token, joined it,
  and initialized the Deepgram and Cartesia WebSockets.
- Joining through Daily's prebuilt UI triggered the first-participant hook.
- OpenAI received the exact system context:
  `You are a terse, slightly grumpy pirate. Keep replies under two sentences.`
- OpenAI returned HTTP 200.
- Cartesia generated and played a pirate greeting. Verified examples:
  `Ahoy, matey! What ye want? Make it quick!` and
  `Ahoy there! What brings ye to my ship, matey?`
- Logs emitted `Bot started speaking` and `Bot stopped speaking`.
- The production frontend has one Connect/Disconnect button and
  `NEXT_PUBLIC_DAILY_ROOM_URL=https://vagent.daily.co/freya-ch1` is now present
  in the local `.env`.
- `/connect` was not implemented.

The source now deliberately does not end the pipeline when one participant
leaves. During live testing, a stale browser participant leaving terminated the
first bot instance even though another participant remained. The leave handler
was removed and the focused tests pass. The final backend image rebuild after
this small lifecycle fix was interrupted, so the first action next session is:

```bash
docker compose up -d --build backend
docker compose logs -f backend
```

The backend Dockerfile cache boundary was also moved so future source-only
changes reuse the expensive Pipecat/ONNX dependency layer.

---

## Verify the current build

```bash
cd voice_agent
cp .env.example .env                 # leave vendor keys blank for now
docker compose up -d --build
docker compose ps                     # both should be (healthy)
curl http://localhost:3000/api/health # {"status":"ok",...}
open http://localhost:3000            # placeholder landing page
docker compose down                   # when done
```

If the backend container was created before editing `.env`, recreate it so
Compose injects the new values:

```bash
docker compose up -d --force-recreate backend
```

Changing `.env` does not mutate an already-running container.

---

## What's wired up

```
voice_agent/
├── CLAUDE.md            target architecture + conventions (read this first)
├── HANDOFF.md           this file
├── README.md            project blurb + quickstart
├── DEPLOY.md            EC2 runbook skeleton (TODOs marked)
├── docker-compose.yml   single file, restart: unless-stopped, healthchecks
├── .env.example         OpenAI/Deepgram/Cartesia/Daily + CORS + NEXT_PUBLIC_API_URL
├── .env                 local copy (untracked); vendor keys blank
├── .gitignore           Python + Node + envs
├── backend/
│   ├── pyproject.toml   fastapi, pydantic-settings, structlog, httpx
│   ├── Dockerfile       single-stage, non-root, /health HEALTHCHECK
│   └── app/
│       ├── main.py      create_app(), lifespan, CORS, exc handler
│       ├── core/        settings (env), logging (structlog JSON), errors
│       └── api/health.py
└── frontend/
    ├── package.json     next 14.2 (App Router), strict TS
    ├── next.config.mjs  output: standalone + /api/* rewrite → http://backend:8000
    ├── Dockerfile       3-stage build, runs node server.js
    ├── app/             layout, page (placeholder), globals.css
    └── lib/             env.ts (validates NEXT_PUBLIC_API_URL), api.ts (typed fetch)
```

Phase 2/3 directories from `CLAUDE.md` (`backend/app/schemas/`,
`backend/app/services/`, `backend/app/pipeline/`, `frontend/components/`,
`frontend/hooks/`, `frontend/types/`) **do not exist yet**. Create them on demand.

CH1 added:

```text
backend/app/bot.py             hardcoded Daily/Pipecat bot
backend/tests/test_ch1_bot.py  deterministic pipeline/context wiring tests
backend/uv.lock                exact backend dependency lock
frontend/lib/daily.ts          Daily.js wrapper
frontend/app/page.tsx          minimal Connect/Disconnect client
frontend/package-lock.json     exact frontend dependency lock
```

---

## Decisions made (and why)

These are session-level choices that aren't in CLAUDE.md.

1. **Same-origin `/api/*` proxy** instead of publishing the backend port.
   `frontend/next.config.mjs` rewrites `/api/:path*` to
   `http://backend:8000/:path*` on the docker network. Means the browser only
   ever sees one origin, the EC2 security group only needs port 22, and
   Cloudflare Tunnel only has to publish one host. `NEXT_PUBLIC_API_URL`
   defaults to `/api` — keep it relative unless we later tunnel the backend on
   a separate hostname.

2. **Backend Dockerfile is single-stage**, not multi-stage. Pure-Python deps,
   no native compilation to isolate. The first attempt used
   `pip wheel --no-deps` to stage and `pip install --no-index` to install
   offline — this dropped transitive deps (`starlette`) and failed. Don't
   reintroduce multi-stage unless you also drop `--no-deps` from the wheel
   step or use `uv pip compile`.

3. **Vendor keys are optional at boot.** `Settings` declares OpenAI/Deepgram/
   Cartesia/Daily fields as `SecretStr | None = None`. The fail-fast contract
   from CLAUDE.md ("error names the missing var") is enforced lazily via
   `Settings.require(name)` — call it from each service before the first API
   call. Lets Phase 1 boot without provisioning all four vendors first.

4. **`BACKEND_CORS_ORIGINS` is comma-separated.** See "Gotchas" #2 for the
   pydantic-settings story. The field is `Annotated[list[str], NoDecode]`
   plus a `field_validator` that handles both `a,b` and `["a","b"]` inputs.

5. **`.env` is generated from `.env.example`** at the top of Phase 1 with
   vendor keys blank. It's gitignored. Real keys go in on EC2 only.

---

## Gotchas (you will hit these again)

1. **Backend Dockerfile cache layers.** Source code lives at `/srv/app` (not
   `/app`) because `WORKDIR=/srv` and we `COPY app ./app`. `pip install .`
   then installs the package into site-packages; uvicorn imports it from
   there, not from `/srv/app`. If you edit code and rebuild, both copies move
   in sync — but a partial rebuild can leave stale wheels. `docker compose
   build --no-cache backend` if you see ghost imports.

2. **pydantic-settings v2 + complex env vars.** For any field typed
   `list[str]` / `dict[...]` / etc., pydantic-settings tries to JSON-decode
   the raw env string **before** field validators run. A bare value like
   `BACKEND_CORS_ORIGINS=http://localhost:3000` raises `SettingsError`. Two
   fixes: (a) write JSON in the env file (`["..."]`), or (b) annotate with
   `NoDecode` (`from pydantic_settings import NoDecode`) and parse in a
   validator. We chose (b).

3. **Frontend production mode only in compose.** Never add `next dev` to the
   compose service. If you need hot reload, run `npm run dev` from
   `frontend/` with `BACKEND_INTERNAL_URL=http://localhost:8000` and the
   backend exposed on `:8000` (uncomment the `ports:` block in
   `docker-compose.yml`). The deployed compose file must stay in production
   mode — rubric checks this.

4. **`NEXT_PUBLIC_API_URL` bakes at build time.** Changing it in `.env`
   without rebuilding the frontend image has no effect. After editing,
   `docker compose up -d --build frontend`.

5. **Mic over HTTPS only.** Not relevant yet (no mic code), but the moment
   Phase 3 lands, testing on `http://localhost:3000` works (browsers treat
   localhost as secure) but `http://<EC2-IP>:3000` will silently fail to
   acquire the microphone. Always test through the tunnel URL.

---

## Verification completed

```text
ruff check: passed
ruff format --check: passed
pytest: 3 passed
mypy app: passed
frontend typecheck: passed
frontend production build: passed
compose backend/frontend: healthy
proxied /api/health: passed
live Daily room join: passed
first greeting through OpenAI + Cartesia: passed
```

Manual verification still worth repeating tomorrow with a physical microphone:

1. Open `http://localhost:3000`.
2. Click Connect and allow microphone access.
3. Confirm the greeting is audible.
4. Speak for a short back-and-forth.
5. Talk over the bot and confirm default interruption stops its speech.

## Next: Phase 2 (Pipecat backend)

Build in this order. Each step is independently testable.

1. **`backend/app/schemas/config.py`** — `SessionConfig` pydantic model:
   `system_prompt`, `temperature`, `max_tokens`, `stt_temperature`,
   `tts_voice_id`, `tts_speed`, `tts_temperature`, `interruptibility_pct`.
   Include sanitization on the system prompt (strip control chars, length
   cap, no role-injection markers).

2. **`backend/app/schemas/events.py`** — `DataChannelEvent` discriminated
   union mirroring the TS contract in CLAUDE.md (`state` / `latency` /
   `interruption`, all with `at` ms).

3. **`backend/app/services/daily.py`** — async `httpx` client for room
   creation + meeting-token issuance. Wrap with `tenacity` bounded retries.

4. **`backend/app/pipeline/vad.py`** — `map_interruptibility(pct: int) ->
   dict`. Pure, monotonic, clamp `[0, 100]`. Docstring must state the
   formula and which Pipecat VAD param names it sets — graded.

5. **`backend/app/pipeline/processors/`** — four `FrameProcessor`
   subclasses. They must `push_frame` everything they observe unchanged.
   - `state_tracker.py` — FSM described in CLAUDE.md (LISTENING / THINKING /
     SPEAKING + interruption transition).
   - `latency_tracker.py` — single shared clock with the state tracker;
     emits `latency` event at the same anchor that flips the state to
     SPEAKING.
   - `interruption_detector.py` — emits `interruption` on user-speech-while-
     SPEAKING. Coordinate with `state_tracker` so the interruption fires
     **before** the LISTENING transition.
   - `data_channel_sender.py` — serializes `DataChannelEvent` and writes to
     the Daily transport.

6. **`backend/app/pipeline/factory.py`** — `build_pipeline(config) ->
   Pipeline`. System prompt + temperature **must** be injected through
   Pipecat `InputParams`, not appended to the message list.

7. **`backend/app/api/session.py`** — `POST /session`. Validates config →
   creates Daily room/token → spawns Pipecat agent bound to the room →
   returns `{roomUrl, token, sessionId}`. Use `structlog.contextvars` to
   bind `session_id` so every log line in the session carries it.

8. **Tests** — `test_config_injection.py`, `test_vad_mapping.py`,
   `test_state_transitions.py`, `test_latency.py`, `test_interruption.py`.
   Drive with synthetic frame sequences + fake clock. Mock the vendor SDKs
   at the service boundary, not deeper.

**Before writing pipeline code, verify the installed Pipecat version's
frame-class names and `InputParams` shape** — pull the version with
`uv add pipecat-ai` (or whatever distribution we pick), then read the
installed source. CLAUDE.md flags this; the API shifts between minor
versions.

After Phase 2, tighten `Settings.require()` calls in the new services so the
fail-fast path is exercised.

---

## Open questions for the user

- **Pipecat version pin.** Latest stable, or a specific minor we want to
  match a tutorial / known-good config?
- **Add-on choice (Phase 4).** Qdrant RAG vs. OpenTelemetry — affects the
  pipeline shape we settle on in Phase 2.
- **Daily account.** Are the API key + subdomain provisioned, or should we
  build with placeholders and wire real credentials only at deploy time?
