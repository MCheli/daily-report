"""Data sources for the daily report.

Each module here exposes one or more functions that fetch raw data and
return a plain dict / dataclass. Rendering happens in `daily_report.report`,
which calls into `daily_report.charts` and `daily_report.styles`.

Convention:
- A `summarize()` function returns the digest for printing (small, totals,
  counts, top-N lists).
- Long-running fetches accept a `timeout=` kwarg and degrade gracefully
  on network errors so a single dead source can't block the whole report.
"""
