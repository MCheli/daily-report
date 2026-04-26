"""Stock data via yfinance (no auth required).

Default ticker is PTC (PTC Inc). Override per call. Returns current
price, day/week/month change, and ~30 days of closes for sparklines.
"""
from __future__ import annotations


def summarize(ticker: str = "PTC", days: int = 30) -> dict:
    import yfinance as yf

    t = yf.Ticker(ticker)
    info = t.info or {}
    hist = t.history(period=f"{days}d")
    if hist.empty:
        return {"error": f"no data for {ticker}", "ticker": ticker}

    closes = hist["Close"]
    current = float(closes.iloc[-1])
    prev = float(closes.iloc[-2]) if len(closes) >= 2 else current
    week_idx = max(0, len(closes) - 6)
    month_idx = 0
    week_ago = float(closes.iloc[week_idx])
    month_ago = float(closes.iloc[month_idx])

    def _pct(now: float, then: float) -> float:
        return ((now - then) / then * 100) if then else 0.0

    return {
        "ticker": ticker,
        "name": info.get("shortName") or info.get("longName") or ticker,
        "current": current,
        "open": float(hist["Open"].iloc[-1]),
        "day_change_pct": _pct(current, prev),
        "week_change_pct": _pct(current, week_ago),
        "month_change_pct": _pct(current, month_ago),
        "volume": int(hist["Volume"].iloc[-1]),
        "history": [
            (d.strftime("%Y-%m-%d"), float(c))
            for d, c in zip(hist.index, closes)
        ],
    }
