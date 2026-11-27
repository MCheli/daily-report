"""Source for the user's finance dashboard at money.markcheli.com (mcheli/tallied).

Real implementation. Authenticates with `X-API-Key` (NOT `Authorization: Bearer`).
Falls back to sample data marked `_stub: True` if `TALLIED_API_KEY` is unset
so the layout still renders during development.

Env vars:
    TALLIED_API_KEY    required for live data
    TALLIED_API_URL    optional, defaults to https://money.markcheli.com

API shape we depend on (Tallied serves its API under /api/v1/):
    GET /api/v1/transactions/?from_date=yyyy-mm-dd&limit=500&offset=0
        -> {"items": [{"id","date","amount","merchant","category", ...}, ...],
            "total": int}
    Newest first; `limit` is capped at 500 server-side, so we page with
    `offset` until we have `total` items.
    `amount` is signed: negative = expense, positive = income.
    `date` is ISO yyyy-mm-dd.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

DEFAULT_API_URL = "https://money.markcheli.com"
PAGE_SIZE = 500     # server-side maximum for `limit`
MAX_PAGES = 20      # safety stop so a bad `total` can't loop forever


def _fetch(api_key: str, api_url: str, *, from_date: date,
           timeout: float = 10.0) -> list[dict]:
    items: list[dict] = []
    for page in range(MAX_PAGES):
        query = urllib.parse.urlencode({
            "from_date": from_date.isoformat(),
            "limit": PAGE_SIZE,
            "offset": page * PAGE_SIZE,
        })
        req = urllib.request.Request(
            f"{api_url.rstrip('/')}/api/v1/transactions/?{query}",
            headers={
                "X-API-Key": api_key,
                # Cloudflare in front of money.markcheli.com 403s the default
                # `Python-urllib/3.x` UA. Send something innocuous instead.
                "User-Agent": "daily-report/1.0 (+https://github.com/MCheli/daily-report)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
        batch = body.get("items", [])
        items.extend(batch)
        if len(batch) < PAGE_SIZE or len(items) >= body.get("total", 0):
            break
    return items


def summarize(*, days: int = 3, api_key: Optional[str] = None) -> dict:
    """Aggregate the last `days` of expenses into a printable digest.

    Returns a receipt-friendly view: the headline is a list of individual
    transactions over the window plus a total. We also keep the by-day
    and top-category aggregates available for callers that want them,
    but the renderer only uses `transactions_recent` and `total`.
    """
    api_key = api_key or os.environ.get("TALLIED_API_KEY")
    if not api_key:
        return _stub(days=days)

    api_url = os.environ.get("TALLIED_API_URL", DEFAULT_API_URL)
    today = date.today()
    cutoff = today - timedelta(days=days - 1)
    items = _fetch(api_key, api_url, from_date=cutoff)

    transactions_recent: list[dict] = []
    by_day_total: dict[str, float] = defaultdict(float)
    by_cat_total: dict[str, float] = defaultdict(float)
    tx_count = 0
    most_recent_date: Optional[date] = None

    for it in items:
        d_str = it.get("date")
        if not d_str:
            continue
        try:
            d = date.fromisoformat(d_str)
        except ValueError:
            continue
        if most_recent_date is None or d > most_recent_date:
            most_recent_date = d
        if d < cutoff:
            continue
        amt = it.get("amount", 0) or 0
        # Keep every transaction in the window (including income) so the
        # receipt-style list is honest. Aggregates below remain expense-only.
        transactions_recent.append({
            "date": d_str,
            "merchant": it.get("merchant") or "(unknown)",
            "amount": amt,
            "category": it.get("category"),
        })
        if amt >= 0:           # aggregates skip income
            continue
        spend = -amt
        by_day_total[d_str] += spend
        cat = it.get("category") or "Uncategorized"
        by_cat_total[cat] += spend
        tx_count += 1

    transactions_recent.sort(key=lambda t: t["date"], reverse=True)

    return {
        "total": round(sum(by_day_total.values()), 2),
        "transactions_recent": transactions_recent,
        "transactions": tx_count,
        "window_days": days,
        "most_recent_tx": most_recent_date.isoformat() if most_recent_date else None,
    }


def _stub(*, days: int) -> dict:
    today = date.today()
    sample = [
        ("Trader Joe's",        -42.18, "Groceries"),
        ("Anthropic, PBC",     -212.50, "Software"),
        ("Stop & Shop",         -86.50, "Groceries"),
    ][:days]
    return {
        "_stub": True,
        "total": round(-sum(t[1] for t in sample), 2),
        "transactions_recent": [
            {
                "date": (today - timedelta(days=i)).isoformat(),
                "merchant": m, "amount": amt, "category": cat,
            }
            for i, (m, amt, cat) in enumerate(sample)
        ],
        "transactions": len(sample),
        "window_days": days,
        "most_recent_tx": today.isoformat(),
    }
