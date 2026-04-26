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
from datetime import datetime, timezone

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


def summarize() -> dict:
    """Return ALL open tasks across personal + professional cycles, with
    enough metadata for the renderer to show two lists with checkboxes
    and days-open."""
    api_key = os.environ.get("TASKS_API_KEY")
    if not api_key:
        return _stub()

    api_url = os.environ.get("TASKS_API_URL", DEFAULT_API_URL)
    now = datetime.now(timezone.utc)

    by_category: dict[str, list[dict]] = {"personal": [], "professional": []}
    for cat in ("personal", "professional"):
        data = _fetch_current_cycle(api_url, api_key, cat)
        open_tasks = data.get("tasks", {}).get("open", []) or []
        for t in sorted(open_tasks, key=lambda x: x.get("position", 0)):
            created = t.get("created_at")
            days_open = 0
            if created:
                try:
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    days_open = max(0, (now - created_dt).days)
                except ValueError:
                    pass
            by_category[cat].append({
                "title": t.get("title") or "(untitled)",
                "days_open": days_open,
                "push_forward_count": int(t.get("push_forward_count", 0) or 0),
            })

    return {
        "personal": by_category["personal"],
        "professional": by_category["professional"],
        "open_count": sum(len(v) for v in by_category.values()),
    }


def _stub() -> dict:
    return {
        "_stub": True,
        "open_count": 5,
        "personal": [
            {"title": "Review homelab backups", "days_open": 3, "push_forward_count": 0},
            {"title": "Email the contractor",   "days_open": 1, "push_forward_count": 0},
            {"title": "Update tasks app README","days_open": 5, "push_forward_count": 1},
        ],
        "professional": [
            {"title": "Submit expense report",  "days_open": 1, "push_forward_count": 0},
            {"title": "Plan Q3 OKRs",           "days_open": 7, "push_forward_count": 2},
        ],
    }
