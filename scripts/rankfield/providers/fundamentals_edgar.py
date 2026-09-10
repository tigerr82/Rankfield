"""SEC EDGAR XBRL — the primary fundamentals source.

Licence: US government work, public domain. No restriction on commercial use or
redistribution. This is why it is the primary source and not a fallback.

Point-in-time discipline lives here. `companyfacts` carries `filed`, `accn` and
`form` on every fact, and EDGAR never overwrites: a restatement arrives as a new
fact with a later `filed`. Scoring as of date D therefore uses only facts with
`filed <= D`, which also removes the reporting-lag trap (a quarter ending 31 Mar
and filed 10 May must not be visible on 31 Mar).

Deviation from the brief, deliberately: the brief suggests the `frames` endpoint
for bulk pulls with `companyfacts` for gap-filling. `frames` responses carry
`accn` but NOT `filed`, and return only the latest (possibly restated) value for
a period — so a frames-based pipeline cannot honour the point-in-time rule, which
the brief also calls mandatory. companyfacts wins the conflict. Cost: one request
per company (~2,400/run at <=9 req/s, a few minutes) instead of a few dozen.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from ..util import RateLimiter, http_json

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


class EdgarFundamentals:
    name = "sec-edgar-xbrl"
    licence = "public domain"

    def __init__(self, user_agent: str, cache_dir: Path | None = None, per_sec: float = 9.0):
        if "@" not in user_agent:
            raise ValueError(
                "SEC policy requires a User-Agent carrying a real name and email address. "
                "Set config/settings.json http.user_agent or RANKFIELD_USER_AGENT."
            )
        self.user_agent = user_agent
        self.limiter = RateLimiter(per_sec)
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- map

    def ticker_cik_map(self) -> dict[str, str]:
        """ticker -> 10-digit zero-padded CIK."""
        payload = http_json(TICKER_MAP_URL, user_agent=self.user_agent, limiter=self.limiter)
        out: dict[str, str] = {}
        for row in payload.values():
            ticker = str(row.get("ticker", "")).strip().upper()
            if ticker:
                out[ticker] = str(row["cik_str"]).zfill(10)
        if len(out) < 5000:
            raise RuntimeError(f"company_tickers.json returned only {len(out)} rows — refusing to proceed")
        return out

    # -------------------------------------------------------------- facts

    def _cache_path(self, cik: str) -> Path | None:
        return self.cache_dir / f"CIK{cik}.json.gz" if self.cache_dir else None

    def company_facts(self, cik: str, *, use_cache: bool = True) -> dict | None:
        """Full XBRL fact history for one filer. None when EDGAR has no facts."""
        path = self._cache_path(cik)
        if use_cache and path and path.exists():
            try:
                with gzip.open(path, "rt", encoding="utf-8") as fh:
                    return json.load(fh)
            except (OSError, ValueError):
                path.unlink(missing_ok=True)  # corrupt cache entry, refetch
        payload = http_json(
            FACTS_URL.format(cik=cik),
            user_agent=self.user_agent,
            limiter=self.limiter,
            allow_404=True,
        )
        if payload is None:
            return None
        if path:
            with gzip.open(path, "wt", encoding="utf-8") as fh:
                json.dump(payload, fh)
        return payload
