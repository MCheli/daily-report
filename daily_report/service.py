"""Long-running service: scheduled prints + HTTP API for ad-hoc runs.

Designed to run as a single container on the homelab. Two responsibilities:

1. **Schedule loop** — runs the configured report at a list of daily
   times via the `schedule` library. Configured via `REPORT_TIMES`
   (comma-separated `HH:MM`, 24-hour, in the container's TZ).
2. **HTTP API** on `0.0.0.0:DAILY_REPORT_PORT` (default 8080):
     GET  /health           -> 200 {"status":"ok"}
     GET  /                 -> HTML preview (same renderer as the
                              `preview` command)
     POST /trigger          -> run a real print to the thermal printer
                              now. Body: {"sections": ["weather", ...]}
                              omit `sections` (or empty list) for the
                              default order.
     POST /preview          -> render a preview only (no print)
                              same body shape as /trigger.

Auth: if `DAILY_REPORT_API_TOKEN` is set, all POST endpoints require
`Authorization: Bearer <token>`. GET endpoints are always open since
they're behind the homelab's LAN-only nginx anyway.
"""
from __future__ import annotations

import html
import json
import os
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import schedule

from . import preview, report

DEFAULT_PORT = 8080


def _bool(env: str, default: bool = False) -> bool:
    v = os.environ.get(env, "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "y", "on")


def _generate_kwargs() -> dict:
    """Pick up the per-section knobs from env so /trigger uses the
    same defaults as the CLI without us re-declaring them everywhere."""
    return {
        "check_urls": _bool("CHECK_URLS"),
        "github_lookback_hours": int(os.environ.get("GITHUB_LOOKBACK_HOURS", 168)),
        "stock_ticker": os.environ.get("STOCK_TICKER", "PTC"),
        "weather_location": os.environ.get("WEATHER_LOCATION", "Ashland,MA"),
        "tallied_days": int(os.environ.get("TALLIED_DAYS", 7)),
    }


def _run_print(sections: list[str] | None) -> dict:
    """Run a real print on the thermal printer. Returns a result dict."""
    started = time.time()
    try:
        report.generate(sections=sections, **_generate_kwargs())
        return {
            "status": "ok",
            "sections": sections or "all",
            "duration_s": round(time.time() - started, 2),
        }
    except Exception as e:
        traceback.print_exc()
        return {
            "status": "error",
            "error": f"{type(e).__name__}: {e}",
            "duration_s": round(time.time() - started, 2),
        }


def _run_preview_only(sections: list[str] | None) -> str:
    """Render a preview to HTML without touching the printer."""
    return preview.generate_preview_html(sections=sections, **_generate_kwargs())


def _scheduled_print() -> None:
    print("[schedule] running daily report ...", flush=True)
    result = _run_print(None)
    print(f"[schedule] {result}", flush=True)


# ---------- HTTP handler ----------

class _Handler(BaseHTTPRequestHandler):
    api_token: str | None = None
    report_kwargs: dict = {}

    # Suppress the default per-request stdout dump; print our own concise line.
    def log_message(self, fmt, *args):
        print(f"[http] {self.address_string()} - {fmt % args}", flush=True)

    # ----- helpers -----

    def _check_auth(self) -> bool:
        if not self.api_token:
            return True
        got = self.headers.get("Authorization", "")
        return got == f"Bearer {self.api_token}"

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _send_json(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, code: int, body: str) -> None:
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ----- routing -----

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        if self.path in ("/", "/preview"):
            try:
                page = preview.generate_preview_html(**_generate_kwargs())
                self._send_html(200, page)
            except Exception:
                err = traceback.format_exc()
                self._send_html(
                    500,
                    f"<pre style='font-family:monospace;color:#faa;"
                    f"background:#2b2b2b;padding:16px'>{html.escape(err)}</pre>",
                )
            return
        if self.path in ("/favicon.ico", "/favicon.png"):
            self.send_response(404); self.end_headers(); return

        self._send_json(404, {"error": f"unknown path: {self.path}"})

    def do_POST(self):
        if not self._check_auth():
            self._send_json(401, {"error": "missing or invalid bearer token"})
            return

        body = self._read_json()
        sections = body.get("sections") or None
        if sections is not None and not isinstance(sections, list):
            self._send_json(400, {"error": "`sections` must be an array"})
            return

        if self.path == "/trigger":
            self._send_json(200, _run_print(sections))
            return
        if self.path == "/preview":
            try:
                self._send_html(200, _run_preview_only(sections))
            except Exception:
                err = traceback.format_exc()
                self._send_html(
                    500,
                    f"<pre style='color:#faa;background:#2b2b2b;padding:16px'>"
                    f"{html.escape(err)}</pre>",
                )
            return

        self._send_json(404, {"error": f"unknown path: {self.path}"})


# ---------- entry point ----------

def serve(
    port: int | None = None,
    *,
    schedule_times: list[str] | None = None,
    api_token: str | None = None,
) -> None:
    """Start the schedule loop + HTTP API. Blocks until Ctrl-C."""
    port = port or int(os.environ.get("DAILY_REPORT_PORT", DEFAULT_PORT))
    api_token = api_token or os.environ.get("DAILY_REPORT_API_TOKEN")
    if schedule_times is None:
        schedule_times = [
            t.strip() for t in os.environ.get("REPORT_TIMES", "").split(",")
            if t.strip()
        ]

    # Wire the scheduler
    if schedule_times:
        for t in schedule_times:
            schedule.every().day.at(t).do(_scheduled_print)
            print(f"[schedule] daily print at {t}", flush=True)
    else:
        print("[schedule] no REPORT_TIMES configured; "
              "scheduled prints disabled (API still works)", flush=True)

    def _scheduler_loop():
        while True:
            schedule.run_pending()
            time.sleep(30)
    threading.Thread(target=_scheduler_loop, daemon=True).start()

    _Handler.api_token = api_token

    addr = ("0.0.0.0", port)
    httpd = ThreadingHTTPServer(addr, _Handler)
    print(f"daily-report service on http://{addr[0]}:{addr[1]} "
          f"(auth={'on' if api_token else 'off'})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[shutdown] stopping http server", flush=True)
        httpd.shutdown()


if __name__ == "__main__":
    serve()
