"""Quote of the day via ZenQuotes (no auth).

Falls back to a small built-in list if the network is unavailable.
"""
from __future__ import annotations

import json
import random
import urllib.request

LOCAL_QUOTES = [
    ("The best way out is always through.", "Robert Frost"),
    ("Success is not final, failure is not fatal: it is the courage to continue that counts.", "Winston Churchill"),
    ("Do the hard jobs first. The easy jobs will take care of themselves.", "Dale Carnegie"),
    ("It does not matter how slowly you go as long as you do not stop.", "Confucius"),
    ("Quality is not an act, it is a habit.", "Aristotle"),
    ("Make it work, make it right, make it fast.", "Kent Beck"),
    ("Simplicity is the ultimate sophistication.", "Leonardo da Vinci"),
    ("Discipline equals freedom.", "Jocko Willink"),
]


def summarize(*, timeout: float = 5.0) -> dict:
    try:
        with urllib.request.urlopen(
            "https://zenquotes.io/api/today", timeout=timeout
        ) as resp:
            data = json.loads(resp.read())[0]
        return {"quote": data["q"], "author": data["a"], "source": "zenquotes"}
    except Exception:
        q, a = random.choice(LOCAL_QUOTES)
        return {"quote": q, "author": a, "source": "local"}
