# daily-report

Print daily reports to an Epson TM-m30III thermal receipt printer.

This repo seeds a Python module (`daily_report/`) with the chart and formatting
primitives needed to compose a printed report, plus two runnable example
"samplers" that show every primitive on a single receipt.

The intent is to grow this over time by adding data sources (homelab metrics,
GitHub activity, calendar agenda, server alerts, etc.) and a scheduler that
prints a report on a regular cadence.

## Hardware

| Setting | Value |
|---|---|
| Model | Epson TM-m30III (P/N C31CK50012) |
| IP | `192.168.1.147` |
| Raw ESC/POS port | `9100` |
| Web admin | `https://192.168.1.147` (self-signed) |
| Paper | 80 mm thermal roll |

## Setup

```bash
cd ~/repos/daily-report
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Quick start

```python
from daily_report import ReceiptPrinter, charts, styles

with ReceiptPrinter() as p:
    styles.title(p, "DAILY REPORT")
    styles.subtitle(p, "2026-04-25")

    charts.kpi_card(p, "REVENUE TODAY", 12438.55, delta_pct=12.3, prefix="$")

    charts.horizontal_bars(p, "Sales by region", [
        ("US", 142), ("EU", 98), ("APAC", 52),
    ])

    charts.sparkline(p, "Sign-ups", [40, 42, 51, 48, 60, 72, 68])

    p.feed(2)
    p.cut()
```

## CLI

```bash
# diagnostics
python -m daily_report.cli status

# print every chart type
python -m daily_report.cli charts

# print every formatting primitive
python -m daily_report.cli styles

# one-offs
python -m daily_report.cli kpi "Revenue" 12438.55 --delta 12.3
python -m daily_report.cli text "hello" "world"
python -m daily_report.cli qr "https://markcheli.com"
```

## Module layout

```
daily_report/
  printer.py     ReceiptPrinter context manager + layout constants + status
  charts.py      Data viz: kpi_card, horizontal_bars, leaderboard, progress,
                 histogram, stacked_100, sparkline, line_chart, bar_chart,
                 heatmap
  styles.py      Formatting: title, subtitle, kicker, section_header,
                 divider_decorative, styled, kv_line, receipt_table, qr,
                 barcode
  cli.py         argparse CLI

examples/
  chart_sampler.py    every chart primitive on one receipt
  style_sampler.py    every formatting primitive on one receipt
