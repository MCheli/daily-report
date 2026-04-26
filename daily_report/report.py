"""Compose and print the daily report.

Two-phase pipeline:

  1. Collect: each registered source's `summarize()` runs and its result
     is stashed in `collected[name]`. Failures are caught and stored as
     `{"error": str}` so a single dead source can't kill the run.
  2. Render: for each section in `sections`, the registered renderer
     receives the collected `data` and prints to a ReceiptPrinter.

The `ai_summary` source is special — it runs *after* the others and
receives the full `collected` dict as its input.

Add a new source:
  1. Drop a module under `daily_report/sources/<name>.py` exposing a
     `summarize(...)` function that returns a dict.
  2. Add a `_section_<name>(p, data)` here.
  3. Register the source in `COLLECTORS` and the renderer in `SECTIONS`.

Run:
    python -m daily_report.cli report
    python -m daily_report.cli report --sections weather stocks ai_summary
"""
from __future__ import annotations

import argparse
from datetime import datetime
from typing import Callable, Optional

from . import charts, styles
from .printer import ReceiptPrinter
from .sources import (
    ai_summary,
    calendar,
    github,
    homelab,
    motivation,
    power,
    server,
    stocks,
    tallied,
    tasks,
    weather,
)


# ---------- helpers used by multiple renderers ----------

def _stub_marker(p: ReceiptPrinter, data: dict) -> None:
    if data.get("_stub"):
        styles.styled(p, "(sample data - not wired up yet)", align="center")


def _error_or_continue(p: ReceiptPrinter, data: Optional[dict]) -> bool:
    """Return True if an error message was printed and the renderer should bail."""
    if data is None:
        p.text("(no data)\n")
        return True
    if "error" in data and data.get("error"):
        p.text(f"(failed: {data['error']})\n")
        return True
    return False


# ---------- section renderers ----------

def _section_homelab(p: ReceiptPrinter, data: dict) -> None:
    styles.section_header(p, "HOMELAB")
    if _error_or_continue(p, data):
        return
    charts.kpi_card(p, "SERVICES TRACKED", data["total"])
    short = lambda s: s.split(" (")[0][:14]
    items = [(short(name), count) for name, count in data["by_category"]]
    charts.horizontal_bars(p, "By category", items)
    if "checks" in data:
        p.newline()
        charts.kpi_card(
            p, "REACHABILITY",
            f"{data['up']}/{data['up'] + data['down']}",
        )
        down = [name for name, _, ok in data["checks"] if not ok]
        if down:
            p.newline()
            styles.styled(p, "DOWN", bold=True)
            for name in down:
                styles.kv_line(p, name, "DOWN", bold_value=True)


def _section_github(p: ReceiptPrinter, data: dict) -> None:
    styles.section_header(p, "GITHUB")
    if _error_or_continue(p, data):
        return
    styles.kv_line(p, "@" + data["user"], "")
    styles.kv_line(p, "Public repos", str(data["public_repos"]))
    styles.kv_line(p, "Total stars", str(data["total_stars"]))
    styles.kv_line(p, "Followers", str(data["followers"]))
    days = data["lookback_hours"] // 24
    label = f"COMMITS ({days}D)" if days >= 1 else f"COMMITS ({data['lookback_hours']}H)"
    p.newline()
    charts.kpi_card(p, label, data["commits_recent"])
    if data["events_by_type"]:
        items = [
            (t.replace("Event", "")[:8], c)
            for t, c in list(data["events_by_type"].items())[:5]
        ]
        charts.horizontal_bars(p, "Activity by type", items)
    if data["top_repos"]:
        p.newline()
        charts.leaderboard(
            p, "Top repos by stars", data["top_repos"],
            name_width=12, bar_width=28, value_fmt="{:>3}",
        )
    if data["open_prs"]:
        p.newline()
        styles.styled(p, "MY OPEN PRs", bold=True)
        for repo, title in data["open_prs"]:
            p.text(f"{repo[:10]:<10} {title[:17]}\n")
    if data["review_queue"]:
        p.newline()
        styles.styled(p, "REVIEW QUEUE", bold=True)
        for repo, title, author in data["review_queue"]:
            p.text(f"{repo[:10]:<10} @{author[:8]}\n")
            p.text(f"  {title[:26]}\n")


