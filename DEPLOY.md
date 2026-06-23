# DEPLOY.md — Freya on EC2

One-page deployment runbook for the Freya interruptible voice agent.

## EC2 target

| Field         | Value                                                         |
| ------------- | ------------------------------------------------------------- |
| Region        | `us-east-1`                                                 |
| AMI           | Ubuntu Server 24.04 LTS (x86_64)                              |
| Instance type | `t3.medium`                                                 |
| Disk          | 16 GB gp3                                                     |
| SSH user      | `ubuntu`                                                    |
| Public URL    | `https://acquire-synthetic-manager-rent.trycloudflare.com/` |

## Security group

Only SSH is open inbound:

| Port       | Source                   | Purpose            |
| ---------- | ------------------------ | ------------------ |
| `22/tcp` | Grader/operator IP range | SSH administration |

Ports `3000` and `8000` are not opened publicly. Cloudflare Tunnel runs as an
outbound process on the EC2 host and exposes the frontend over HTTPS. This keeps
the backend private and still gives browsers a secure origin for microphone
access.

## Docker Compose wiring

The deployment uses the single repository `docker-compose.yml`.

- `frontend`: Next.js production server on host port `3000`.
- `backend`: FastAPI/Pipecat service on internal port `8000`, not published.
- `qdrant`: internal vector store on the Docker network.
- The frontend proxies `/api/*` to `http://backend:8000` using the Compose
  network, so browser traffic only needs the frontend origin.
- Cloudflare Tunnel forwards public HTTPS traffic to `http://localhost:3000`.
- All services use `restart: unless-stopped` so Docker restarts them after reboot.

Initial boot after secrets are provisioned:

```bash
git clone <repo>
cd vagent
docker compose up -d --build
```

After pulling code changes:

```bash
git pull
docker compose up -d --build --force-recreate backend frontend
```

## Logs and health checks

Application logs go to container stdout/stderr and are available through Docker:

```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f qdrant
docker compose ps
```

Health check:

```bash
curl http://localhost:3000/api/health
```

Expected result includes `"status":"ok"`.

## Restart after reboot

Docker brings the Compose services back automatically because each service uses
`restart: unless-stopped`. To verify after reboot:

```bash
cd ~/vagent
docker compose ps
curl http://localhost:3000/api/health
```

If a manual restart is needed:

```bash
cd ~/vagent
docker compose down
docker compose up -d
```

For the temporary Cloudflare URL, keep `cloudflared` running in `tmux`:

```bash
tmux attach -t freya
# or create it:
tmux new -s freya
cloudflared tunnel --url http://localhost:3000
```

Detach with `Ctrl+b`, then `d`. The `trycloudflare.com` URL remains reachable
only while that tunnel process stays alive.
