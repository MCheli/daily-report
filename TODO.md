# Daily-report TODO

Status of each section and the order I'd suggest tackling the remaining work.
Ranked roughly easiest → hardest. "Effort" is rough wall time including any
external setup (account creation, OAuth dances, etc.).

## Done (real data flowing)

- [x] **homelab** — reads `services.json` from the PersonalWebsite repo, optional live HEAD checks
- [x] **github** — uses your existing `gh` CLI auth
- [x] **weather** — wttr.in (no auth)
- [x] **stocks** — yfinance (no auth)
- [x] **motivation** — ZenQuotes with offline fallback list
- [x] **ai_summary** — Anthropic SDK (Claude Haiku 4.5). Needs `ANTHROPIC_API_KEY`. Falls back to a "disabled" line otherwise.
- [x] **tallied** — `X-API-Key` against `money.markcheli.com`. Needs `TALLIED_API_KEY`.

## Trivial (10 minutes each)

- [ ] **Export `ANTHROPIC_API_KEY` so the AI summary actually runs** — code is already there. One `export` away from working.
  - Effort: 5 min
  - You provide: your Anthropic key
- [ ] **Add `.env` file support** so we stop needing shell exports for every key
  - Effort: 15 min
  - Add `python-dotenv` to requirements, call `load_dotenv()` at startup, document a `.env.example` template, gitignore `.env`
- [ ] **Commit + push the preview/tallied work to GitHub**
  - Effort: 5 min

## Easy (30–60 minutes each)

- [ ] **tasks** (mcheli/tasks at tasks.markcheli.com) — same pattern as tallied
  - Effort: 30 min once we have an API key + endpoint
  - You provide: an API key from the tasks app + the endpoint path the Vue frontend uses (visible in browser DevTools → Network), or auth details from the mcheli/tasks repo
  - Returns: open count, by_cycle breakdown, top open tasks list
- [ ] **server** (mcheli/83rr-poweredge resource summary) — query Prometheus
  - Effort: 30–60 min depending on which metrics are exposed
  - You provide: the Prometheus URL on your LAN (likely `http://prometheus.ops.markcheli.com:9090` based on your services.json — confirm)
  - Returns: 1m/5m/15m load, CPU%, mem used/total, disk used%, container counts
  - Fallback if no Prometheus: a stub that SSHs and runs `uptime`/`free`/`df`/`docker ps` — uglier but works without a metrics stack

## Medium (60–90 minutes each)

- [ ] **calendar** — Google Calendar next-events
  - Effort: 60–90 min including the one-time OAuth dance
  - Two paths:
    - `brew install gcalcli` + `gcalcli init` (browser OAuth, one time), then shell out to `gcalcli agenda --tsv ...`. Lower code, requires `gcalcli` to stay installed wherever the report runs
    - Or `google-api-python-client` + a service-account / stored refresh token. More setup but pure Python, deployable anywhere
  - Returns: today_count, week_count, next 5 events with start/title/location/duration

- [ ] **Auto-refresh on the preview server** — currently you have to hit reload manually
  - Effort: 30–60 min
  - Easy version: meta-refresh every 30s
  - Better version: a Server-Sent Events stream that re-renders when source files change (watchdog on `daily_report/`)

- [ ] **Finalize section order** — your spec listed `tasks → tallied → stocks → calendar → motivation → ai_summary → weather → power → server`
  - Effort: 5 min once you confirm it
  - Currently `DEFAULT_ORDER` matches your list with `homelab` and `github` appended at the end

## Harder (depends on choices)

- [ ] **power** — home power consumption
  - Effort: 60–180 min depending on the data source
  - **You need to pick the source first** — this is what makes it hard. Options:
    - **Home Assistant on the LAN**: REST API, easy if you already track power there (best path if available)
    - **Sense**: `sense_energy` Python lib + login
    - **Emporia Vue**: `pyemvue` lib
    - **Tesla Powerwall**: `teslapy` lib
    - **Eversource utility**: download Green Button CSVs manually, parse — tedious
  - Returns: today_kwh, by_day (last 7), current_w, peak_w_today

## Polish (whenever)

- [ ] **Fold the chart sampler / style sampler examples into preview routes** so they're previewable too (e.g. `/charts`, `/styles` in addition to `/`)
- [ ] **Tighten any sections that look thin at the new 52-char width** — e.g. add columns to the tasks list, more weather forecast detail
- [ ] **A "minimal" report mode** for short receipts (e.g. `report --sections weather stocks ai_summary`) for printing twice a day without burning a foot of paper
- [ ] **Schedule it via cron** — README has the snippet; running it is a one-liner once we're happy with output

## Suggested next move

I'd attack in this order:
1. Commit current work (5 min)
2. `.env` file support (15 min) — pays for itself immediately
3. **tasks** (30 min) — easy win, same pattern as tallied, fills out a major section
4. **server via Prometheus** (30–60 min) — high informational value, you probably already have Prometheus running
5. **calendar via gcalcli** (60–90 min) — most user-visible "this is a real assistant" feature
6. **power** — once you decide on a data source

Want me to start at the top of that list?
