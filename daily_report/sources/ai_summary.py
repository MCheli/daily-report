"""Generate a short AI summary paragraph from the rest of the report data.

Uses the Anthropic SDK + Claude Haiku 4.5 (fast and cheap for summaries).
Requires ANTHROPIC_API_KEY in the environment.

This is *not* a normal source — it's called by the renderer after every
other source has run, with the collected data as input.
"""
from __future__ import annotations

import json
import os

PROMPT_TEMPLATE = """You are a personal assistant printing a one-paragraph summary on an 80mm thermal receipt printer.

Below is the data already gathered for today's report. Write a single paragraph (under 80 words, ~6-8 sentences max) that summarises the day's most notable items across this data. Lead with the most important or surprising thing. Be concrete: cite specific numbers, names, dates, or events. Do not list every section - synthesize. Avoid filler like "Here's a summary" or "Today's report shows".

Data:
{data}

Write only the paragraph itself, no preamble or sign-off. Plain ASCII text only (no emojis, no fancy quotes - the printer's character set is limited)."""


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
