"""Thin wrapper around python-escpos for the Epson TM-m30III.

Centralises everything we learned during initial setup:
- Default IP, port, timeout for our specific unit
- Reset sequence (init + upside-down off) on every connection
- Layout constants tuned to this physical printer's effective text width
  (see CONTENT_WIDTH below — narrower than the printer's nominal 48 cols)
- Status query helper for diagnostics
"""
from __future__ import annotations

import socket
from typing import Optional

from escpos.printer import Network


class ReceiptPrinter:
    """Context-managed Network printer plus convenience helpers.

    Layout constants are class-level so chart/style functions can reference
    them without holding a printer reference. They reflect what actually
    looks good on this unit, not the printer's nominal capabilities.
    """

    HOST = "192.168.1.147"
    PORT = 9100
    TIMEOUT = 15

    # Effective character widths.
    # Font A is nominally 48 cols, but mixed-content lines (label+bar+value)
    # start to feel "too long" past ~28 chars on this unit. Keep content
    # narrow; only use full-width for solid dividers.
    CONTENT_WIDTH = 28        # tables, kv lines, histograms
    BAR_WIDTH = 12            # bars inside chart rows
    DIVIDER_WIDTH = 32        # section dividers (=, -, *)

    # Image rendering. The print head supports ~540 px; 512 leaves a small
    # right margin and dithers cleanly.
    IMAGE_WIDTH_PX = 512
    IMAGE_MAX_PX = 540

    def __init__(
        self,
        host: str = HOST,
        port: int = PORT,
        timeout: int = TIMEOUT,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._p: Optional[Network] = None

    # ----- lifecycle -----

    def __enter__(self) -> "ReceiptPrinter":
        self._p = Network(self.host, port=self.port, timeout=self.timeout)
        self.reset()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._p is not None:
            try:
                self._p.close()
            finally:
                self._p = None

    @property
    def raw(self) -> Network:
        if self._p is None:
            raise RuntimeError("Printer not connected. Use as a context manager.")
        return self._p

    def reset(self) -> None:
        """ESC @ (init) + ESC { 0 (upside-down off). Safe at top of any job."""
        self.raw._raw(b"\x1b@")
        self.raw._raw(b"\x1b{\x00")

    # ----- escpos passthroughs -----

    def text(self, s: str) -> None:
        self.raw.text(s)

    def set(self, **kwargs) -> None:
        self.raw.set(**kwargs)

    def feed(self, lines: int = 1) -> None:
        self.raw.text("\n" * lines)

    def cut(self, partial: bool = True) -> None:
        if partial:
            self.raw._raw(b"\x1dV\x01")
        else:
            self.raw._raw(b"\x1dV\x00")

    def image(self, img) -> None:
        self.raw.image(img, impl="bitImageColumn")

    def qr(self, data: str, size: int = 8) -> None:
        self.raw.qr(data, size=size, native=True)

    # ----- formatting helpers -----

    def divider(self, char: str = "-", width: Optional[int] = None) -> None:
        self.raw.set(align="left")
        self.text((char * (width or self.DIVIDER_WIDTH)) + "\n")

    def newline(self, n: int = 1) -> None:
        self.text("\n" * n)

    # ----- diagnostics -----

    @classmethod
    def status(cls, host: str = HOST, port: int = PORT) -> dict:
        """Send DLE EOT n queries and return a parsed status dict.

        Opens its own short-lived socket — call this *without* entering a
        ReceiptPrinter context, since the printer only accepts one TCP
        connection on port 9100 at a time. Returns:
            {"online": bool, "cover_open": bool, "paper_present": bool,
             "error": bool, "raw": {1: int, 2: int, 3: int, 4: int}}
        """
        with socket.create_connection((host, port), timeout=5) as s:
            s.settimeout(2)
            raw = {}
            for n in (1, 2, 3, 4):
                s.sendall(b"\x10\x04" + bytes([n]))
                raw[n] = s.recv(1)[0]
        return {
            "online": (raw[1] & 0x08) == 0,
            "cover_open": bool(raw[2] & 0x04),
            "paper_present": (raw[4] & 0x60) == 0,
            "error": bool(raw[3] & 0x40),
            "raw": raw,
        }
