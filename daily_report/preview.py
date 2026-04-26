"""Local web preview of the daily report.

Runs `report.generate()` against a `PreviewPrinter` that captures every
print operation as a structured event, then renders the events as HTML
and serves them on `http://localhost:5050/`. This way we can iterate on
sources, layouts, and styling without burning thermal paper.

Usage:
    python -m daily_report.cli preview
    # then open http://localhost:5050 - hit refresh to re-run the report

The preview honors the same layout constants as `ReceiptPrinter`, so
line widths in HTML match what would print on paper.
"""
from __future__ import annotations

import base64
import html
import io
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .printer import ReceiptPrinter


# ---------- capturing printer ----------

class PreviewPrinter:
    """Drop-in replacement for `ReceiptPrinter` that records HTML events
    instead of pushing bytes to the network printer."""

    HOST = "preview"
    PORT = 0
    TIMEOUT = 0

    # Mirror layout constants so chart code produces the same widths.
    CONTENT_WIDTH = ReceiptPrinter.CONTENT_WIDTH
    BAR_WIDTH = ReceiptPrinter.BAR_WIDTH
    DIVIDER_WIDTH = ReceiptPrinter.DIVIDER_WIDTH
    IMAGE_WIDTH_PX = ReceiptPrinter.IMAGE_WIDTH_PX
    IMAGE_MAX_PX = ReceiptPrinter.IMAGE_MAX_PX
    LINE_SPACING_DOTS = ReceiptPrinter.LINE_SPACING_DOTS

    def __init__(self, font: str = "b") -> None:
        self.font = font
        self.events: list[dict] = []
        self._style: dict[str, Any] = {
            "align": "left",
            "bold": False,
            "underline": False,
            "double_height": False,
            "double_width": False,
        }

    @classmethod
    def status(cls, *_, **__) -> dict:
        return {"online": True, "cover_open": False, "paper_present": True,
                "error": False, "raw": {}}

    def __enter__(self) -> "PreviewPrinter":
        return self

    def __exit__(self, *_):
        return None

    @property
    def raw(self) -> "_RawStub":
        return _RawStub(self)

    def reset(self) -> None:
        pass

    def set(self, **kwargs) -> None:
        for k in ("align", "bold", "underline", "double_height", "double_width"):
            if k in kwargs and kwargs[k] is not None:
                self._style[k] = kwargs[k]

    def text(self, s: str) -> None:
        chunks = s.split("\n")
        for i, chunk in enumerate(chunks):
            if i > 0:
                self.events.append({"type": "newline"})
            if chunk:
                self.events.append({
                    "type": "text",
                    "text": chunk,
                    "style": self._style.copy(),
                })

    def feed(self, lines: int = 1) -> None:
        for _ in range(lines):
            self.events.append({"type": "newline"})

    def newline(self, n: int = 1) -> None:
        self.feed(n)

    def cut(self, partial: bool = True) -> None:
        self.events.append({"type": "cut"})

    def image(self, img) -> None:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        self.events.append({"type": "image", "data": b64})

    def qr(self, data: str, size: int = 8) -> None:
        import qrcode
        img = qrcode.make(data).get_image()
        self.image(img)

    def divider(self, char: str = "-", width: int | None = None) -> None:
        self.set(align="left")
        self.text((char * (width or self.DIVIDER_WIDTH)) + "\n")


class _RawStub:
    """Stub for `python-escpos`'s low-level escape-byte interface so chart
    code that calls `p.raw.barcode(...)` etc. doesn't blow up under preview."""

    def __init__(self, parent: PreviewPrinter) -> None:
        self.parent = parent

    def text(self, s: str) -> None:
        self.parent.text(s)

    def barcode(self, code: str, kind: str, **_) -> None:
        self.parent.text(f"[barcode {kind}: {code}]\n")

    def qr(self, data: str, size: int = 8, **_) -> None:
        self.parent.qr(data, size=size)

    def image(self, img, **_) -> None:
        self.parent.image(img)

    def _raw(self, *_args, **_kwargs) -> None:
        pass


