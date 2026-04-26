# CLAUDE.md

Context for AI assistants working in this repo. Keep this short and
load-bearing — anything that would make a future session redo work
already done.

## What this is

A Python module that prints daily reports to an Epson TM-m30III thermal
receipt printer at `192.168.1.147`. Intended to grow over time by adding
data sources and a scheduler.

## Hard-won facts about the physical printer

The printer is on the LAN at `192.168.1.147:9100` (raw ESC/POS). Web admin
on `:80`/`:443`, ePOS-Print API on `:8008`/`:8043`.

**Effective text width is narrower than the spec.** Font A is nominally 48
columns, but on this unit, mixed-content lines (label + bar + value) start
to feel "too long" past ~28 chars. Use the layout constants on
`ReceiptPrinter` rather than hard-coding widths:

- `CONTENT_WIDTH = 28` — for tables, KV lines, histograms
- `BAR_WIDTH = 12` — for the bar portion of any text chart
- `DIVIDER_WIDTH = 32` — for solid `=`/`-`/`*` dividers
- `IMAGE_WIDTH_PX = 512` — print head supports ~540, 512 dithers cleanly

If a chart starts wrapping, narrow the bar/content width before assuming
the printer config changed. We've already calibrated this.

**Other gotchas** (codified in `printer.py` / `styles.py`):

- Always send `ESC @` + `ESC { 0` at the top of every job (done in
  `ReceiptPrinter.__enter__`)
- CODE128 barcodes need a `{B` prefix (`styles.barcode` adds it if missing)
- QR codes should use the printer's native renderer (`native=True`)
- If paper feeds but doesn't print, the **roll is upside-down** — coated
  side must face the print head (down)

## Architecture

```
daily_report/
  printer.py    ReceiptPrinter (context manager) + constants + status query
  charts.py     Data viz functions, all take ReceiptPrinter as first arg
  styles.py     Formatting helpers (titles, sections, QR, barcode, table)
  report.py     Two-phase pipeline: collect data, then render sections
  cli.py        argparse CLI for ad-hoc printing
  sources/      one module per data source, each exposing summarize()
examples/
  chart_sampler.py  every chart on one receipt
  style_sampler.py  every formatting primitive on one receipt
```

Two key architectural decisions:

1. **Charts and styles are free functions taking a printer**, not methods
   on the printer. Keeps the printer class focused on transport and lets
   data sources compose chart calls freely.

2. **`report.py` is two-phase**: it collects all source data into a
   `collected: dict` first, then renders sections from that dict. The
   `ai_summary` source consumes `collected` after every other source has
   run, so it can synthesize across them. Section renderers are pure
   `(printer, data) -> None` — they don't fetch anything themselves.

## Source pattern

Each `daily_report/sources/<name>.py` exposes `summarize(...) -> dict`.
Conventions:

- Required fields go at the top of the dict; optional ones at the bottom.
- Stub sources return realistic sample data with `_stub: True`. Renderers
  detect this and print a "(sample data - not wired up yet)" line.
- Sources with auth requirements check env vars first; if missing, a
  stub source returns sample data, but a real source returns
  `{"error": "<what's missing>"}` (the renderer surfaces it).
- Long-running fetches accept `timeout=` and degrade gracefully on network
  errors so a single dead source can't block the whole report.

## Conventions

- All chart/style functions take `p: ReceiptPrinter` as the first positional
  argument.
- Functions print directly; they don't return strings or buffers.
- After a function returns, the printer state should be reset to plain
  left-aligned text. Set styles, print, then unset.
- Image widths default to `p.IMAGE_WIDTH_PX`. Allow overriding via
  `width_px=` kwarg.
- New data sources go under `daily_report/sources/` and produce dicts /
  dataclasses; the rendering layer in `report.py` (to be written) calls
  charts/styles to print them.

## Things to NOT do

- Don't widen text content past ~28 chars without re-checking on the
  physical printer first. We burned several iterations on this.
- Don't add error handling around `Network()` connect failures; let it
  raise. The user wants to see real failures, not silent retries.
- Don't add a `hostname` / discovery layer. The IP is static and lives
  on the constant.
- Don't migrate away from python-escpos — we evaluated and chose it over
  raw ESC/POS and the ePOS-Print HTTP API.

## Quick verification commands

```bash
# Check the printer is online
python -m daily_report.cli status

# Print everything (full sampler)
python -m daily_report.cli charts
python -m daily_report.cli styles
```
