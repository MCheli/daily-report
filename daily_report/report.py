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


def _error_or_continue_silent(data: Optional[dict]) -> bool:
    """True if the section should be suppressed entirely (no header). Use
    when an empty/errored section shouldn't even print its title."""
    if data is None:
        return True
    return bool(data.get("error"))


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

    def _print_list(label: str, items: list[dict]) -> None:
        if not items:
            return
        styles.styled(p, f"{label} ({len(items)})", bold=True)
        # Layout: "[ ] " (4) + title (variable) + age column right-aligned.
        # Reserve 6 chars at the right for "(NNd*)" so titles can run up
        # to CONTENT_WIDTH - 4 - 1 - 6 = 21 chars at width 32.
        title_max = max(8, p.CONTENT_WIDTH - 4 - 1 - 6)
        for it in items:
            title = (it.get("title") or "(untitled)")[:title_max]
            d = int(it.get("days_open", 0))
            push = int(it.get("push_forward_count", 0) or 0)
            age = f"{d}d" + ("*" if push > 0 else "")
            age_str = f"({age})"
            pad = max(1, p.CONTENT_WIDTH - 4 - len(title) - len(age_str))
            p.text(f"[ ] {title}{' ' * pad}{age_str}\n")

    _print_list("PERSONAL",     data.get("personal") or [])
    if data.get("personal") and data.get("professional"):
        p.newline()
    _print_list("PROFESSIONAL", data.get("professional") or [])


def _section_tallied(p: ReceiptPrinter, data: dict) -> None:
    if _error_or_continue_silent(data):
        return
    recent = data.get("transactions_recent") or []
    if not recent:
        # Quiet days don't earn paper.
        return
    styles.section_header(p, "TALLIED")
    _stub_marker(p, data)
    days = data.get("window_days", 3)
    p.text(f"Last {days} days\n")
    p.divider("-")
    total = 0.0
    for tx in recent:
        date_s = tx["date"][5:]            # MM-DD
        merchant = (tx.get("merchant") or "?")[:24]
        amt = tx.get("amount", 0) or 0
        # Expense: $42.18    Income: +$42.18 (positive sign in the prefix col)
        if amt > 0:
            amt_str = f"+${amt:>7.2f}"
        else:
            amt_str = f"${-amt:>8.2f}"
            total += -amt
        # 5 (date) + 1 + 24 (merchant) + remaining for amount
        line_width = p.CONTENT_WIDTH
        pad = max(1, line_width - 5 - 1 - len(merchant) - len(amt_str))
        p.text(f"{date_s} {merchant}{' ' * pad}{amt_str}\n")
    p.divider("-")
    total_str = f"${total:>7.2f}"
    pad = max(1, p.CONTENT_WIDTH - len("TOTAL") - len(total_str))
    p.set(bold=True)
    p.text(f"TOTAL{' ' * pad}{total_str}\n")
    p.set(bold=False)


def _section_stocks(p: ReceiptPrinter, data: dict) -> None:
    styles.section_header(p, "STOCKS")
    if _error_or_continue(p, data):
        return
    name = data.get("name") or data["ticker"]
    p.text(f"{data['ticker']} - {name[:24]}\n")
    charts.kpi_card(
        p, f"{data['ticker']} CLOSE", data["current"], prefix="$",
    )
    # Day / Week / Month change on a single line - replaces the kpi_card
    # delta (which would otherwise be hardcoded "vs last week").
    p.text(
        f"Day {data['day_change_pct']:+.1f}%  "
        f"Wk {data['week_change_pct']:+.1f}%  "
        f"Mo {data['month_change_pct']:+.1f}%\n"
    )
    history = data.get("history") or []
    if history:
        from datetime import datetime as _dt
        xs = [_dt.fromisoformat(d) for d, _ in history]
        ys = [c for _, c in history]
        charts.line_chart(
            p,
            f"{data['ticker']} close - last {len(history)} days",
            xs, ys,
            ylabel="$",
        )