def _section_tasks(p: ReceiptPrinter, data: dict) -> None:
    styles.section_header(p, "TASKS")
    if _error_or_continue(p, data):
        return
    _stub_marker(p, data)
    charts.kpi_card(p, "OPEN TASKS", data["open_count"])
    charts.horizontal_bars(p, "By cycle", data["by_cycle"])
    p.newline()
    styles.styled(p, "Top tasks", bold=True)
    for title, due, prio in data["top_tasks"]:
        prio_mark = {"high": "!!", "med": "* ", "low": "  "}.get(prio, "  ")
        p.text(f"{prio_mark}{title[:20]}\n")
        p.text(f"   due: {due}\n")


def _section_tallied(p: ReceiptPrinter, data: dict) -> None:
    styles.section_header(p, "TALLIED")
    if _error_or_continue(p, data):
        return
    _stub_marker(p, data)
    days = data.get("window_days", 7)
    charts.kpi_card(p, f"SPEND ({days}D)", data["total"], prefix="$")
    daily = [(d[5:], v) for d, v in data["by_day"]]   # MM-DD labels
    charts.horizontal_bars(p, "By day", daily, name_width=5, value_width=7)
    if data.get("top_categories"):
        p.newline()
        charts.leaderboard(
            p, "Top categories", data["top_categories"],
            name_width=14, bar_width=24, value_fmt="${:>5,.0f}",
        )
    p.newline()
    styles.kv_line(p, "Transactions", str(data["transactions"]))
    if data.get("most_recent_tx"):
        styles.kv_line(p, "Last tx", data["most_recent_tx"])


def _section_stocks(p: ReceiptPrinter, data: dict) -> None:
    styles.section_header(p, "STOCKS")
    if _error_or_continue(p, data):
        return
    name = data.get("name") or data["ticker"]
    p.text(f"{data['ticker']} - {name[:24]}\n")
    charts.kpi_card(
        p, f"{data['ticker']} CLOSE",
        data["current"], delta_pct=data["day_change_pct"], prefix="$",
    )
    # Performance bars (handle negative values by sign-character bars)
    p.newline()
    styles.styled(p, "Performance", bold=True)
    perf = [
        ("Day",   data["day_change_pct"]),
        ("Week",  data["week_change_pct"]),
        ("Month", data["month_change_pct"]),
    ]
    mx = max((abs(v) for _, v in perf), default=1) or 1
    perf_bar_width = 36
    for label, v in perf:
        n = int(round(perf_bar_width * abs(v) / mx))
        bar_str = ("+" if v >= 0 else "-") * n
        p.text(f"{label:<6}{bar_str:<{perf_bar_width}} {v:>+6.2f}%\n")
    p.newline()
    styles.kv_line(p, "Volume", f"{data['volume']:,}")
    if data.get("history"):
        p.newline()
        charts.sparkline(
            p, "30d close",
            [c for _, c in data["history"]],
        )


def _section_calendar(p: ReceiptPrinter, data: dict) -> None:
    styles.section_header(p, "CALENDAR")
    if _error_or_continue(p, data):
        return
    _stub_marker(p, data)
    styles.kv_line(p, "Today",     str(data["today_count"]))
    styles.kv_line(p, "This week", str(data["week_count"]))
    # Events-per-day bar chart for the upcoming events
    if data["next_events"]:
        from collections import Counter
        per_day = Counter(ev["start"][:10] for ev in data["next_events"])
        items = [(d[5:], c) for d, c in sorted(per_day.items())]
        p.newline()
        charts.horizontal_bars(p, "Events per day", items, name_width=5, value_width=2)
    p.newline()
    styles.styled(p, "Up next", bold=True)
    for ev in data["next_events"]:
        when = ev["start"].replace("T", " ")
        p.text(f"{when[5:16]}  {ev['title'][:18]}\n")
        if ev.get("location"):
            p.text(f"   @ {ev['location'][:28]}\n")


def _section_motivation(p: ReceiptPrinter, data: dict) -> None:
    styles.section_header(p, "QUOTE OF THE DAY")
    if _error_or_continue(p, data):
        return
    p.set(align="center")
    # Wrap manually to ~28 chars
    quote = data["quote"]
    words = quote.split()
    line = ""
    for w in words:
        if len(line) + len(w) + 1 > p.CONTENT_WIDTH:
            p.text(line.rstrip() + "\n")
            line = w + " "
        else:
            line += w + " "
    if line.strip():
        p.text(line.rstrip() + "\n")
    p.text(f"\n- {data['author']}\n")
    p.set(align="left")


