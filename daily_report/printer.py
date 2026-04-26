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
    # Calibrated against this physical unit at Font B:
    #   - A 52-char solid bar prints fully on one row (proven safe max).
    #   - A 56-char dotted line printed too, but only because trailing
    #     whitespace compresses; safer to budget against the solid case.
    # Stay <= 52 for any line that uses solid characters (#, =, *) and we
    # won't wrap.
    CONTENT_WIDTH = 52        # tables, kv lines, histograms
    BAR_WIDTH = 36            # bars inside chart rows
    DIVIDER_WIDTH = 52        # section dividers (=, -, *)

    # Line spacing in dots. Default Epson line height is 30 dots; Font B
    # itself is only 17 dots tall, so we can pack rows much tighter.
    # ~22 leaves a small gap; pull lower for denser, higher for airier.
    LINE_SPACING_DOTS = 22

    # Image rendering. The print head supports ~540 px; 512 leaves a small
    # right margin and dithers cleanly.
    IMAGE_WIDTH_PX = 512
    IMAGE_MAX_PX = 540

    def __init__(
        self,
        host: str = HOST,
        port: int = PORT,
        timeout: int = TIMEOUT,
        font: str = "b",
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.font = font
        self._p: Optional[Network] = None

    # ----- lifecycle -----

    def __enter__(self) -> "ReceiptPrinter":
        self._p = Network(self.host, port=self.port, timeout=self.timeout)
        self.reset()
        # Default to the small font (B) so long reports don't eat a meter of
        # paper. python-escpos's set(font='b') was unreliable on this unit -
        # something downstream kept reverting to Font A - so we send the raw
        # ESC M n command directly and re-assert it after every set() call.
        self._assert_font()
        # ESC 3 n - set line spacing in dots. Tighter than the 30-dot default.
        self.raw._raw(b"\x1b3" + bytes([self.LINE_SPACING_DOTS]))
        return self

    @property
    def _font_byte(self) -> bytes:
        return b"\x01" if self.font.lower() == "b" else b"\x00"

    def _assert_font(self) -> None:
        # ESC M n  - n=0 Font A, n=1 Font B
        self.raw._raw(b"\x1bM" + self._font_byte)

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
        """Send ESC/POS print mode bytes directly.

        We avoid python-escpos's set() because:
          1. Its font selection didn't reliably stick on this unit.
          2. It only emits "size" commands when double_*=True, so
             passing double_height=False after a title leaves the
             previous 2x size enabled - which is why every byte after
             a title was printing huge.

        Supported kwargs (everything else is silently ignored so existing
        callers don't break): align, bold, double_height, double_width,
        underline, font.
        """
        font = kwargs.get("font") or self.font
        self.raw._raw(b"\x1bM" + (b"\x01" if font.lower() == "b" else b"\x00"))

        if "align" in kwargs and kwargs["align"] is not None:
            a = {"left": 0, "center": 1, "right": 2}[kwargs["align"].lower()]
            self.raw._raw(b"\x1ba" + bytes([a]))

        if "bold" in kwargs and kwargs["bold"] is not None:
            self.raw._raw(b"\x1bE" + (b"\x01" if kwargs["bold"] else b"\x00"))

        if "underline" in kwargs and kwargs["underline"] is not None:
            u = 1 if kwargs["underline"] else 0
            self.raw._raw(b"\x1b-" + bytes([u]))

        # Size: always emit a GS ! command if either size kwarg is mentioned,
        # so going back to normal actually clears the bit.
        if "double_height" in kwargs or "double_width" in kwargs:
            n = 0
            if kwargs.get("double_height"):
                n |= 0x01           # bit 0: height x2
            if kwargs.get("double_width"):
                n |= 0x10           # bit 4: width x2
            self.raw._raw(b"\x1d!" + bytes([n]))

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
        # Use self.set so the font wrapper kicks in - bypassing it would silently
        # reset to Font A and break every divider mid-report.
        self.set(align="left")
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
