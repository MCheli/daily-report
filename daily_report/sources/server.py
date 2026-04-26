"""Homelab server resource summary (mcheli/83rr-poweredge).

Queries Prometheus directly. The 83rr-poweredge stack scrapes:
  - node-exporter   (host metrics: load, cpu, mem, disk)
  - cadvisor        (per-container metrics)
  - nginx-exporter  (nginx stats)

When daily-report runs *on* the homelab in its own container alongside
the monitoring stack, it should hit Prometheus on the docker network
at `http://prometheus:9090` (no nginx, no auth). For other deployment
scenarios (e.g. behind the LAN-only nginx-fronted endpoint) set
PROM_URL and optionally PROM_AUTH explicitly.

Env vars:
    PROM_URL    base Prometheus URL (default: http://prometheus:9090)
    PROM_AUTH   optional value for the `Authorization` header, e.g.
                "Basic <base64(user:pass)>" if going through nginx auth

Falls back to sample data marked `_stub: True` if PROM_URL is unreachable
or unset on the local machine.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

DEFAULT_PROM_URL = "http://prometheus:9090"
_USER_AGENT = "daily-report/1.0 (+https://github.com/MCheli/daily-report)"


def _query(url: str, expr: str, *, auth: str | None = None,
           timeout: float = 5.0) -> float | None:
    """Run an instant Prometheus query, return the first sample value or None."""
    full = f"{url.rstrip('/')}/api/v1/query?{urllib.parse.urlencode({'query': expr})}"
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    if auth:
        headers["Authorization"] = auth
    req = urllib.request.Request(full, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    if data.get("status") != "success":
        return None
    result = data.get("data", {}).get("result", [])
    if not result:
        return None
    try:
        return float(result[0]["value"][1])
    except (KeyError, IndexError, ValueError, TypeError):
        return None


def _query_count(url: str, expr: str, *, auth: str | None = None,
                 timeout: float = 5.0) -> int:
    """Run an instant query and return the number of result series."""
    full = f"{url.rstrip('/')}/api/v1/query?{urllib.parse.urlencode({'query': expr})}"
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    if auth:
        headers["Authorization"] = auth
    req = urllib.request.Request(full, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return len(data.get("data", {}).get("result", []) or [])


def summarize() -> dict:
    """Pull a snapshot of host load, CPU, memory, disk, and container counts."""
    url = os.environ.get("PROM_URL")
    if not url:
        # When deployed on-host, the operator should set PROM_URL or rely on
        # the docker DNS default. On a dev laptop nothing is reachable, so
        # return stub data rather than blocking on a long timeout.
        return _stub()
    auth = os.environ.get("PROM_AUTH")

    try:
        load1  = _query(url, "node_load1",  auth=auth)  or 0.0
        load5  = _query(url, "node_load5",  auth=auth)  or 0.0
        load15 = _query(url, "node_load15", auth=auth)  or 0.0

        # CPU % busy: 100 - average idle over 1m, across cpus
        cpu_pct = _query(
            url,
            '100 - avg(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100',
            auth=auth,
        ) or 0.0

        # Memory in GB
        mem_total = _query(url, "node_memory_MemTotal_bytes",     auth=auth) or 0.0
        mem_avail = _query(url, "node_memory_MemAvailable_bytes", auth=auth) or 0.0
        mem_used  = mem_total - mem_avail

        # Disk on the root filesystem
        disk_size = _query(
            url, 'node_filesystem_size_bytes{mountpoint="/"}',  auth=auth,
        ) or 0.0
        disk_avail = _query(
            url, 'node_filesystem_avail_bytes{mountpoint="/"}', auth=auth,
        ) or 0.0
        disk_used_pct = (
            ((disk_size - disk_avail) / disk_size * 100) if disk_size else 0.0
        )

        # Uptime in days. Compute the diff server-side so we get a single
        # consistent answer (no clock-skew between two separate queries).
        # Try a few metric names because node-exporter versions vary.
        uptime_seconds: float | None = None
        for expr in (
            "time() - node_boot_time_seconds",
            "time() - node_boot_time",                # older exporters
            "node_time_seconds - node_boot_time_seconds",
        ):
            v = _query(url, expr, auth=auth)
            if v is not None and v > 0:
                uptime_seconds = v
                break
        uptime_days: float | None
        if uptime_seconds is None:
            uptime_days = None      # signal "metric unavailable" to the renderer
        else:
            uptime_days = uptime_seconds / 86400

        # Container counts via cadvisor: each running container exposes one
        # series for `container_last_seen{name="..."}`. We count *series*
        # rather than wrapping in `count(...)` — `count(...)` collapses to
        # a single series whose value is the count, which would always read
        # back as 1 series.
        containers_up = _query_count(
            url, 'container_last_seen{name!=""}', auth=auth,
        )
        # Stopped containers don't appear in cadvisor's recent series, so
        # we have no "total" reference unless a separate exporter publishes
        # one. For now `total == up` and the renderer's *DOWN flag stays
        # quiet.
        containers_total = containers_up

        return {
            "host": "83rr-poweredge",
            "uptime_days": round(uptime_days, 2),
            "load_1m":  round(load1,  2),
            "load_5m":  round(load5,  2),
            "load_15m": round(load15, 2),
            "cpu_pct":  round(cpu_pct, 1),
            "mem_used_gb":  round(mem_used  / 1024**3, 1),
            "mem_total_gb": round(mem_total / 1024**3, 1),
            "disk_used_pct": round(disk_used_pct, 1),
            "containers_up":    containers_up,
            "containers_total": containers_total,
        }
    except Exception as e:
        return {"error": f"prometheus unreachable: {type(e).__name__}: {e}"}


def _stub() -> dict:
    return {
        "_stub": True,
        "host": "83rr-poweredge",
        "uptime_days": 12.4,
        "load_1m": 0.42,
        "load_5m": 0.51,
        "load_15m": 0.48,
        "cpu_pct": 18.0,
        "mem_used_gb": 23.1,
        "mem_total_gb": 64.0,
        "disk_used_pct": 42.0,
        "containers_up": 26,
        "containers_total": 26,
    }
