# DEPLOY.md — Freya on EC2

One-page production runbook. The stack uses a single `docker-compose.yml` that
boots identically on a laptop and on EC2.

> Phase-1 scaffold note: the live deployment is finalized in Phase 6.
> Section TODOs below mark fields that must be filled before submission.

## Target

| Field          | Value                                                  |
| -------------- | ------------------------------------------------------ |
| AWS Region     | _TODO (e.g. `us-east-1`)_                              |
| AMI            | Ubuntu Server 22.04 LTS (x86_64)                       |
| Instance Type  | `t3.medium`                                            |
| Disk           | 16 GB gp3                                              |
| SSH user       | `ubuntu`                                               |
| Public host    | _TODO — Cloudflare Tunnel hostname_                    |

## Security group (inbound)

| Port | Why                                                                |
| ---- | ------------------------------------------------------------------ |
| 22   | SSH for the grader / operator                                      |

**Only port 22.** The frontend and backend are **not** exposed to the public
internet directly. Cloudflare Tunnel runs as an outbound process on the box and
publishes the frontend (`localhost:3000`) over HTTPS. Outbound is the default
allow on AWS, so no extra rules are needed.

Mic access in the browser requires a secure context — always test through the
Cloudflare Tunnel HTTPS URL, never the raw EC2 IP.

## Compose architecture

```
            ┌──────────────────────────────────────────────────┐
            │ EC2 host                                         │
            │                                                  │
   (HTTPS)  │   cloudflared ──► 127.0.0.1:3000                │
   ───────► │                       │                          │
            │                       ▼                          │
            │   ┌──────────────┐ /api/* ┌───────────────────┐ │
            │   │  frontend    │───────►│  backend          │ │
            │   │  Next.js 14  │  http  │  FastAPI + Pipecat│ │
            │   │  prod mode   │        │  (port 8000)      │ │
            │   │  port 3000   │        │  unpublished      │ │
            │   └──────────────┘        └───────────────────┘ │
            │      docker network: "freya"                    │
            └──────────────────────────────────────────────────┘
```

- Frontend uses Next.js rewrites to forward `/api/*` to the backend on the
  internal docker network, so the browser only ever talks to one origin.
- `restart: unless-stopped` on both services — the stack returns after
  `sudo reboot`.

## Environment

1. SSH into the box.
2. `git clone <repo> && cd <repo>`
3. `cp .env.example .env`
4. Fill in API keys in `.env` (see [`.env.example`](./.env.example) for the full list).
5. `docker compose up -d --build`
6. Verify: `curl http://localhost:3000/api/health` returns `{"status":"ok",...}`.
7. Start the Cloudflare Tunnel pointing at `http://localhost:3000`.

The production `.env` lives **only** on the EC2 box. It is never committed.

## Logs

```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose ps          # health status
```

JSON-structured logs land on stdout and are captured by Docker's local driver.
For longer retention, ship to CloudWatch or attach a log-rotation policy on the
Docker daemon (`/etc/docker/daemon.json` → `log-opts.max-size`).

## Restart after reboot

`restart: unless-stopped` brings the containers back automatically when the
Docker daemon comes up after boot. To force a manual restart:

```bash
cd ~/voice_agent
docker compose down
docker compose up -d
```

To rebuild after pulling code changes:

```bash
git pull
docker compose up -d --build
```

## Troubleshooting

- **Mic doesn't activate in the browser** — you are on `http://`. Use the HTTPS
  tunnel URL.
- **`/api/health` 502s** — backend container is unhealthy. Check `docker compose logs backend`; usually a missing required env var on first boot.
- **Stack didn't survive reboot** — verify `restart: unless-stopped` is on every
  service in `docker-compose.yml` and that the Docker daemon is enabled
  (`systemctl is-enabled docker`).
