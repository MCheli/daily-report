"""Source for the user's tasks app at tasks.markcheli.com (mcheli/tasks).

Real implementation. Auth is the per-user API-key model the tasks app
shipped at commit 9383600: mint a key in /settings, set the
`TASKS_API_KEY` env var, done. The header is `X-API-Key`.

Env vars (read at request time):
    TASKS_API_URL        optional, default https://tasks.markcheli.com
    TASKS_API_KEY        required for live data; falls back to stub if unset

Endpoints (see API_SPEC.md in mcheli/tasks):
    GET /api/cycles/current?category=personal       -> open tasks
    GET /api/cycles/current?category=professional   -> open tasks
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

DEFAULT_API_URL = "https://tasks.markcheli.com"
_USER_AGENT = "daily-report/1.0 (+https://github.com/MCheli/daily-report)"


def _get_json(url: str, api_key: str, *, timeout: float = 10.0):
    req = urllib.request.Request(
        url,
        headers={
            "X-API-Key": api_key,
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _fetch_current_cycle(api_url: str, api_key: str, category: str) -> dict:
    url = (
        f"{api_url.rstrip('/')}/api/cycles/current?"
        + urllib.parse.urlencode({"category": category})
    )
    return _get_json(url, api_key)


def summarize(*, top_n: int = 5) -> dict:
    """Aggregate open tasks across personal + professional cycles."""
    api_key = os.environ.get("TASKS_API_KEY")
    if not api_key:
        return _stub()

    api_url = os.environ.get("TASKS_API_URL", DEFAULT_API_URL)

    out_open: list[dict] = []
    by_cycle: list[tuple[str, int]] = []
    for cat in ("personal", "professional"):
        data = _fetch_current_cycle(api_url, api_key, cat)
        open_tasks = data.get("tasks", {}).get("open", []) or []
        by_cycle.append((cat, len(open_tasks)))
        for t in open_tasks:
            t["_cycle"] = cat
            out_open.append(t)

    out_open.sort(key=lambda t: (t.get("_cycle"), t.get("position", 0)))

    top_tasks: list[tuple[str, str, str]] = []
    for t in out_open[:top_n]:
        title = t.get("title", "(untitled)")[:24]
        cyc = t.get("_cycle", "")
        # The API doesn't surface priority/due fields today; using the cycle
        # as the secondary line keeps the renderer interface stable.
        top_tasks.append((title, cyc, "med"))

    return {
        "open_count": len(out_open),
        "by_cycle": by_cycle,
        "top_tasks": top_tasks,
    }


def _stub() -> dict:
    return {
        "_stub": True,
        "open_count": 12,
        "by_cycle": [("personal", 4), ("professional", 8)],
        "top_tasks": [
            ("Review homelab backups",   "personal",     "high"),
            ("Submit expense report",    "professional", "med"),
            ("Plan Q3 OKRs",             "professional", "med"),
            ("Email the contractor",     "personal",     "low"),
            ("Update tasks app README",  "personal",     "low"),
        ],
    }