def _section_weather(p: ReceiptPrinter, data: dict) -> None:
    styles.section_header(p, "WEATHER")
    if _error_or_continue(p, data):
        return
    cur = data["current"]
    today = data["today"]
    p.set(align="center")
    p.text(f"{data['location']}\n")
    p.set(bold=True, double_height=True, double_width=True)
    p.text(f"{cur['temp_f']}F\n")
    p.set(bold=False, double_height=False, double_width=False)
    p.text(f"{cur['desc']}\n")
    p.text(f"feels {cur['feels_f']}F  hum {cur['humidity']}%\n")
    p.text(f"wind {cur['wind_mph']} mph\n")
    p.set(align="left")
    p.newline()
    styles.kv_line(p, "Today",   f"{today['min_f']}F / {today['max_f']}F")
    styles.kv_line(p, "Sunrise", today["sunrise"])
    styles.kv_line(p, "Sunset",  today["sunset"])
    if len(data["forecast"]) > 1:
        p.newline()
        styles.styled(p, "Forecast", bold=True)
        upcoming = data["forecast"][1:6]
        for day in upcoming:
            label = day["date"][5:]   # MM-DD
            p.text(f"{label}  {day['min_f']:>3}F/{day['max_f']:>3}F  {day['desc'][:10]}\n")
        # Bar chart of daily highs to show warming/cooling trend
        p.newline()
        charts.horizontal_bars(
            p, "High temps (F)",
            [(day["date"][5:], day["max_f"]) for day in upcoming],
            name_width=5,
        )


def _section_power(p: ReceiptPrinter, data: dict) -> None:
    styles.section_header(p, "POWER")
    if _error_or_continue(p, data):
        return
    _stub_marker(p, data)
    charts.kpi_card(p, "TODAY", data["today_kwh"], suffix=" kWh")
    daily = [(d.split("-")[-1], v) for d, v in data["by_day"]]
    charts.horizontal_bars(p, "By day (kWh)", daily, name_width=4, value_width=6)
    p.newline()
    styles.kv_line(p, "Live draw", f"{data['current_w']:,} W")
    styles.kv_line(p, "Peak today", f"{data['peak_w_today']:,} W")


def _section_server(p: ReceiptPrinter, data: dict) -> None:
    styles.section_header(p, "SERVER")
    if _error_or_continue(p, data):
        return
    _stub_marker(p, data)
    p.text(f"{data['host']}\n")
    styles.kv_line(p, "Uptime", f"{data['uptime_days']:.1f}d")
    styles.kv_line(p, "Load 1/5/15",
                   f"{data['load_1m']} {data['load_5m']} {data['load_15m']}")
    p.newline()
    charts.progress(p, "Resources", [
        ("CPU",  data["cpu_pct"] / 100),
        ("Mem",  data["mem_used_gb"] / data["mem_total_gb"]),
        ("Disk", data["disk_used_pct"] / 100),
    ])
    p.newline()
    styles.kv_line(p, "Containers",
                   f"{data['containers_up']}/{data['containers_total']}")


def _section_ai_summary(p: ReceiptPrinter, data: dict) -> None:
    styles.section_header(p, "DAILY SUMMARY")
    if _error_or_continue(p, data):
        return
    p.set(align="left")
    text = data.get("summary", "")
    # Wrap to content width
    for paragraph in text.split("\n"):
        words = paragraph.split()
        line = ""
        for w in words:
            if len(line) + len(w) + 1 > p.CONTENT_WIDTH:
                p.text(line.rstrip() + "\n")
                line = w + " "
            else:
                line += w + " "
        if line.strip():
            p.text(line.rstrip() + "\n")
    if data.get("model"):
        p.newline()
        p.set(align="center")
        p.text(f"-- {data['model']} --\n")
        p.set(align="left")


# ---------- registry ----------

