"""Homelab service catalog source.

Reads the services.json catalog from the PersonalWebsite repo (the single
source of truth for what's running on the homelab) and optionally does
live HEAD checks to see which URLs respond.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

DEFAULT_CATALOG_PATH = Path(
    os.environ.get(
        "HOMELAB_CATALOG",
        Path.home() / "repos" / "PersonalWebsite" / "services.json",
    )
)


def load_catalog(path: Path = DEFAULT_CATALOG_PATH) -> dict:
    with open(path) as f:
        return json.load(f)


def _check_url(url: str, timeout: float) -> bool:
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 500
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return False


def summarize(
    *,
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    check_urls: bool = False,
    timeout: float = 2.0,
) -> dict:
    """Return a printable digest of the homelab.

    Shape:
        {
          "total":        int,
          "by_category":  [(category_title, count), ...],
          "categories":   [{"title": str, "count": int, "services": [name,...]}],
          "checks":       [(name, url, up: bool), ...]   # only if check_urls
          "up":           int,                            # only if check_urls
          "down":         int,                            # only if check_urls
        }
    """
    cat = load_catalog(catalog_path)
    cats = cat.get("categories", [])

    by_category: list[tuple[str, int]] = []
    categories_detail: list[dict] = []
    all_with_urls: list[tuple[str, str]] = []

    for c in cats:
        services = c.get("services", [])
        title = c.get("title", c.get("id", "?"))
        by_category.append((title, len(services)))
        categories_detail.append({
            "title": title,
            "count": len(services),
            "services": [s.get("name", "?") for s in services],
        })
        for s in services:
            url = s.get("url")
            if url:
                all_with_urls.append((s.get("name", "?"), url))

    out = {
        "total": sum(n for _, n in by_category),
        "by_category": by_category,
        "categories": categories_detail,
    }

    if check_urls and all_with_urls:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(
                lambda nu: (nu[0], nu[1], _check_url(nu[1], timeout)),
                all_with_urls,
            ))
        out["checks"] = results
        out["up"] = sum(1 for _, _, ok in results if ok)
        out["down"] = sum(1 for _, _, ok in results if not ok)

    return out
