"""Home power-consumption source.

STUB: returns sample data marked `_stub: True`. The user has not yet
specified the data source. Common options:

  - Sense (sense.com) — has an unofficial python client (sense_energy)
  - Emporia Vue — pyemvue
  - Tesla Powerwall / Solar — teslapy
  - Home Assistant — REST API on the homelab (probably the easiest)
  - Utility provider (Eversource) — manual scrape of green button CSV

Env vars to plumb through (when ready):
    POWER_PROVIDER     one of the above
    POWER_API_*        provider-specific creds

Expected return shape:
    {
        "today_kwh":       float,
        "yesterday_kwh":   float,
        "by_day":          [(YYYY-MM-DD, kwh), ...],   # last 7
        "current_w":       int,                         # live power draw
        "peak_w_today":    int,
    }
"""
from __future__ import annotations

import os
from datetime import date, timedelta


def summarize() -> dict:
    if not os.environ.get("POWER_PROVIDER"):
        today = date.today()
        sample_kwh = [42.5, 38.1, 41.2, 45.0, 39.8, 47.3, 44.1]
        return {
            "_stub": True,
            "today_kwh": sample_kwh[-1],
            "yesterday_kwh": sample_kwh[-2],
            "by_day": [
                ((today - timedelta(days=6 - i)).isoformat(), v)
                for i, v in enumerate(sample_kwh)
            ],
            "current_w": 1820,
            "peak_w_today": 4310,
        }
    raise NotImplementedError(
        "Power provider not yet wired up. Implement fetch in "
        "daily_report/sources/power.py and remove this raise."
    )
