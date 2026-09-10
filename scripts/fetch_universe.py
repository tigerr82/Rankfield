"""Stage 1 - universe, sector and market cap.

Emits data/universe.json plus the first stages of the eligibility funnel. Every
stage records a count so the funnel is auditable end to end in
data/coverage_report.json.

Run: python scripts/fetch_universe.py
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rankfield.config import DATA_DIR, ensure_dirs, load_settings, user_agent, write_json
from rankfield.providers import get_fundamentals_provider, get_universe_provider

# Securities that are not an operating company's common equity. Rankfield ranks
# businesses, so units, warrants, preferreds, funds and blank-cheque shells are
# removed before anything is scored.
NON_COMMON = re.compile(
    r"\b(warrant|right|unit|preferred|depositary|debenture|note|bond|trust|fund|etf|etn|"
    r"acquisition corp|acquisitions corp|spac|closed end|closed-end|index|portfolio)\b",
    re.IGNORECASE,
)
COMMON_HINT = re.compile(r"(common stock|ordinary share|common share|class [a-z] )", re.IGNORECASE)


def is_common_stock(name: str) -> bool:
    if NON_COMMON.search(name or ""):
        return False
    return bool(COMMON_HINT.search(name or ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="debug: cap the universe size")
    args = parser.parse_args()

    ensure_dirs()
    settings = load_settings()
    uni_cfg = settings["universe"]
    ua = user_agent()

    provider = get_universe_provider("nasdaq", user_agent=ua, exchanges=uni_cfg["exchanges"])
    listings = provider.fetch()
    funnel = [{"stage": "listed on NYSE/NASDAQ", "count": len(listings)}]

    common = [x for x in listings if is_common_stock(x.name)]
    funnel.append({"stage": "common stock (units, warrants, funds, SPACs removed)", "count": len(common)})

    floor = uni_cfg["market_cap_floor_usd"]
    big = [x for x in common if x.market_cap and x.market_cap >= floor]
    funnel.append({"stage": f"market cap >= ${floor/1e9:.0f}B", "count": len(big)})

    # Dual-class de-duplication: one line per company, keyed on CIK rather than
    # on name heuristics. GOOG/GOOGL are one business counted twice.
    edgar = get_fundamentals_provider("edgar", user_agent=ua, per_sec=settings["http"]["sec_rate_limit_per_sec"])
    cik_map = edgar.ticker_cik_map()

    by_cik: dict[str, list] = {}
    no_cik = []
    for row in big:
        cik = cik_map.get(row.ticker)
        if not cik:
            no_cik.append(row)
            continue
        by_cik.setdefault(cik, []).append(row)

    deduped, dropped_classes = [], []
    for cik, rows in by_cik.items():
        if len(rows) == 1:
            keep = rows[0]
        else:
            # prefer the more liquid class
            keep = max(rows, key=lambda r: (r.volume or 0) * (r.last_sale or 0))
            dropped_classes.extend(
                {"kept": keep.ticker, "dropped": r.ticker, "company": r.name}
                for r in rows if r.ticker != keep.ticker
            )
        record = keep.as_dict()
        record["cik"] = cik
        record["share_classes"] = sorted(r.ticker for r in rows)
        deduped.append(record)

    funnel.append({"stage": "matched to an SEC filer (CIK)", "count": len(deduped) + len(dropped_classes)})
    funnel.append({"stage": "dual-class duplicates collapsed", "count": len(deduped)})

    deduped.sort(key=lambda r: r["market_cap"] or 0, reverse=True)
    if args.limit:
        deduped = deduped[: args.limit]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": provider.name,
        "market_cap_floor_usd": floor,
        "funnel": funnel,
        "dropped_share_classes": dropped_classes,
        "unmatched_tickers": sorted(r.ticker for r in no_cik),
        "listings": deduped,
    }
    path = write_json(DATA_DIR / "universe.json", payload)

    print(f"universe -> {path}")
    for stage in funnel:
        print(f"  {stage['count']:>6}  {stage['stage']}")
    if no_cik:
        print(f"  {len(no_cik):>6}  dropped: no CIK in SEC ticker map (e.g. {', '.join(sorted(r.ticker for r in no_cik)[:6])})")
    sectors: dict[str, int] = {}
    for r in deduped:
        sectors[r["sector"] or "(none)"] = sectors.get(r["sector"] or "(none)", 0) + 1
    print("\n  sectors:")
    for s, n in sorted(sectors.items(), key=lambda kv: -kv[1]):
        print(f"    {n:>5}  {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
