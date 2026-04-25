"""GitHub activity source.

Shells out to the `gh` CLI (already authenticated on the host) rather than
managing tokens directly. Run `gh auth status` to verify.

Useful API endpoints we hit:
- /user                              -> profile counts
- /users/{u}/events?per_page=100     -> recent activity
- /search/issues?q=is:open+is:pr+author:@me           -> my open PRs
- /search/issues?q=is:open+is:pr+review-requested:@me -> review queue
- /users/{u}/repos?per_page=100      -> total stars + top repos
"""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone


def _gh_api(path: str) -> dict | list:
    """Call `gh api <path>` and parse JSON. Raises on non-zero exit."""
    out = subprocess.run(
        ["gh", "api", path],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def _gh_username() -> str:
    out = subprocess.run(
        ["gh", "api", "user", "--jq", ".login"],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def _parse_iso(s: str) -> datetime:
    # GitHub returns trailing Z; treat as UTC.
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _repo_name(url_or_full: str) -> str:
    """Extract just the repo name from either a repository_url or full name."""
    return url_or_full.rsplit("/", 1)[-1]


def summarize(*, lookback_hours: int = 24, top_n: int = 5) -> dict:
    """Return a printable digest of recent GitHub activity.

    Shape:
        {
          "user": "MCheli",
          "public_repos": int,
          "followers": int,
          "total_stars": int,
          "commits_recent": int,            # last `lookback_hours`
          "events_by_type": {type: count},  # last `lookback_hours`
          "lookback_hours": int,
          "open_prs": [(repo, title), ...],
          "review_queue": [(repo, title, author), ...],
          "top_repos": [(name, stars), ...],
        }
    """
    user = _gh_username()
    profile = _gh_api("user")

    # Events
    events = _gh_api(f"users/{user}/events?per_page=100")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    recent = [e for e in events if _parse_iso(e["created_at"]) >= cutoff]

    by_type = Counter(e["type"] for e in recent)
    commits_recent = sum(
        len(e.get("payload", {}).get("commits", []))
        for e in recent if e["type"] == "PushEvent"
    )

    # PRs
    open_prs = _gh_api(
        "search/issues?q=is%3Aopen+is%3Apr+author%3A%40me&per_page=10"
    )
    review_queue = _gh_api(
        "search/issues?q=is%3Aopen+is%3Apr+review-requested%3A%40me&per_page=10"
    )

    # Repos
    repos = _gh_api(f"users/{user}/repos?per_page=100&sort=updated")
    total_stars = sum(r["stargazers_count"] for r in repos)
    top_repos = sorted(
        repos, key=lambda r: r["stargazers_count"], reverse=True,
    )[:top_n]

    return {
        "user": user,
        "public_repos": profile["public_repos"],
        "followers": profile["followers"],
        "total_stars": total_stars,
        "commits_recent": commits_recent,
        "events_by_type": dict(by_type.most_common()),
        "lookback_hours": lookback_hours,
        "open_prs": [
            (_repo_name(pr["repository_url"]), pr["title"])
            for pr in open_prs.get("items", [])[:top_n]
        ],
        "review_queue": [
            (_repo_name(pr["repository_url"]), pr["title"], pr["user"]["login"])
            for pr in review_queue.get("items", [])[:top_n]
        ],
        "top_repos": [
            (r["name"], r["stargazers_count"]) for r in top_repos
        ],
    }