# Each entry: (collector, renderer)
# `collector` takes the merged `kwargs` dict and returns a data dict.
COLLECTORS: dict[str, Callable[[dict], dict]] = {
    "homelab":    lambda kw: homelab.summarize(check_urls=kw.get("check_urls", False)),
    "github":     lambda kw: github.summarize(lookback_hours=kw.get("github_lookback_hours", 168)),
    "tasks":      lambda kw: tasks.summarize(),
    "tallied":    lambda kw: tallied.summarize(days=kw.get("tallied_days", 7)),
    "stocks":     lambda kw: stocks.summarize(ticker=kw.get("stock_ticker", "PTC")),
    "calendar":   lambda kw: calendar.summarize(),
    "motivation": lambda kw: motivation.summarize(),
    "weather":    lambda kw: weather.summarize(location=kw.get("weather_location", "Ashland,MA")),
    "power":      lambda kw: power.summarize(),
    "server":     lambda kw: server.summarize(),
}

SECTIONS: dict[str, Callable[[ReceiptPrinter, dict], None]] = {
    "homelab":    _section_homelab,
    "github":     _section_github,
    "tasks":      _section_tasks,
    "tallied":    _section_tallied,
    "stocks":     _section_stocks,
    "calendar":   _section_calendar,
    "motivation": _section_motivation,
    "ai_summary": _section_ai_summary,    # special: collected after others
    "weather":    _section_weather,
    "power":      _section_power,
    "server":     _section_server,
}

DEFAULT_ORDER = [
    "tasks", "tallied", "stocks", "calendar",
    "motivation", "ai_summary", "weather",
    "power", "server", "homelab", "github",
]


# ---------- driver ----------

def generate(
    sections: list[str] | None = None,
    *,
    title: str = "DAILY REPORT",
    printer_factory=None,
    **kwargs,
) -> None:
    """Compose and print the report.

    `printer_factory` is a callable returning a context-manager printer
    (defaults to ReceiptPrinter). The preview module passes a factory
    that produces a PreviewPrinter, so the same code path can drive
    either output without changes to the section renderers.
    """
    sections = sections or DEFAULT_ORDER
    factory = printer_factory or ReceiptPrinter

    # Phase 1: collect all source data (skip ai_summary; depends on the rest)
    collected: dict[str, dict] = {}
    for name in sections:
        if name == "ai_summary":
            continue
        collector = COLLECTORS.get(name)
        if collector is None:
            collected[name] = {"error": f"unknown source: {name}"}
            continue
        try:
            collected[name] = collector(kwargs)
        except NotImplementedError as e:
            collected[name] = {"error": str(e)}
        except Exception as e:
            collected[name] = {"error": f"{type(e).__name__}: {e}"}

    if "ai_summary" in sections:
        try:
            collected["ai_summary"] = ai_summary.summarize(collected)
        except Exception as e:
            collected["ai_summary"] = {"error": f"{type(e).__name__}: {e}"}

    # Phase 2: render
    with factory() as p:
        styles.title(p, title)
        styles.subtitle(p, datetime.now().strftime("%Y-%m-%d  %H:%M"))

        for name in sections:
            renderer = SECTIONS.get(name)
            if renderer is None:
                styles.section_header(p, name.upper())
                p.text(f"(unknown section: {name})\n")
                continue
            try:
                renderer(p, collected.get(name, {}))
            except Exception as e:
                styles.section_header(p, name.upper())
                p.text(f"(render failed: {type(e).__name__}: {e})\n")

        p.newline()
        styles.subtitle(p, "End of report")
        # The auto-cutter takes a few mm above the actual cut line; without
        # enough leader the last text line gets sliced off. 6 lines of feed
        # at Font B is the empirically safe minimum.
        p.feed(6)
        p.cut()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="daily-report-print")
    parser.add_argument(
        "--sections", nargs="+", default=None,
        help=f"subset of sections (default order: {' '.join(DEFAULT_ORDER)})",
    )
    parser.add_argument(
        "--check-urls", action="store_true",
        help="for the homelab section, do live HEAD checks against URLs",
    )
    parser.add_argument(
        "--github-lookback-hours", type=int, default=168,
        help="window for the github section (default: 168 / 7d)",
    )
    parser.add_argument("--stock-ticker", default="PTC")
    parser.add_argument("--weather-location", default="Ashland,MA")
    parser.add_argument("--tallied-days", type=int, default=7,
                        help="window for the tallied section (default: 7)")
    parser.add_argument("--title", default="DAILY REPORT")
    args = parser.parse_args(argv)
    generate(
        args.sections,
        title=args.title,
        check_urls=args.check_urls,
        github_lookback_hours=args.github_lookback_hours,
        stock_ticker=args.stock_ticker,
        weather_location=args.weather_location,
        tallied_days=args.tallied_days,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
