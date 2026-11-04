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
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


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

    # ---------------------------------------------------------- filing index

    def newest_periodic_filing(self, cik: str, as_of) -> dict | None:
        """The newest 10-K or 10-Q the company had filed by `as_of`, from the SEC's filing index.

        Independent of the structured-data API: for some filers (Prologis, Verisk, Citigroup in
        2026) the index lists a report that the XBRL facts never received, which is how a company
        with a current filing can look as if it had stopped reporting.
        """
        payload = http_json(
            SUBMISSIONS_URL.format(cik=cik), user_agent=self.user_agent, limiter=self.limiter, allow_404=True,
        )
        if not payload:
            return None
        recent = (payload.get("filings") or {}).get("recent") or {}
        cutoff = as_of.isoformat()
        best = None
        for form, filed, period in zip(recent.get("form", []), recent.get("filingDate", []),
                                       recent.get("reportDate", [])):
            if form in ("10-K", "10-Q") and filed <= cutoff and period:
                if best is None or period > best["report_date"]:
                    best = {"form": form, "filed": filed, "report_date": period}
        return best

    def files_successor_notice(self, cik: str) -> bool:
        """True when the registrant has filed an 8-K12B: it took over another registrant's reporting.

        That form is how a holding-company reorganisation or merger announces that the new
        registrant is the successor issuer, so a company with a short record and this form probably
        has a longer history under another registration number (see config/successors.json).
        """
        payload = http_json(
            SUBMISSIONS_URL.format(cik=cik), user_agent=self.user_agent, limiter=self.limiter, allow_404=True,
        )
        return has_successor_notice(payload)


def has_successor_notice(submissions: dict | None) -> bool:
    recent = ((submissions or {}).get("filings") or {}).get("recent") or {}
    return any(form in ("8-K12B", "8-K12G3") for form in recent.get("form", []))