def _section_calendar(p: ReceiptPrinter, data: dict) -> None:
    styles.section_header(p, "CALENDAR")
    if _error_or_continue(p, data):
        return
    _stub_marker(p, data)
    events = data.get("next_events") or []
    if not events:
        p.text("nothing on the calendar in the next 90 days\n")
        return

    from datetime import date as _date, datetime as _dt
    today = _date.today()

    for i, ev in enumerate(events):
        if i > 0:
            p.newline()    # blank line between events for breathing room

        try:
            dt = _dt.fromisoformat(ev["start"])
        except (KeyError, ValueError):
            p.text(f"  {ev.get('start', '?')}  {ev.get('title', '')[:24]}\n")
            continue

        days_until = (dt.date() - today).days
        if days_until == 0:
            rel = "today"
        elif days_until == 1:
            rel = "tomorrow"
        elif days_until < 0:
            rel = "past"
        else:
            rel = f"in {days_until}d"

        # Header row: bold "Fri May 1  8:00 PM" on the left, "in 6d" right.
        date_str = dt.strftime("%a %b %d")
        time_str = dt.strftime("%I:%M %p").lstrip("0")
        left = f"{date_str}  {time_str}"
        pad = max(1, p.CONTENT_WIDTH - len(left) - len(rel))
        p.set(bold=True)
        p.text(f"{left}{' ' * pad}{rel}\n")
        p.set(bold=False)

        # Title row(s), word-wrapped under a 3-space indent.
        title = ev.get("title", "(no title)")
        duration_min = ev.get("duration_min") or 0
        if duration_min >= 24 * 60:
            days_long = duration_min // (24 * 60)
            title = f"{title}  [{days_long}d trip]"
        _wrap_lines(p, title, indent=3)

        # Location: skip URLs (useless on paper); keep physical addresses.
        loc = ev.get("location")
        if loc and not loc.startswith(("http://", "https://")):
            _wrap_lines(p, f"@ {loc}", indent=3)


def _wrap_lines(p: ReceiptPrinter, text: str, *, indent: int = 0) -> None:
    """Word-wrap `text` to `p.CONTENT_WIDTH` with a leading indent on every line."""
    pad = " " * indent
    width = p.CONTENT_WIDTH - indent
    words = text.split()
    line = ""
    for w in words:
        if not line:
            line = w
        elif len(line) + 1 + len(w) > width:
            p.text(pad + line + "\n")
            line = w
        else:
            line += " " + w
    if line:
        p.text(pad + line + "\n")


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
    styles.kv_line(p, "Today",   f"{today.get('min_f', 0)}F / {today.get('max_f', 0)}F")
    styles.kv_line(p, "Sunrise", today.get("sunrise", ""))
    styles.kv_line(p, "Sunset",  today.get("sunset",  ""))

    forecast = data.get("forecast") or []
    if len(forecast) > 1:
        p.newline()
        styles.styled(p, "5-day forecast", bold=True)
        # Horizontal layout, one column per day - reads left-to-right like
        # a weather widget.
        cols = forecast[:5]
        col_w = p.CONTENT_WIDTH // len(cols)
        # Row 1: day-of-week
        p.set(bold=True)
        p.text("".join(f"{d.get('day_of_week','?'):^{col_w}}" for d in cols) + "\n")
        p.set(bold=False)
        # Row 2: high/low
        p.text("".join(
            f"{f'{d['max_f']}/{d['min_f']}F':^{col_w}}" for d in cols
        ) + "\n")
        # Row 3: short condition (truncate to col_w-1 to keep a 1-char gutter)
        p.text("".join(
            f"{d.get('desc','')[:col_w-1]:^{col_w}}" for d in cols
        ) + "\n")
        # Matplotlib bar chart of daily highs reinforces the trend visually.
        charts.bar_chart(
            p, "Daily highs (F)",
            [d["day_of_week"] for d in cols],
            [d["max_f"] for d in cols],
        )


def _section_power(p: ReceiptPrinter, data: dict) -> None:
    styles.section_header(p, "POWER")
    if _error_or_continue(p, data):
        return
    _stub_marker(p, data)
    # At 7 AM, "today" is mostly empty so make YESTERDAY the headline.
    charts.kpi_card(p, "YESTERDAY", data.get("yesterday_kwh", 0.0), suffix=" kWh")

    # 7-day chart as a matplotlib bar image (matches the weather forecast
    # chart's aesthetic), with day-of-week labels.
    by_day = data.get("by_day") or []
    if by_day:
        from datetime import date as _date
        labels: list[str] = []
        values: list[float] = []
        for d_str, kwh in by_day:
            try:
                dow = _date.fromisoformat(d_str).strftime("%a")
            except ValueError:
                dow = d_str[5:]
            labels.append(dow)
            values.append(kwh)
        charts.bar_chart(p, "kWh per day", labels, values)

    # Live draw is genuinely "now" so keep it; today_kwh / peak_today
    # are early-morning noise so we drop them at render time.
    p.newline()
    styles.kv_line(p, "Live draw", f"{data['current_w']:,} W")