# ---------- HTML rendering ----------

def _render_body(events: list[dict]) -> str:
    parts: list[str] = ['<div class="receipt">']
    current_line: list[dict] = []

    def flush_line() -> None:
        nonlocal current_line
        if not current_line:
            parts.append('<div class="line">&nbsp;</div>')
            return
        align = current_line[0]["style"].get("align", "left")
        line_html = f'<div class="line align-{align}">'
        for chunk in current_line:
            text = html.escape(chunk["text"]).replace(" ", "&nbsp;")
            classes = []
            st = chunk["style"]
            if st.get("bold"):
                classes.append("bold")
            if st.get("underline"):
                classes.append("underline")
            if st.get("double_height") or st.get("double_width"):
                classes.append("big")
            if classes:
                line_html += f'<span class="{" ".join(classes)}">{text}</span>'
            else:
                line_html += f"<span>{text}</span>"
        line_html += "</div>"
        parts.append(line_html)
        current_line = []

    for ev in events:
        t = ev["type"]
        if t == "text":
            current_line.append(ev)
        elif t == "newline":
            flush_line()
        elif t == "image":
            flush_line()
            parts.append(
                f'<div class="line align-center">'
                f'<img src="data:image/png;base64,{ev["data"]}"></div>'
            )
        elif t == "cut":
            flush_line()
            parts.append('<div class="cut">--- cut ---</div>')

    flush_line()
    parts.append("</div>")
    return "".join(parts)


