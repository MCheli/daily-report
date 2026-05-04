"""Google Calendar source via the ICS secret-URL feed.

Why ICS instead of gcalcli / OAuth?
- We deploy on a headless homelab server, not a workstation.
- gcalcli requires an interactive OAuth dance the first time it runs,
  which doesn't work without a browser.
- Service accounts don't work for personal Gmail (Workspace only).
- Google publishes a per-calendar "Secret address in iCal format" URL
  that returns the full calendar with no auth beyond keeping the URL
  itself secret. Read-only, exactly what a daily report needs.

How to get the URL:
    Google Calendar -> Settings (gear) -> Settings -> select your calendar
    in the left sidebar -> "Integrate calendar" -> copy the
    "Secret address in iCal format" URL.

Env vars:
    CALENDAR_ICS_URL   the secret iCal URL above. Falls back to stub if unset.
                       Accepts a comma-separated list to merge multiple
                       calendars (e.g. personal + shared birthdays + US
                       holidays). Events from all feeds are merged and
                       sorted chronologically; the renderer doesn't care
                       which calendar an event came from.

Returns the same shape the renderer was already wired against:
    {
      "next_events":  [{"start": ISO, "title": str,
                        "duration_min": int, "location": str|None}, ...],
      "today_count":  int,
      "week_count":   int,
    }
"""
from __future__ import annotations

import os
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Optional

_USER_AGENT = "daily-report/1.0 (+https://github.com/MCheli/daily-report)"


def _fetch_ics(url: str, *, timeout: float = 10.0) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Accept": "text/calendar"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _parse_events(ics_text: str, *, horizon_days: int = 14) -> list[dict]:
    """Parse VEVENT blocks from an iCalendar feed, expanding recurrences.

    `icalendar.walk("VEVENT")` returns each VEVENT exactly once at its
    original DTSTART — so a yearly-recurring birthday anchored to e.g.
    2021-07-15 just looks like a 2021 event and gets filtered out as
    "in the past". `recurring_ical_events` materialises RRULE/RDATE/
    EXDATE/RECURRENCE-ID into concrete occurrences within a window,
    which is the only way the family-birthdays feed surfaces anything.
    """
    from icalendar import Calendar  # lazy import; only needed when wired
    import recurring_ical_events

    cal = Calendar.from_ical(ics_text)
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=horizon_days)
    local_tz = datetime.now().astimezone().tzinfo

    events: list[dict] = []
    for component in recurring_ical_events.of(cal).between(now, horizon):
        start = component.get("dtstart")
        if start is None:
            continue
        start_val = start.dt
        # All-day events arrive as `date` rather than `datetime`. Store them
        # at midnight LOCAL (not UTC) so astimezone() round-trips don't slide
        # them onto the previous evening — a birthday on May 5 should display
        # as "May 5", not "May 4 at 8:00 PM".
        all_day = not isinstance(start_val, datetime)
        if all_day:
            start_dt = datetime.combine(start_val, datetime.min.time(),
                                        tzinfo=local_tz)
        else:
            start_dt = start_val
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)

        end = component.get("dtend")
        duration_min = 0
        if end is not None:
            end_dt = end.dt
            if isinstance(end_dt, datetime):
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
            else:
                end_dt = datetime.combine(end_dt, datetime.min.time(),
                                          tzinfo=timezone.utc)
            duration_min = max(0, int((end_dt - start_dt).total_seconds() // 60))

        title = str(component.get("summary") or "(no title)")
        location = component.get("location")
        events.append({
            "start": start_dt.astimezone().isoformat(timespec="minutes"),
            "title": title,
            "duration_min": duration_min,
            "location": str(location) if location else None,
            "all_day": all_day,
            "_start_dt": start_dt,
        })

    events.sort(key=lambda e: e["_start_dt"])
    return events


def summarize(*, horizon_days: int = 90, top_n: int = 5) -> dict:
    """Return the next `top_n` events merged across all configured ICS feeds."""
    raw = os.environ.get("CALENDAR_ICS_URL")
    if not raw:
        return _stub(top_n=top_n)

    urls = [u.strip() for u in raw.split(",") if u.strip()]
    events: list[dict] = []
    failures: list[str] = []
    for url in urls:
        try:
            ics_text = _fetch_ics(url)
            events.extend(_parse_events(ics_text, horizon_days=horizon_days))
        except Exception as e:
            failures.append(f"{type(e).__name__}: {e}")

    if failures and not events:
        # Every feed failed — surface the error rather than silently empty.
        return {"error": "calendar fetch failed: " + "; ".join(failures)}

    # Re-sort the merged list (each feed is sorted, but interleaving isn't).
    events.sort(key=lambda e: e["_start_dt"])

    today = date.today()
    week_end = today + timedelta(days=7)
    today_count = sum(1 for e in events if e["_start_dt"].date() == today)
    week_count  = sum(1 for e in events if today <= e["_start_dt"].date() < week_end)

    next_events = []
    for e in events[:top_n]:
        ev = {k: v for k, v in e.items() if not k.startswith("_")}
        next_events.append(ev)

    return {
        "next_events": next_events,
        "today_count": today_count,
        "week_count":  week_count,
    }


def _stub(*, top_n: int = 5) -> dict:
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    sample = [
        ("Daily standup",            now + timedelta(hours=1),  15, "Zoom"),
        ("1:1 with manager",         now + timedelta(hours=3),  30, None),
        ("Architecture review",      now + timedelta(days=1, hours=2), 60, "Conf Rm 2"),
        ("Dentist appointment",      now + timedelta(days=2, hours=4), 45, "Ashland"),
        ("Quarterly planning",       now + timedelta(days=3, hours=1), 90, "Boston HQ"),
    ]
    return {
        "_stub": True,
        "next_events": [
            {
                "start": s.isoformat(timespec="minutes"),
                "title": title,
                "duration_min": dur,
                "location": loc,
            }
            for title, s, dur, loc in sample[:top_n]
        ],
        "today_count": 2,
        "week_count": 5,
    }