def _section_server(p: ReceiptPrinter, data: dict) -> None:
    styles.section_header(p, "SERVER")
    if _error_or_continue(p, data):
        return
    _stub_marker(p, data)

    cpu_pct = float(data.get("cpu_pct", 0))
    mem_used = float(data.get("mem_used_gb", 0))
    mem_total = float(data.get("mem_total_gb", 1)) or 1.0
    mem_pct = mem_used / mem_total * 100
    disk_pct = float(data.get("disk_used_pct", 0))
    cont_up = int(data.get("containers_up", 0))
    cont_total = int(data.get("containers_total", 0)) or cont_up

    # Top: identifying info as a key/value table.
    styles.kv_line(p, "Host",       data.get("host", "?"))
    styles.kv_line(p, "Uptime",     f"{data.get('uptime_days', 0):.1f}d")
    styles.kv_line(
        p, "Load 1/5/15",
        f"{data.get('load_1m', 0)} "
        f"{data.get('load_5m', 0)} "
        f"{data.get('load_15m', 0)}",
    )
    cont_str = f"{cont_up}/{cont_total}"
    if cont_up < cont_total:
        cont_str += "  *DOWN"
    styles.kv_line(p, "Containers", cont_str, bold_value=(cont_up < cont_total))

    # Bottom: resource utilization with progress bars + threshold flag.
    p.newline()
    bar_w = 20
    rows = [
        ("CPU",    cpu_pct,  70),
        ("Memory", mem_pct,  80),
        ("Disk",   disk_pct, 85),
    ]
    for name, pct, threshold in rows:
        filled = int(round(bar_w * min(max(pct, 0), 100) / 100))
        bar = "[" + "#" * filled + "-" * (bar_w - filled) + "]"
        flag = "  *HIGH" if pct >= threshold else ""
        p.text(f"{name:<8} {int(round(pct)):>3}%  {bar}{flag}\n")


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


def _header_subtitle(collected: dict) -> str:
    """Day of week + a countdown to the next calendar event when we have one."""
    now = datetime.now()
    today = now.strftime("%a %b %d").upper()      # "THU APR 25"
    cal = collected.get("calendar") or {}
    events = cal.get("next_events") or []
    if not events:
        return today
    try:
        first = events[0]
        from datetime import datetime as _dt
        start = _dt.fromisoformat(first["start"])
        days_until = (start.date() - now.date()).days
        title_short = (first.get("title") or "").strip()[:18]
        if not title_short:
            return today
        if days_until == 0:
            tag = f"today: {title_short}"
        elif days_until == 1:
            tag = f"tomorrow: {title_short}"
        else:
            tag = f"{days_until}d to {title_short}"
        return f"{today}  -  {tag}"
    except (KeyError, ValueError, TypeError):
        return today


# ---------- registry ----------

# Each entry: (collector, renderer)
# `collector` takes the merged `kwargs` dict and returns a data dict.
COLLECTORS: dict[str, Callable[[dict], dict]] = {
    "homelab":    lambda kw: homelab.summarize(check_urls=kw.get("check_urls", False)),
    "github":     lambda kw: github.summarize(lookback_hours=kw.get("github_lookback_hours", 168)),
    "tasks":      lambda kw: tasks.summarize(),
    "tallied":    lambda kw: tallied.summarize(days=kw.get("tallied_days", 3)),
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

# Tuned per the post-launch review:
#   - top of receipt is what to act on (weather, calendar, tasks)
#   - ai_summary is the synthesized read of *everything* (still has access
#     to all collected data; rendering it 4th just means the punchline is
#     near the top)
#   - power/server/stocks/tallied are skim-or-skip
#   - motivation goes at the bottom: pleasant filler, not load-bearing
#   - homelab and github dropped from default print (mostly static / vanity);
#     still callable via /trigger with {"sections": [...]}.
DEFAULT_ORDER = [
    "ai_summary",   # the punchline first - always reflects ALL collected data
    "weather",
    "calendar",
    "tasks",
    "power",
    "server",
    "stocks",
    "tallied",
    "motivation",
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
        styles.subtitle(p, _header_subtitle(collected))

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
    parser.add_argument("--tallied-days", type=int, default=3,
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
