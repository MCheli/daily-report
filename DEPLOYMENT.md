# Deploying daily-report on 83rr-poweredge

Self-contained instructions for the deployment agent. Adds this service to
the existing 83rr-poweredge docker-compose stack as a long-running container
that prints the report on a schedule and exposes an HTTP API for ad-hoc runs.

The image is published from this repo via GitHub Actions on every push to
`main` as `ghcr.io/mcheli/daily-report:latest`.

## TL;DR

1. Add a `daily-report` service to `~/83rr-poweredge/docker-compose.yml`
   (stanza below). Same `infrastructure` network as Prometheus.
2. Add the secrets listed in **Environment** to `~/83rr-poweredge/.env`.
3. `make pull && make up` (or `docker compose up -d daily-report`).
4. Verify `curl http://localhost:8080/health` returns `{"status":"ok"}`
   from the host. Add an nginx site only if you want the API reachable
   off-host.

## Container facts

| | |
|---|---|
| Image | `ghcr.io/mcheli/daily-report:latest` |
| Default command | `python -m daily_report.cli service` |
| API port | `8080` (inside the container) |
| Health endpoint | `GET /health` |
| Network requirement | must reach `prometheus:9090` and the LAN printer at `192.168.1.147:9100` |
| Persistent state | none |
| Auto-update | Watchtower-compatible (label included) |

## docker-compose stanza

Drop this into the `services:` block of `~/83rr-poweredge/docker-compose.yml`,
preferably near `tasks` / `tallied` for grouping:

```yaml
  # ═════════════════════════════════════════════════════════════════════════════
  # Daily Report (thermal-printer report generator)
  # Image published from: github.com/MCheli/daily-report
  # ═════════════════════════════════════════════════════════════════════════════
  daily-report:
    image: ghcr.io/mcheli/daily-report:latest
    container_name: daily-report
    restart: unless-stopped
    logging: *default-logging
    labels:
      - "com.centurylinklabs.watchtower.enable=true"
    env_file: .env
    environment:
      - TZ=America/New_York
      - REPORT_TIMES=07:00
      - PROM_URL=http://prometheus:9090
      - DAILY_REPORT_PORT=8080
      # Pull-throughs from .env (defined in the Environment section below):
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - TALLIED_API_KEY=${TALLIED_API_KEY}
      - TASKS_API_KEY=${TASKS_API_KEY}
      - HOME_ASSISTANT_TOKEN=${HOME_ASSISTANT_TOKEN}
      - CALENDAR_ICS_URL=${CALENDAR_ICS_URL}
      - DAILY_REPORT_API_TOKEN=${DAILY_REPORT_API_TOKEN}
    networks:
      - infrastructure
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8080/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s
```

**No new volume**, **no new network**, **no port publish** — the API is
internal-only by default. Add an nginx route below if you want LAN access.

## Environment

Add these to `~/83rr-poweredge/.env` (gitignored). Values come from this
repo's `.env.example`; the maintainer of the daily-report code will provide
the secrets out of band.

```bash
# AI summary (Claude Haiku 4.5)
ANTHROPIC_API_KEY=sk-ant-api03-...

# Tallied finance data (money.markcheli.com)
TALLIED_API_KEY=tld_...

# Tasks (tasks.markcheli.com — mint at /settings)
TASKS_API_KEY=tsk_...

# Home Assistant (home.markcheli.com — long-lived access token)
HOME_ASSISTANT_TOKEN=eyJ...

# Google Calendar ICS secret URL
CALENDAR_ICS_URL=https://calendar.google.com/calendar/ical/.../private-.../basic.ics

# API auth (any random string; required header is `Authorization: Bearer <token>`)
DAILY_REPORT_API_TOKEN=<pick-a-strong-random-string>
```

The container also reads `WEATHER_LOCATION`, `STOCK_TICKER`, and
`TALLIED_DAYS` if you want to override them — sensible defaults
(`Ashland,MA`, `PTC`, `7`) are baked in.

## Schedule

The report prints **once a day at 07:00 local time** by default
(`REPORT_TIMES=07:00`, `TZ=America/New_York`).

To print at multiple times, comma-separate:

```yaml
- REPORT_TIMES=07:00,18:00
```

## API

The API is bound to `0.0.0.0:8080` inside the container. From the host:

```bash
# Health
curl http://daily-report:8080/health
# Trigger a full print
curl -X POST -H "Authorization: Bearer $DAILY_REPORT_API_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{}' http://daily-report:8080/trigger
# Trigger a partial print (only weather + stocks + ai_summary)
curl -X POST -H "Authorization: Bearer $DAILY_REPORT_API_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"sections":["weather","stocks","ai_summary"]}' \
     http://daily-report:8080/trigger
# HTML preview without printing
curl http://daily-report:8080/preview > /tmp/preview.html
```

GET endpoints (`/`, `/preview`, `/health`) don't require auth so the LAN
nginx can serve them. POST endpoints require the bearer token.

## Optional nginx route

If you want the API reachable from your LAN at e.g. `report.ops.markcheli.com`,
drop a site config into `~/83rr-poweredge/infrastructure/nginx/conf.d/`
following the existing `*.ops.markcheli.com` LAN-only pattern. The upstream
is `http://daily-report:8080`. **Do not expose `/trigger` publicly** —
keep it LAN-only or add an additional auth layer.

Minimal config sketch:

```nginx
server {
    listen 443 ssl http2;
    server_name report.ops.markcheli.com;
    include /etc/nginx/conf.d/_lan_only.conf;   # if you have one

    location / {
        proxy_pass http://daily-report:8080;
        proxy_set_header Host $host;
    }
}
```

## Verification checklist

After `docker compose up -d daily-report`:

- [ ] `docker compose ps daily-report` shows `running` + `healthy`
- [ ] `docker compose logs daily-report` shows `[schedule] daily print at 07:00`
      and `daily-report service on http://0.0.0.0:8080`
- [ ] `curl http://localhost:8080/health` returns 200 from the host
- [ ] `docker compose exec daily-report curl -fsS http://prometheus:9090/-/healthy`
      returns 200 (so the server section will work)
- [ ] `docker compose exec daily-report sh -c 'echo > /dev/tcp/192.168.1.147/9100'`
      succeeds (so the printer is reachable)
- [ ] `curl http://localhost:8080/preview` renders HTML with all sections
- [ ] First scheduled print at 07:00 produces a real receipt

## Updating

Watchtower picks up new `:latest` tags automatically. To roll a specific
SHA:

```yaml
image: ghcr.io/mcheli/daily-report:391e090
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `/health` returns 200 but no print at 07:00 | Container TZ wrong; verify with `docker compose exec daily-report date` |
| Server section shows `"prometheus unreachable"` | Service not on the `infrastructure` network |
| Tallied / tasks / power section returns `"_stub": true` | Corresponding env var missing — check the **Environment** section |
| 401 on `POST /trigger` | Missing or wrong `Authorization: Bearer <DAILY_REPORT_API_TOKEN>` |
| `printer fetch failed` / connection refused | Container can't route to `192.168.1.147:9100`; check the printer is online and the host network has a route |

## Where to make changes

- Code, schedule logic, API contract → **this repo** (`MCheli/daily-report`)
- Compose stanza, env-var values, nginx route → `MCheli/83rr-poweredge`
