"""Note, on an existing data/fundamentals.json, which stale-looking companies have a newer filing.

fetch_fundamentals does this for every run. This is the same step on its own, for a
fundamentals file that was built before the rule existed: only the companies whose latest
readable report is older than the freshness rule are looked up (a few dozen requests), and
nothing else in the file is touched. Scoring is then re-run on the whole file, because a
percentile moves when a company joins its cohort.

Run: python scripts/annotate_newer_filings.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rankfield.config import DATA_DIR, load_settings, read_json, user_agent, write_json
from rankfield.providers import get_fundamentals_provider


def main() -> int:
    settings = load_settings()
    payload = read_json(DATA_DIR / "fundamentals.json")
    if not payload:
        print("data/fundamentals.json missing", file=sys.stderr)
        return 1
    as_of = date.fromisoformat(payload["as_of"])
    limit = settings["universe"]["max_report_age_days"]
    edgar = get_fundamentals_provider(
        "edgar", user_agent=user_agent(), per_sec=settings["http"]["sec_rate_limit_per_sec"])

    looked, found = 0, 0
    for ticker, record in payload["companies"].items():
        latest = (record.get("provenance") or {}).get("latest_balance_sheet")
        if not latest or (as_of - date.fromisoformat(latest)).days <= limit:
            record.setdefault("newer_filing", None)
            continue
        looked += 1
        filing = edgar.newest_periodic_filing(record["cik"], as_of)
        record["newer_filing"] = filing if filing and filing["report_date"] > latest else None
        found += record["newer_filing"] is not None
    write_json(DATA_DIR / "fundamentals.json", payload, compact=True)
    print(f"{looked} companies with a stale readable report looked up; {found} have a newer filing on record")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
