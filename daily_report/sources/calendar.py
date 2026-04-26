"""Google Calendar source for the next few events.

STUB: returns sample data marked `_stub: True`. Wiring this up has two
realistic paths:

  1. Google Calendar API directly — google-api-python-client + an OAuth
     credentials.json + a stored refresh token. Most flexible.
  2. Or use `gcalcli` if installed:
        gcalcli agenda --tsv --details=description tomorrow "1 week"
     and parse stdout. Simpler, no oauth dance to manage in this repo.

Env vars to plumb through (when ready):
    GCAL_CALENDAR_ID    primary or specific calendar id
    GCAL_CREDENTIALS    path to oauth credentials.json
    GCAL_TOKEN          path to refresh token

Expected return shape:
    {
        "next_events": [
            {"start": ISO8601, "title": str, "location": str|None,
             "duration_min": int},
            ...
        ],
        "today_count":   int,
        "week_count":    int,
    }
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta


def summarize(*, n: int = 5) -> dict:
    if not os.environ.get("GCAL_CREDENTIALS"):
        # Sample calendar starting "now"
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
                for title, s, dur, loc in sample[:n]
            ],
            "today_count": 2,
            "week_count": 5,
        }
    raise NotImplementedError(
        "Google Calendar client not yet wired up. Implement OAuth + fetch "
        "in daily_report/sources/calendar.py and remove this raise."
    )
