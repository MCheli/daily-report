"""Generate a short AI summary paragraph from the rest of the report data.

Uses the Anthropic SDK + Claude Haiku 4.5 (fast and cheap for summaries).
Requires ANTHROPIC_API_KEY in the environment.

This is *not* a normal source — it's called by the renderer after every
other source has run, with the collected data as input.
"""
from __future__ import annotations

import json
import os

PROMPT_TEMPLATE = """You are writing the synthesis block at the top of a daily-brief receipt printed at 7 AM. The full report is laid out on the receipt below your text - the reader will see every section in detail. Your job is NOT to restate or summarize it. They can read it themselves.

Your job is to be the part the reader cannot do alone: a meta-analysis that looks ACROSS sections to surface connections, patterns, anomalies, or implications they would miss from any single section.

Aim for one of these per paragraph:
  - a connection between two+ sections (e.g. "first meeting at 8:30 + 29F low - layer up early")
  - a pattern or trend (e.g. "6 personal tasks have been open 6+ days; momentum is slipping")
  - an anomaly worth investigating (e.g. "yesterday's kWh spike doesn't match the mild weather - check the furnace")
  - a recommended focus or risk for the day

Hard rules:
  - Do NOT list facts the receipt already shows (tasks, temps, prices, kWh, meetings)
  - Do NOT enumerate. No "X is Y, Z is W" sentences.
  - If you catch yourself writing "X is at Y" or "you have N tasks," rewrite as an implication
  - Under 40 words total
  - 2-3 short paragraphs separated by a blank line
  - Plain ASCII only (no emojis, no fancy quotes)
  - Output only the paragraphs - no preamble, header, or sign-off

Data:
{data}"""


def summarize(collected: dict, *, model: str = "claude-haiku-4-5") -> dict:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {
            "summary": "(AI summary disabled - export ANTHROPIC_API_KEY to enable)",
            "model": None,
        }

    from anthropic import Anthropic

    # Strip the heaviest fields so we don't blow context on raw history arrays.
    def _shrink(d):
        if not isinstance(d, dict):
            return d
        out = {}
        for k, v in d.items():
            if k in ("history", "raw", "checks", "categories"):
                continue
            out[k] = _shrink(v) if isinstance(v, dict) else v
        return out

    shrunk = {k: _shrink(v) for k, v in collected.items() if v}
    prompt = PROMPT_TEMPLATE.format(data=json.dumps(shrunk, indent=2, default=str))

    client = Anthropic()
    msg = client.messages.create(
        model=model,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(
        block.text for block in msg.content if getattr(block, "text", None)
    ).strip()
    return {
        "summary": text,
        "model": model,
        "input_tokens": msg.usage.input_tokens,
        "output_tokens": msg.usage.output_tokens,
    }
