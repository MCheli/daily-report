"""Generate a short AI summary paragraph from the rest of the report data.

Uses the Anthropic SDK + Claude Haiku 4.5 (fast and cheap for summaries).
Requires ANTHROPIC_API_KEY in the environment.

This is *not* a normal source — it's called by the renderer after every
other source has run, with the collected data as input.
"""
from __future__ import annotations

import json
import os

PROMPT_TEMPLATE = """You are writing 2-3 short observations at the top of a daily-brief receipt printed at 7 AM. The reader will see every section below in detail. Your job is to highlight what is *new or notable about TODAY*, not to recap the data.

Lean into things that genuinely change day to day and are worth a quick observation:
  - Weather changes vs the trend (cold snap, rain coming, big swing day-to-day)
  - Stock movement worth flagging (a >2% daily move, or a notable break from the recent range)
  - Spending anomalies (one unusually large transaction, a category spiking, total well above or below recent days)
  - Power-consumption anomalies vs the recent baseline
  - A calendar item that is *imminent* (today or tomorrow) or that appears to be NEW since the last few days

Hard rules - the previous version of this got these wrong:

  1. The user's calendar is their PERSONAL calendar only. It is NOT their complete schedule. Do not draw conclusions about how busy or balanced their week is overall.

  2. Do NOT infer the purpose of a calendar event. Only describe what is literally in the title. "Online Consultation" is not a "mental health consultation." If the title is ambiguous, leave it out.

  3. Do NOT moralize about task progress. Open tasks are often reminders, not delinquencies. Phrases like "momentum is slipping," "consider whether priorities are crowding out," "these need concrete blocking time today" are forbidden. The user already knows what's on their list.

  4. Do NOT comment on a calendar item more than 7 days out unless something about it has clearly changed. The same "block prep time" advice the day before would be repeating yourself.

  5. Do NOT generate evergreen advice. Each observation must be specific to today's data.

  6. If nothing is genuinely notable in a category, skip it. A 2-sentence summary that says something real beats a 3-paragraph one with filler.

  7. Tasks in this data have NO due dates. The `days_open` field is the
     number of days since the task was created (or pushed into the current
     cycle). It is NOT "days until due" or anything similar.

     The word "due" is FORBIDDEN in any sentence about tasks. Do not write
     "due today," "due soon," "due this week," "is due," or any other
     phrasing implying a deadline. The data has no deadline information,
     period - even if a task title sounds like it has an inherent
     deadline (e.g. "RSVP," "submit X by Friday"), the data has no field
     telling you when. You may say a task was "added today" (days_open=0)
     or "open for N days" (otherwise), and that's it.

Format:
  - 2-3 short paragraphs, one observation each
  - Separate paragraphs with a blank line (use \\n\\n in the output)
  - Plain ASCII only (no emojis, no fancy quotes)
  - Under 60 words total
  - Output the paragraphs only - no preamble, header, or sign-off

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
