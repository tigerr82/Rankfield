"""Universe, sector and market cap from Nasdaq's public stock screener.

One request returns every NYSE/NASDAQ listing with sector, industry, market cap,
last sale and volume, which is why it beats scraping index constituents.

Licence: no published redistribution grant. We redistribute derived values
(sector label, market-cap band), not the feed itself. See SOURCES.md.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from ..util import RateLimiter, http_json

ENDPOINT = "https://api.nasdaq.com/api/screener/stocks"


@dataclass
class Listing:
    ticker: str
    name: str
    exchange: str
    sector: str | None
    industry: str | None
    market_cap: float | None
    last_sale: float | None
    volume: float | None
    country: str | None
    ipo_year: int | None

    def as_dict(self) -> dict:
        return asdict(self)


def _money(text) -> float | None:
    if text in (None, "", "NA", "N/A"):
        return None
    try:
        return float(str(text).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


class NasdaqUniverse:
    """Fails loudly if the payload shape changes rather than writing bad data."""

    name = "nasdaq-screener"

    def __init__(self, user_agent: str, exchanges: list[str] | None = None):
        # The screener rejects a bare script UA; a browser UA is required to get JSON.
        self.user_agent = "Mozilla/5.0 (compatible; Rankfield/1.0)"
        self._sec_ua = user_agent
        self.exchanges = exchanges or ["NYSE", "NASDAQ"]
        self.limiter = RateLimiter(2)

    def fetch(self) -> list[Listing]:
        out: list[Listing] = []
        for exchange in self.exchanges:
            url = f"{ENDPOINT}?tableonly=true&limit=25000&offset=0&download=true&exchange={exchange}"
            payload = http_json(url, user_agent=self.user_agent, limiter=self.limiter)
            rows = (payload or {}).get("data", {}).get("rows")
            if not isinstance(rows, list) or not rows:
                raise RuntimeError(
                    f"Nasdaq screener returned no rows for {exchange}; "
                    "the endpoint shape may have changed. Refusing to write a partial universe."
                )
            required = {"symbol", "name", "marketCap", "sector"}
            missing = required - set(rows[0].keys())
            if missing:
                raise RuntimeError(f"Nasdaq screener payload missing fields {missing}")
            for r in rows:
                sym = (r.get("symbol") or "").strip().upper()
                if not sym:
                    continue
                out.append(
                    Listing(
                        ticker=sym,
                        name=(r.get("name") or "").strip(),
                        exchange=exchange,
                        sector=(r.get("sector") or "").strip() or None,
                        industry=(r.get("industry") or "").strip() or None,
                        market_cap=_money(r.get("marketCap")),
                        last_sale=_money(r.get("lastsale")),
                        volume=_money(r.get("volume")),
                        country=(r.get("country") or "").strip() or None,
                        ipo_year=int(r["ipoyear"]) if str(r.get("ipoyear") or "").isdigit() else None,
                    )
                )
        return out
