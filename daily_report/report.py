"""Compose and print the daily report.

This is the rendering layer that ties data sources to chart/style
primitives. Add a new source by:

  1. Putting it under `daily_report/sources/<name>.py` with a
     `summarize()` function that returns a dict.
  2. Adding a `_section_<name>(p)` function here that pulls from the
     source and calls into charts/styles.
  3. Registering it in `SECTIONS` below.

Run with:
    python -m daily_report.report
    python -m daily_report.report --sections homelab
    python -m daily_report.report --check-urls       # live up/down checks
"""
from __future__ import annotations

import argparse
from datetime import datetime

from . import charts, styles
from .printer import ReceiptPrinter
from .sources import github, homelab


# ---------- sections ----------

def _section_homelab(p: ReceiptPrinter, *, check_urls: bool = False) -> None:
    data = homelab.summarize(check_urls=check_urls)

    styles.section_header(p, "HOMELAB")
    charts.kpi_card(p, "SERVICES TRACKED", data["total"])

    # Truncate long category titles so they fit our 28-char content width.
    short = lambda s: s.split(" (")[0][:14]
    items = [(short(name), count) for name, count in data["by_category"]]
    charts.horizontal_bars(p, "By category", items)

    if check_urls and "checks" in data:
        p.newline()
        charts.kpi_card(
            p, "REACHABILITY",
            f"{data['up']}/{data['up'] + data['down']}",
            delta_pct=None,
        )
        down = [(name, "down") for name, _, ok in data["checks"] if not ok]
        if down:
            styles.section_header(p, "DOWN")
            for name, _ in down:
                styles.kv_line(p, name, "DOWN", bold_value=True)
        else:
            styles.styled(p, "All services reachable.", align="center")


def _section_github(p: ReceiptPrinter, *, lookback_hours: int = 24 * 7) -> None:
    data = github.summarize(lookback_hours=lookback_hours)

    styles.section_header(p, "GITHUB")

    # Profile stat block
    styles.kv_line(p, "@" + data["user"], "")
    styles.kv_line(p, "Public repos", str(data["public_repos"]))
    styles.kv_line(p, "Total stars", str(data["total_stars"]))
    styles.kv_line(p, "Followers", str(data["followers"]))

    # Activity in the lookback window
    days = lookback_hours // 24
    label = f"COMMITS ({days}D)" if days >= 1 else f"COMMITS ({lookback_hours}H)"
    p.newline()
    charts.kpi_card(p, label, data["commits_recent"])

    if data["events_by_type"]:
        items = [
            (t.replace("Event", "")[:8], c)
            for t, c in list(data["events_by_type"].items())[:5]
        ]
        charts.horizontal_bars(p, "Activity by type", items)

    # Top repos
    if data["top_repos"]:
        p.newline()
        charts.leaderboard(
            p, "Top repos by stars",
            data["top_repos"],
            name_width=12, bar_width=6, value_fmt="{:>3}",
        )

    # Open PRs
    if data["open_prs"]:
        p.newline()
        styles.styled(p, "MY OPEN PRs", bold=True)
        for repo, title in data["open_prs"]:
            p.text(f"{repo[:10]:<10} {title[:17]}\n")

    # Review queue
    if data["review_queue"]:
        p.newline()
        styles.styled(p, "REVIEW QUEUE", bold=True)
        for repo, title, author in data["review_queue"]:
            p.text(f"{repo[:10]:<10} @{author[:8]}\n")
            p.text(f"  {title[:26]}\n")


SECTIONS = {
    "homelab": _section_homelab,
    "github": _section_github,
}


# ---------- driver ----------

def generate(
    sections: list[str] | None = None,
    *,
    check_urls: bool = False,
    github_lookback_hours: int = 24 * 7,
    title: str = "DAILY REPORT",
) -> None:
    sections = sections or list(SECTIONS.keys())
    section_kwargs: dict[str, dict] = {
        "homelab": {"check_urls": check_urls},
        "github":  {"lookback_hours": github_lookback_hours},
    }
    with ReceiptPrinter() as p:
        styles.title(p, title)
        styles.subtitle(p, datetime.now().strftime("%Y-%m-%d  %H:%M"))

        for name in sections:
            fn = SECTIONS.get(name)
            if fn is None:
                styles.section_header(p, name.upper())
                p.text(f"(unknown section: {name})\n")
                continue
            try:
                fn(p, **section_kwargs.get(name, {}))
            except Exception as e:
                styles.section_header(p, name.upper())
                p.text(f"(failed: {e})\n")

        p.newline()
        styles.subtitle(p, "End of report")
        p.feed(2)
        p.cut()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="daily-report-print")
    parser.add_argument(
        "--sections", nargs="+", default=None,
        help="subset of sections to include (default: all)",
    )
    parser.add_argument(
        "--check-urls", action="store_true",
        help="do live HEAD checks against service URLs",
    )
    parser.add_argument(
        "--github-lookback-hours", type=int, default=24 * 7,
        help="how far back the github section looks (default: 168h / 7d)",
    )
    parser.add_argument(
        "--title", default="DAILY REPORT",
    )
    args = parser.parse_args(argv)
    generate(
        args.sections,
        check_urls=args.check_urls,
        github_lookback_hours=args.github_lookback_hours,
        title=args.title,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
