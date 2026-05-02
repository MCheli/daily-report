"""Home power consumption via Home Assistant.

Pulls today's kWh, current draw, peak draw, and a 7-day daily breakdown
from the `home.markcheli.com` Home Assistant install. Auth is a
long-lived access token (Bearer).

Entities used (set up in this user's HA install):
    sensor.total_mains_watts        current power, W (state_class: measurement)
    sensor.total_mains_energy       today's kWh so far (state_class: total -
                                    a utility_meter helper that resets at
                                    midnight)

Env vars:
    HOME_ASSISTANT_URL    default https://home.markcheli.com
    HOME_ASSISTANT_TOKEN  long-lived access token (required for live data)

The HA REST history endpoint requires URL-encoded timestamps and *must*
include `end_time` for ranges longer than ~1 day, otherwise it silently
caps to a 24h window. Both gotchas are handled here.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

DEFAULT_HA_URL = "https://home.markcheli.com"
POWER_ENTITY = "sensor.total_mains_watts"
ENERGY_ENTITY = "sensor.total_mains_energy"
_USER_AGENT = "daily-report/1.0 (+https://github.com/MCheli/daily-report)"


def _get(url: str, token: str, *, timeout: float = 15.0):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _state(base_url: str, token: str, entity_id: str) -> dict:
    return _get(f"{base_url.rstrip('/')}/api/states/{entity_id}", token)


def _history(
    base_url: str, token: str, entity_id: str,
    start: datetime, end: datetime,
) -> list[dict]:
    """Return a flat list of state samples for the given entity & window."""
    start_iso = urllib.parse.quote(start.isoformat(timespec="seconds"), safe="")
    end_iso = urllib.parse.quote(end.isoformat(timespec="seconds"), safe="")
    url = (
        f"{base_url.rstrip('/')}/api/history/period/{start_iso}"
        f"?filter_entity_id={entity_id}"
        f"&minimal_response&end_time={end_iso}"
    )
    data = _get(url, token)
    return data[0] if data and data[0] else []


def _safe_float(s: dict) -> float | None:
    try:
        return float(s["state"])
    except (KeyError, ValueError, TypeError):
        return None


def summarize(*, days: int = 7) -> dict:
    """Pull today's kWh, current/peak W, and last `days` daily totals.

    The energy entity is consumed as a raw reading and we compute per-day
    deltas client-side. This way it doesn't matter whether the sensor is:
      - daily-reset (utility_meter): each day's total = max value that day
      - monotonically increasing (raw kWh counter): each day's total =
        today's last value - yesterday's last value
    A negative delta (would imply a reset) is treated as the post-reset
    "today's consumption so far," which is exactly today's last value.
    """
    token = os.environ.get("HOME_ASSISTANT_TOKEN")
    if not token:
        return _stub(days=days)

    base_url = os.environ.get("HOME_ASSISTANT_URL", DEFAULT_HA_URL)

    try:
        # Live current draw
        watts_state = _state(base_url, token, POWER_ENTITY)
        current_w = _safe_float(watts_state) or 0.0

        # Current energy reading (could be cumulative or daily-reset).
        energy_state = _state(base_url, token, ENERGY_ENTITY)
        current_energy = _safe_float(energy_state) or 0.0

        now = datetime.now(timezone.utc)
        # Pull `days + 1` calendar days of history so we have a comparison
        # point for the earliest day in the chart.
        start = now - timedelta(days=days + 1)

        energy_history = _history(base_url, token, ENERGY_ENTITY, start, now)

        # Take the LAST value seen within each local date (or the MAX,
        # which is equivalent for both monotonic and daily-reset sensors).
        last_per_day: dict[date, float] = {}
        for s in energy_history:
            ts_str = s.get("last_changed") or s.get("last_updated")
            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            v = _safe_float(s)
            if v is None:
                continue
            d = ts.astimezone().date()
            if d not in last_per_day or v > last_per_day[d]:
                last_per_day[d] = v

        # Build daily deltas. For a monotonic counter, delta is the day's
        # consumption. For a daily-reset sensor, delta would go negative
        # at midnight rollover -> treat that as "the day's total IS the
        # day's max."
        sorted_days = sorted(last_per_day.keys())
        daily_kwh: dict[date, float] = {}
        for i, d in enumerate(sorted_days):
            if i == 0:
                continue   # need a previous day to diff against
            delta = last_per_day[d] - last_per_day[sorted_days[i - 1]]
            if delta < 0:
                delta = last_per_day[d]    # post-reset
            daily_kwh[d] = delta

        # Today's consumption so far: current reading minus yesterday's
        # last value, with the same negative-means-reset rule.
        today_local = datetime.now().date()
        yesterday = today_local - timedelta(days=1)
        prev = last_per_day.get(yesterday)
        if prev is None:
            today_kwh = current_energy
        else:
            today_kwh = current_energy - prev
            if today_kwh < 0:
                today_kwh = current_energy
        # Make sure today's bucket reflects the live "so far" value too.
        daily_kwh[today_local] = today_kwh

        by_day: list[tuple[str, float]] = []
        for offset in range(days - 1, -1, -1):
            d = today_local - timedelta(days=offset)
            by_day.append((d.isoformat(), round(daily_kwh.get(d, 0.0), 2)))

        yesterday_kwh = daily_kwh.get(yesterday, 0.0)

        # Peak watts today (since local midnight) - unchanged.
        local_midnight = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ).astimezone()
        midnight_utc = local_midnight.astimezone(timezone.utc)
        peak_w = 0.0
        for s in _history(base_url, token, POWER_ENTITY, midnight_utc, now):
            v = _safe_float(s)
            if v is not None and v > peak_w:
                peak_w = v
        peak_w = max(peak_w, current_w)

        return {
            "today_kwh": round(today_kwh, 2),
            "yesterday_kwh": round(yesterday_kwh, 2),
            "by_day": by_day,
            "current_w": int(round(current_w)),
            "peak_w_today": int(round(peak_w)),
        }
    except Exception as e:
        return {"error": f"home-assistant fetch failed: {type(e).__name__}: {e}"}


def _stub(*, days: int = 7) -> dict:
    today = date.today()
    sample = [42.5, 38.1, 41.2, 45.0, 39.8, 47.3, 44.1][:days]
    return {
        "_stub": True,
        "today_kwh": sample[-1],
        "yesterday_kwh": sample[-2] if len(sample) >= 2 else 0,
        "by_day": [
            ((today - timedelta(days=days - 1 - i)).isoformat(), v)
            for i, v in enumerate(sample)
        ],
        "current_w": 1820,
        "peak_w_today": 4310,
    }
