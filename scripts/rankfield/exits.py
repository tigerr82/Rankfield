"""Who left the ranking since last month, and why.

A company that was scored last month and is not this month has either failed a
rule or dropped out of the feed. Each exit is traced to the first stage that
removed it, so the reader sees a reason rather than a number going down.

The classification is deliberately plain: it reads the artefacts the run already
produced (the universe, the exclusion list, the insufficient-data list) and
invents nothing. A company with no trace anywhere is reported as exactly that.
"""
from __future__ import annotations

KIND_FLOOR = "market_cap_floor"
KIND_EXCLUDED = "excluded"
KIND_INSUFFICIENT = "insufficient_data"
KIND_SHARE_CLASS = "share_class"
KIND_NO_FILER = "no_sec_match"
KIND_UNLISTED = "unlisted"


def build_exits(
    prior_by_ticker: dict[str, dict],
    scored_now: set[str],
    *,
    excluded: list[dict],
    insufficient: list[dict],
    universe: dict,
) -> list[dict]:
    """One record per company scored last month and not scored now."""
    excluded_by = {e["ticker"]: e for e in excluded}
    insufficient_by = {r["ticker"]: r for r in insufficient}
    below_floor = universe.get("below_floor") or {}
    floor = universe.get("market_cap_floor_usd")
    merged = {d["dropped"]: d["kept"] for d in universe.get("dropped_share_classes", [])}
    unmatched = set(universe.get("unmatched_tickers", []))

    exits = []
    for ticker, was in prior_by_ticker.items():
        if ticker in scored_now:
            continue
        cap = None
        if ticker in excluded_by:
            kind = KIND_EXCLUDED
            reason = f"{excluded_by[ticker]['stage']}: {excluded_by[ticker]['reason']}"
        elif ticker in insufficient_by:
            row = insufficient_by[ticker]
            kind = KIND_INSUFFICIENT
            reason = row.get("reason") or "too few metrics resolved to score"
        elif ticker in merged:
            kind = KIND_SHARE_CLASS
            reason = f"now counted under its other share class, {merged[ticker]}"
        elif ticker in below_floor:
            kind = KIND_FLOOR
            cap = below_floor[ticker]
            reason = f"market cap ${cap / 1e6:,.0f}M, below the ${(floor or 0) / 1e9:g}B floor"
        elif ticker in unmatched:
            kind = KIND_NO_FILER
            reason = "no longer matched to an SEC filer"
        else:
            kind = KIND_UNLISTED
            reason = "no longer in the exchange listing feed (delisted, acquired, renamed or moved)"
        exits.append({
            "ticker": ticker,
            "name": was.get("name"),
            "sector": was.get("sector"),
            "segment": was.get("segment"),
            "prior_rank": was.get("rank"),
            "kind": kind,
            "reason": reason,
            "market_cap": cap,
        })
    exits.sort(key=lambda e: (e["kind"], e["prior_rank"] if e["prior_rank"] is not None else 10**9))
    return exits
