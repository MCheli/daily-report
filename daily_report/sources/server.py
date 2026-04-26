"""Homelab server resource summary (mcheli/83rr-poweredge).

STUB: returns sample data marked `_stub: True`. Wiring options:

  1. Prometheus on the homelab (probably present in the observability
     stack) — query the `node_exporter` series via the HTTP API:
        GET http://prometheus.ops:9090/api/v1/query?query=...
     Good metrics: 1m load, mem_used / mem_total, fs_used / fs_total.
  2. SSH + run `uptime`, `free -m`, `df -h` and parse. Heavier.
  3. Glances / netdata REST endpoint if running.

Env vars to plumb through (when ready):
    PROM_URL    e.g. http://prometheus.ops:9090

Expected return shape:
    {
        "host":        str,
        "uptime_days": float,
        "load_1m":     float,
        "load_5m":     float,
        "load_15m":    float,
        "cpu_pct":     float,
        "mem_used_gb": float,
        "mem_total_gb": float,
        "disk_used_pct": float,
        "containers_up": int,
        "containers_total": int,
    }
"""
from __future__ import annotations

import os


def summarize() -> dict:
    if not os.environ.get("PROM_URL"):
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
    raise NotImplementedError(
        "Prometheus client not yet wired up. Implement query in "
        "daily_report/sources/server.py and remove this raise."
    )
