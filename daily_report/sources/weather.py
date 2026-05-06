"""Weather source via Open-Meteo (no auth, no signup, 7+ day forecasts).

Switched from wttr.in because wttr caps at 3 days. Open-Meteo gives us
arbitrary horizons and proper sunrise/sunset.

Two endpoints used:
  1. https://geocoding-api.open-meteo.com/v1/search  -- "Ashland, MA" -> lat/lon
  2. https://api.open-meteo.com/v1/forecast          -- the actual forecast

Weather codes are WMO codes (0-99); we map to short human strings.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

_USER_AGENT = "daily-report/1.0 (+https://github.com/MCheli/daily-report)"

# Process-lifetime cache of geocoding results so we don't pay for a
# second HTTP call every render once we've resolved a place.
_GEOCODE_CACHE: dict[str, tuple[float, float, str]] = {}

# Hardcoded fallback so the morning print doesn't rely on Open-Meteo's
# geocoder being healthy at 5 AM. Used only when geocoding fails for
# the default location string.
_DEFAULT_FALLBACKS: dict[str, tuple[float, float, str]] = {
    "ashland,ma": (42.2611, -71.4636, "Ashland, Massachusetts, US"),
}


# ---------- WMO weather code -> short description ----------
# https://open-meteo.com/en/docs (Variables -> WMO Weather interpretation codes)
_WMO = {
    0:  "Clear",
    1:  "Mostly clear",
    2:  "Partly cloudy",
    3:  "Overcast",
    45: "Fog",
    48: "Fog",
    51: "Drizzle",
    53: "Drizzle",
    55: "Drizzle",
    56: "Frz drizzle",
    57: "Frz drizzle",
    61: "Rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Frz rain",
    67: "Frz rain",
    71: "Snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Showers",
    81: "Showers",
    82: "Heavy show.",
    85: "Snow show.",
    86: "Snow show.",
    95: "T-storm",
    96: "T-storm/hail",
    99: "T-storm/hail",
}


def _wmo_to_text(code: int | None) -> str:
    if code is None:
        return ""
    return _WMO.get(int(code), f"code {code}")


def _get_json(url: str, *, timeout: float = 10.0, attempts: int = 3) -> dict:
    """GET JSON with a few retries. Open-Meteo flakes occasionally on the
    first cold call of the day - one transient failure shouldn't kill
    the whole weather section."""
    last_err: Exception | None = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError,
                json.JSONDecodeError) as e:
            last_err = e
            if i < attempts - 1:
                time.sleep(0.5 * (i + 1))   # 0.5s, 1.0s, ...
    assert last_err is not None
    raise last_err


def _geocode(name: str) -> tuple[float, float, str]:
    """Resolve a free-form place name to (lat, lon, resolved_name).

    Sources, in priority order:
      1. WEATHER_LAT + WEATHER_LON env vars (skip the network entirely)
      2. process-lifetime cache from a prior successful resolution
      3. Open-Meteo's geocoding endpoint
      4. hardcoded fallback for known default locations

    Open-Meteo's geocoder doesn't honor "City, State"-formatted strings,
    so when there's a comma we search by the city alone and filter by
    state (admin1).
    """
    # 1. Explicit env override
    env_lat = os.environ.get("WEATHER_LAT")
    env_lon = os.environ.get("WEATHER_LON")
    if env_lat and env_lon:
        try:
            return float(env_lat), float(env_lon), name
        except ValueError:
            pass

    # 2. Cache
    cache_key = name.lower().strip()
    if cache_key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[cache_key]

    city = name
    state_hint: str | None = None
    if "," in name:
        city, _, state_hint = name.partition(",")
        city = city.strip()
        state_hint = state_hint.strip()

    # 3. Open-Meteo geocoder. If it fails, fall back to a hardcoded
    # default for known locations so the morning print isn't held
    # hostage by a third-party flake.
    try:
        url = (
            "https://geocoding-api.open-meteo.com/v1/search?"
            + urllib.parse.urlencode({"name": city, "count": 50, "format": "json"})
        )
        data = _get_json(url)
        results = data.get("results") or []
    except Exception:
        results = []

    if not results:
        if cache_key in _DEFAULT_FALLBACKS:
            return _DEFAULT_FALLBACKS[cache_key]
        raise RuntimeError(f"could not geocode location: {name!r}")

    if state_hint:
        # Match against admin1 either by full name or 2-letter abbreviation.
        # Open-Meteo only returns full state names, so do a case-insensitive
        # contains/startswith on whichever style the user passed.
        wanted = state_hint.upper()
        STATES = {
            "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
            "CA": "California", "CO": "Colorado", "CT": "Connecticut",
            "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
            "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
            "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
            "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
            "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
            "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
            "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
            "NY": "New York", "NC": "North Carolina", "ND": "North Dakota",
            "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
            "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
            "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
            "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
            "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
        }
        full_state = STATES.get(wanted, state_hint).lower()
        for r in results:
            if (r.get("admin1") or "").lower() == full_state:
                results = [r]
                break

    r = results[0]
    label_parts = [r.get("name"), r.get("admin1"), r.get("country_code")]
    label = ", ".join(p for p in label_parts if p)
    out = (float(r["latitude"]), float(r["longitude"]), label)
    _GEOCODE_CACHE[cache_key] = out
    return out


def summarize(location: str = "Ashland,MA", *, days: int = 5) -> dict:
    lat, lon, resolved = _geocode(location)

    forecast_url = (
        "https://api.open-meteo.com/v1/forecast?"
        + urllib.parse.urlencode({
            "latitude": lat,
            "longitude": lon,
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "weather_code,wind_speed_10m"
            ),
            "daily": (
                "temperature_2m_max,temperature_2m_min,weather_code,"
                "sunrise,sunset"
            ),
            "forecast_days": days,
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": "auto",
        })
    )
    raw = _get_json(forecast_url)

    cur = raw.get("current", {})
    daily = raw.get("daily", {})

    def _parse_date(s: str) -> datetime:
        # daily.time entries are YYYY-MM-DD (local TZ); sunrise/sunset are ISO.
        return datetime.fromisoformat(s)

    forecast: list[dict] = []
    times = daily.get("time", []) or []
    maxes = daily.get("temperature_2m_max", []) or []
    mins  = daily.get("temperature_2m_min", []) or []
    codes = daily.get("weather_code", []) or []
    sunrises = daily.get("sunrise", []) or []
    sunsets  = daily.get("sunset", []) or []

    for i, t in enumerate(times):
        try:
            d = _parse_date(t)
        except ValueError:
            continue
        forecast.append({
            "date": t,                                # YYYY-MM-DD
            "day_of_week": d.strftime("%a"),          # Mon, Tue, ...
            "max_f": int(round(float(maxes[i]))) if i < len(maxes) else 0,
            "min_f": int(round(float(mins[i]))) if i < len(mins) else 0,
            "desc": _wmo_to_text(codes[i]) if i < len(codes) else "",
            "sunrise": sunrises[i][11:16] if i < len(sunrises) else "",
            "sunset":  sunsets[i][11:16]  if i < len(sunsets)  else "",
        })

    today = forecast[0] if forecast else {}

    return {
        "location": resolved or location,
        "current": {
            "temp_f":   int(round(float(cur.get("temperature_2m", 0)))),
            "feels_f":  int(round(float(cur.get("apparent_temperature", 0)))),
            "desc":     _wmo_to_text(cur.get("weather_code")),
            "humidity": int(round(float(cur.get("relative_humidity_2m", 0)))),
            "wind_mph": int(round(float(cur.get("wind_speed_10m", 0)))),
        },
        "today": today,
        "forecast": forecast,    # `days` entries, including today as forecast[0]
    }
