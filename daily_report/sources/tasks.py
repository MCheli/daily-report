"""Source for the user's tasks app at tasks.markcheli.com (mcheli/tasks).

STUB: returns realistic sample data marked `_stub: True`. To wire up, replace
the body of `summarize()` to hit the tasks API. The likely shape:

    GET https://tasks.markcheli.com/api/tasks?status=open
    Authorization: Bearer <TASKS_API_TOKEN>

Env vars to plumb through:
    TASKS_API_URL    e.g. https://tasks.markcheli.com/api
    TASKS_API_TOKEN  bearer token

Expected return shape (keep stable for the renderer):
    {
        "open_count":  int,
        "by_cycle":    [(cycle_name, count), ...],
        "top_tasks":   [(title, due, priority), ...],
    }
"""
from __future__ import annotations

import os


def summarize() -> dict:
    if not os.environ.get("TASKS_API_URL"):
        return {
            "_stub": True,
            "open_count": 12,
            "by_cycle": [("today", 4), ("week", 5), ("later", 3)],
            "top_tasks": [
                ("Review homelab backups",   "today", "high"),
                ("Submit expense report",    "today", "med"),
                ("Plan Q3 OKRs",             "this week", "med"),
                ("Email the contractor",     "tomorrow", "low"),
                ("Update tasks app README",  "this week", "low"),
            ],
        }
    raise NotImplementedError(
        "Tasks API client not yet wired up. Implement HTTP fetch in "
        "daily_report/sources/tasks.py and remove this raise."
    )