_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Daily Report Preview</title>
<style>
  body {{
    background: #2b2b2b;
    color: #ddd;
    margin: 0;
    padding: 24px;
    font-family: -apple-system, system-ui, sans-serif;
  }}
  .topbar {{
    text-align: center;
    margin-bottom: 24px;
  }}
  .topbar button {{
    font: inherit;
    padding: 8px 18px;
    border: 1px solid #555;
    background: #444;
    color: #eee;
    cursor: pointer;
    border-radius: 4px;
    margin: 0 4px;
  }}
  .topbar button:hover {{ background: #555; }}
  .topbar button.print {{ background: #2d6a3a; border-color: #3d8a4a; }}
  .topbar button.print:hover {{ background: #3a8048; }}
  .topbar button:disabled {{ opacity: 0.6; cursor: wait; }}
  .topbar .meta {{ color: #888; margin-left: 12px; font-size: 13px; }}
  .topbar .status {{
    display: inline-block; margin-left: 12px; font-size: 13px;
    font-family: monospace;
  }}
  .topbar .status.ok  {{ color: #6f6; }}
  .topbar .status.err {{ color: #f88; }}

  .receipt {{
    background: #f8f6f1;
    color: #222;
    width: 360px;
    margin: 0 auto;
    padding: 18px 14px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
    font-size: 11px;
    line-height: 1.15;
    border-radius: 2px;
  }}
  .line {{
    min-height: 1em;
    white-space: pre;
    font-variant-ligatures: none;
  }}
  .align-center {{ text-align: center; }}
  .align-right  {{ text-align: right;  }}
  .bold      {{ font-weight: 700; }}
  .underline {{ text-decoration: underline; }}
  .big       {{ font-size: 22px; font-weight: 700; line-height: 1.05; }}
  .receipt img {{
    display: block;
    margin: 4px auto;
    max-width: 100%;
    image-rendering: pixelated;
  }}
  .cut {{
    text-align: center;
    color: #888;
    border-top: 1px dashed #aaa;
    margin: 10px -14px 0;
    padding: 6px 0 0;
  }}
  .err {{
    background: #4a1f1f;
    color: #faa;
    padding: 16px;
    border-radius: 4px;
    white-space: pre-wrap;
    font-family: monospace;
    max-width: 800px;
    margin: 0 auto;
  }}
</style>
</head>
<body>
<div class="topbar">
  <button id="reload" onclick="location.reload()">Reload &uarr;</button>
  <button id="print" class="print" onclick="triggerPrint()">Print to thermal printer</button>
  <span id="status" class="status"></span>
  <span class="meta">{meta}</span>
</div>
{body}
<script>
async function triggerPrint() {{
  const btn = document.getElementById('print');
  const status = document.getElementById('status');
  btn.disabled = true;
  status.className = 'status';
  status.textContent = 'sending to printer...';
  try {{
    const resp = await fetch('/trigger', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{}}),
    }});
    const data = await resp.json();
    if (data.status === 'ok') {{
      status.className = 'status ok';
      status.textContent = 'printed ' + (data.duration_s ? '(' + data.duration_s + 's)' : '');
    }} else {{
      status.className = 'status err';
      status.textContent = 'failed: ' + (data.error || 'unknown');
    }}
  }} catch (e) {{
    status.className = 'status err';
    status.textContent = 'network error: ' + e;
  }} finally {{
    btn.disabled = false;
  }}
}}
</script>
</body>
</html>
"""


def render_full_page(events: list[dict], meta: str = "") -> str:
    return _PAGE.format(meta=html.escape(meta), body=_render_body(events))


# ---------- preview generation ----------

def generate_preview_html(**kwargs) -> str:
    """Run `report.generate()` against a `PreviewPrinter` and return HTML."""
    # Imported here to avoid a circular import at module load time.
    from . import report

    captured: list[PreviewPrinter] = []

    def factory() -> PreviewPrinter:
        p = PreviewPrinter()
        captured.append(p)
        return p

    report.generate(printer_factory=factory, **kwargs)
    if not captured:
        return render_full_page([], meta="(no printer was created)")
    return render_full_page(captured[0].events, meta="rendered just now")


# ---------- HTTP server ----------

class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/favicon.ico", "/favicon.png"):
            self.send_response(404)
            self.end_headers()
            return
        try:
            page = generate_preview_html(**self.server.report_kwargs)  # type: ignore[attr-defined]
            data = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            import traceback
            err = traceback.format_exc()
            body = (
                f'<!DOCTYPE html><html><body style="background:#2b2b2b;color:#ddd;'
                f'font-family:monospace;padding:24px;"><div class="err" '
                f'style="background:#4a1f1f;color:#faa;padding:16px;'
                f'white-space:pre-wrap;">{html.escape(err)}</div>'
                f'</body></html>'
            )
            data = body.encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(data)

    def do_POST(self):
        # The preview server is bound to 127.0.0.1 only, so /trigger can
        # be open without auth - if you can hit it you're already on this
        # machine.
        if self.path != "/trigger":
            self.send_response(404)
            self.end_headers()
            return

        import json as _json
        import time as _time
        import traceback as _tb

        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            body = _json.loads(self.rfile.read(length)) if length else {}
        except _json.JSONDecodeError:
            body = {}
        sections = body.get("sections") or None

        started = _time.time()
        try:
            from . import report
            # Server-level kwargs may already carry a `sections` value from
            # the CLI flag; pop it so the request body wins.
            kwargs = dict(self.server.report_kwargs)  # type: ignore[attr-defined]
            kwargs.pop("sections", None)
            report.generate(sections=sections, **kwargs)
            resp = {
                "status": "ok",
                "sections": sections or "all",
                "duration_s": round(_time.time() - started, 2),
            }
            code = 200
        except Exception as e:
            _tb.print_exc()
            resp = {
                "status": "error",
                "error": f"{type(e).__name__}: {e}",
                "duration_s": round(_time.time() - started, 2),
            }
            code = 500

        data = _json.dumps(resp).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        # Quieter than the default stdout dump
        print(f"[preview] {self.address_string()} - {fmt % args}")


def serve(port: int = 5050, *, open_browser: bool = True, **report_kwargs) -> None:
    """Start the preview server. Re-renders on every request, so just
    refresh the page after editing code."""
    addr = ("127.0.0.1", port)
    server = ThreadingHTTPServer(addr, _Handler)
    server.report_kwargs = report_kwargs  # type: ignore[attr-defined]

    url = f"http://localhost:{port}/"
    print(f"Daily-report preview at {url}  (Ctrl-C to stop)")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        server.shutdown()