```

## What we learned about this printer

These are tuned defaults for our specific physical unit. They live as
constants on `ReceiptPrinter` so all chart and style functions pick them
up automatically.

| Constant | Value | Why |
|---|---|---|
| `CONTENT_WIDTH` | 28 | Mixed-content lines (label + bar + value) feel "too long" past ~28 chars on this unit, even though Font A nominally supports 48. |
| `BAR_WIDTH` | 12 | Sweet spot for text bars — readable proportions inside a 24-char content line. |
| `DIVIDER_WIDTH` | 32 | Solid `=`/`-`/`*` dividers print fine at this width. |
| `IMAGE_WIDTH_PX` | 512 | Print head supports ~540 px; 512 leaves a small right margin and dithers cleanly. |

Other gotchas:

- **Thermal paper has a coated side.** If the printer feeds paper but prints
  nothing, the roll is loaded upside-down. Scratch with a coin to find the
  coated side; load it facing down (toward the print head).
- **CODE128 barcodes** need a code-set prefix. `styles.barcode()` auto-prepends
  `{B` if missing.
- **Always reset on connect.** `ReceiptPrinter.__enter__` sends `ESC @` (init)
  and `ESC { 0` (upside-down off) so prior job state can't leak in.
- **QR codes** use the printer's native renderer (`native=True` in python-escpos).
  Faster and sharper than rasterising in PIL.

## Status / diagnostics

```python
with ReceiptPrinter() as p:
    print(p.status())
# {'online': True, 'cover_open': False, 'paper_present': True,
#  'error': False, 'raw': {1: 0x16, 2: 0x12, 3: 0x12, 4: 0x12}}
```

A clean baseline reads back as `0x16 / 0x12 / 0x12 / 0x12` for the four
DLE-EOT queries (printer / offline cause / error / paper sensor).

## Composing the report

`daily_report/report.py` is the rendering layer. It reads from
`daily_report/sources/`, calls into `charts` / `styles`, and prints.

```bash
# print every registered section in DEFAULT_ORDER
python -m daily_report.cli report

# subset
python -m daily_report.cli report --sections weather stocks ai_summary

# tune per-source knobs
python -m daily_report.cli report --check-urls \
    --github-lookback-hours 720 \
    --stock-ticker AAPL \
    --weather-location "Boston,MA"
```

## Adding a new data source

1. Drop a module under `daily_report/sources/<name>.py` exposing a
   `summarize(...)` function that returns a plain dict.
2. Add a `_section_<name>(p)` function in `daily_report/report.py` that
   pulls from the source and calls into `charts` / `styles`.
3. Register it in the `SECTIONS` dict at the bottom of `report.py`.

Sources currently shipped:

**Real (no setup needed):**
- `sources/homelab.py` — reads `services.json` from PersonalWebsite,
  optionally does live HEAD checks via `summarize(check_urls=True)`.
- `sources/github.py` — shells out to the `gh` CLI (uses your existing
  auth) for profile, recent activity, open PRs, review queue, top repos.
- `sources/weather.py` — wttr.in JSON (no auth). Defaults to Ashland, MA.
  Returns current conditions + 5-day forecast.
- `sources/stocks.py` — yfinance (no auth). Default ticker `PTC`.
  Includes 30-day close history for sparklines.
- `sources/motivation.py` — ZenQuotes (no auth) with a built-in fallback
  list when the network is unavailable.

**AI:**
- `sources/ai_summary.py` — calls Claude Haiku 4.5 via the Anthropic SDK
  with the rest of the day's data and gets back a short synthesized
  paragraph. Requires `ANTHROPIC_API_KEY`; falls back to a "disabled"
  message when the key isn't set so the layout still prints.

**Stubbed (return sample data marked `_stub: True` until wired up):**
- `sources/tasks.py` — for tasks.markcheli.com. Needs `TASKS_API_URL`
  and `TASKS_API_TOKEN` plus an HTTP client.
- `sources/tallied.py` — for money.markcheli.com. Tallied uses Google
  SSO so will need either a service-account token or an SSO-exempt
  endpoint.
- `sources/calendar.py` — Google Calendar. Either oauth via
  google-api-python-client + a stored refresh token, or shell out to
  `gcalcli`.
- `sources/power.py` — home power consumption. The data source isn't
  picked yet (Sense, Emporia Vue, Powerwall, Home Assistant, etc.).
- `sources/server.py` — homelab resource summary. Best path is querying
  the existing Prometheus/`node_exporter` series via `PROM_URL`.

Each stub source prints a "(sample data - not wired up yet)" subtitle
under its section header so it's obvious what's real vs placeholder.

Rough pattern for adding GitHub activity, for example:

```python
# daily_report/sources/github.py
def summarize(token):
    ...  # hit the GH API
    return {"opened": 4, "merged": 7, "review_queue": [("repo-a", 3), ("repo-b", 1)]}

# daily_report/report.py
from .sources import github

def _section_github(p):
    data = github.summarize(token=os.environ["GITHUB_TOKEN"])
    styles.section_header(p, "GITHUB")
    charts.kpi_card(p, "PRs MERGED TODAY", data["merged"])
    charts.horizontal_bars(p, "Review queue", data["review_queue"])

SECTIONS["github"] = _section_github
```

## Scheduling

The simplest way to print on a cadence is cron. The `with ReceiptPrinter()`
block opens its own TCP connection per run — there's no daemon to manage.

```cron
# crontab -e   (every weekday at 8 AM)
0 8 * * 1-5  cd /Users/mcheli/repos/daily-report && .venv/bin/python -m daily_report.cli report >> /tmp/daily-report.log 2>&1
```

If you'd rather schedule a remote agent (Claude Code routine), the same
`python -m daily_report.cli report` invocation works from any working
directory, and writes its full diagnostic output to stdout.

For development, you can also call `daily_report.report.generate()`
directly from a Python REPL or notebook to test composition without
re-running the CLI.
