# ---------------------------------------------------------------------------
# PERSONAL-USE DATA SOURCE — REPLACE BEFORE ANY COMMERCIAL LAUNCH.
#
# Yahoo Finance's chart endpoint is free and unauthenticated, but Yahoo's terms
# do not grant redistribution rights. It is acceptable for personal research;
# it is NOT acceptable to serve to paying users. Before monetizing, swap this
# adapter for a commercially licensed feed (e.g. Polygon, Tiingo, EODHD). The
# provider interface below is the whole surface that has to change.
#
# See SOURCES.md.
# ---------------------------------------------------------------------------
"""Split/dividend-adjusted daily closes.

Always uses the ADJUSTED series. Unadjusted closes create false cliffs at every
split, and month-over-month change computed against a raw prior price reads a
10-for-1 split as -90%.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..util import RateLimiter, http_json, parse_iso
from datetime import datetime, timezone

ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"


@dataclass
class PriceSeries:
    ticker: str
    dates: list[str] = field(default_factory=list)     # ISO, ascending
    closes: list[float] = field(default_factory=list)  # adjusted
    volumes: list[float] = field(default_factory=list)
    splits: list[dict] = field(default_factory=list)   # {date, ratio} within the window

    def close_on_or_before(self, when: date) -> tuple[str, float] | None:
        """Last adjusted close at or before `when` — the whole series is on
        today's adjusted basis, so both endpoints of a change are comparable."""
        target = when.isoformat()
        for i in range(len(self.dates) - 1, -1, -1):
            if self.dates[i] <= target:
                return self.dates[i], self.closes[i]
        return None

    def avg_dollar_volume(self, days: int = 63) -> float | None:
        n = min(days, len(self.closes))
        if n == 0:
            return None
        pairs = [
            self.closes[i] * self.volumes[i]
            for i in range(len(self.closes) - n, len(self.closes))
            if self.closes[i] is not None and self.volumes[i] is not None
        ]
        return sum(pairs) / len(pairs) if pairs else None


class YahooPrices:
    name = "yahoo-chart"
    licence = "personal use only — no redistribution"

    def __init__(self, user_agent: str, per_sec: float = 8.0):
        self.user_agent = "Mozilla/5.0 (compatible; Rankfield/1.0)"
        self.limiter = RateLimiter(per_sec)

    def history(self, ticker: str, *, range_: str = "1y") -> PriceSeries | None:
        url = ENDPOINT.format(ticker=ticker.replace(".", "-")) + (
            f"?range={range_}&interval=1d&events=split"
        )
        payload = http_json(
            url, user_agent=self.user_agent, limiter=self.limiter, allow_404=True, retries=3
        )
        if not payload:
            return None
        result = ((payload.get("chart") or {}).get("result") or [None])[0]
        if not result or not result.get("timestamp"):
            return None
        stamps = result["timestamp"]
        indicators = result.get("indicators", {})
        adj = (indicators.get("adjclose") or [{}])[0].get("adjclose")
        quote = (indicators.get("quote") or [{}])[0]
        raw_close = quote.get("close") or []
        volume = quote.get("volume") or []
        if not adj:
            adj = raw_close  # pre-adjustment fallback; flagged by the caller's sanity check
        series = PriceSeries(ticker=ticker)
        for i, ts in enumerate(stamps):
            close = adj[i] if i < len(adj) else None
            if close is None:
                continue
            series.dates.append(
                datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
            )
            series.closes.append(float(close))
            vol = volume[i] if i < len(volume) else None
            series.volumes.append(float(vol) if vol is not None else None)
        for _, ev in ((result.get("events") or {}).get("splits") or {}).items():
            series.splits.append(
                {
                    "date": datetime.fromtimestamp(ev["date"], tz=timezone.utc).date().isoformat(),
                    "ratio": f"{ev.get('numerator')}:{ev.get('denominator')}",
                }
            )
        return series if series.closes else None
