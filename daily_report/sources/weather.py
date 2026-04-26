"""Weather source via wttr.in (no auth, no signup).

We hit the JSON endpoint (`?format=j1`) which gives current conditions,
today's hi/lo, and a 3-day forecast.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request


def summarize(location: str = "Ashland,MA") -> dict:
    url = f"https://wttr.in/{urllib.parse.quote(location)}?format=j1"
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())

    current = data["current_condition"][0]
    days = data["weather"]

    def _midday_desc(day: dict) -> str:
        # `hourly` has 8 entries (every 3h). Index 4 is roughly midday.
        return day["hourly"][min(4, len(day["hourly"]) - 1)]["weatherDesc"][0]["value"]

    return {
        "location": location,
        "current": {
            "temp_f": int(current["temp_F"]),
            "feels_f": int(current["FeelsLikeF"]),
            "desc": current["weatherDesc"][0]["value"],
            "humidity": int(current["humidity"]),
            "wind_mph": int(current["windspeedMiles"]),
        },
        "today": {
            "date": days[0]["date"],
            "max_f": int(days[0]["maxtempF"]),
            "min_f": int(days[0]["mintempF"]),
            "desc": _midday_desc(days[0]),
            "sunrise": days[0]["astronomy"][0]["sunrise"],
            "sunset": days[0]["astronomy"][0]["sunset"],
        },
        "forecast": [
            {
                "date": d["date"],
                "max_f": int(d["maxtempF"]),
                "min_f": int(d["mintempF"]),
                "desc": _midday_desc(d),
            }
            for d in days
        ],
    }
