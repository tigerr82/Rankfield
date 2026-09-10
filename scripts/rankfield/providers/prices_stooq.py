# ---------------------------------------------------------------------------
# PERSONAL-USE DATA SOURCE — REPLACE BEFORE ANY COMMERCIAL LAUNCH.
# Stooq grants no redistribution rights. See SOURCES.md.
# ---------------------------------------------------------------------------
"""Stooq CSV adapter — implemented, but currently NOT usable unattended.

As of 2026-09, `https://stooq.com/q/d/l/?s={ticker}.us&i=d` no longer returns
CSV to a script. It returns an HTML interstitial that runs a JavaScript
proof-of-work challenge and only then issues the CSV. That is a bot-detection
mechanism, and this project does not circumvent it.

The adapter is kept because the prompt ranks Stooq first and because the block
may be lifted or a licensed endpoint may appear. `history()` raises a clear
error rather than silently returning nothing, so a misconfiguration surfaces
loudly instead of producing an empty price column.
"""
from __future__ import annotations

import csv
import io

import requests

from .prices_yahoo import PriceSeries
from ..util import RateLimiter

ENDPOINT = "https://stooq.com/q/d/l/?s={ticker}.us&i=d"


class StooqBlocked(RuntimeError):
    pass


class StooqPrices:
    name = "stooq-csv"
    licence = "personal use only — no redistribution"

    def __init__(self, user_agent: str, per_sec: float = 2.0):
        self.user_agent = user_agent
        self.limiter = RateLimiter(per_sec)

    def history(self, ticker: str, *, range_: str = "1y") -> PriceSeries | None:
        self.limiter.wait()
        resp = requests.get(
            ENDPOINT.format(ticker=ticker.lower()),
            headers={"User-Agent": self.user_agent},
            timeout=30,
        )
        body = resp.text
        if body.lstrip().lower().startswith("<!doctype html") or "<script" in body[:400].lower():
            raise StooqBlocked(
                "Stooq served a JavaScript browser-verification challenge instead of CSV. "
                "Rankfield does not solve bot-detection challenges. Use the `yahoo` price "
                "provider, or a licensed feed, until Stooq serves CSV to scripts again."
            )
        series = PriceSeries(ticker=ticker)
        for row in csv.DictReader(io.StringIO(body)):
            if not row.get("Date") or not row.get("Close"):
                continue
            series.dates.append(row["Date"])
            series.closes.append(float(row["Close"]))
            series.volumes.append(float(row["Volume"]) if row.get("Volume") else None)
        return series if series.closes else None
