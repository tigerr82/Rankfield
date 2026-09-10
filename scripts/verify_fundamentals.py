"""Build-order step 2 - eyeball raw fundamentals for a handful of companies
before scaling the pipeline to 2,000+ names.

Prints the resolved inputs and metric values for a sample spanning several
sectors, including a bank, so the numbers can be checked against the actual
filings. Nothing downstream should be trusted until this output looks right.

Run: python scripts/verify_fundamentals.py [--tickers AAPL,JPM,...]
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rankfield.config import CACHE_DIR, DATA_DIR, load_settings, read_json, user_agent
from rankfield.facts import FactSet
from rankfield.metrics import METRICS, compute_metrics, standardised_unexpected_earnings
from rankfield.providers import get_fundamentals_provider
from rankfield.util import last_day_of_prior_month

DEFAULT = [
    # technology / software
    "AAPL", "MSFT", "NVDA", "ORCL",
    # banks & insurers - these must NOT produce a plausible-looking Health score
    "JPM", "BAC", "PGR",
    # utilities
    "SO", "DUK",
    # industrials
    "CAT", "GE", "UNP",
    # consumer
    "KO", "WMT", "MCD",
    # energy / materials
    "XOM", "NEM",
    # health care
    "JNJ", "LLY",
    # real estate
    "AMT",
]


def fmt(value, unit: str) -> str:
    if value is None:
        return "        --"
    if unit == "pct":
        return f"{value * 100:9.2f}%"
    if unit == "pp":
        return f"{value * 100:9.2f}pp"
    if unit == "x":
        return f"{value:9.2f}x"
    return f"{value:10.2f}"


def money(value) -> str:
    if value is None:
        return "--"
    for scale, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(value) >= scale:
            return f"{value / scale:,.2f}{suffix}"
    return f"{value:,.0f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", default=",".join(DEFAULT))
    parser.add_argument("--as-of", default=None, help="scoring date (default: last day of prior month)")
    args = parser.parse_args()

    settings = load_settings()
    as_of = date.fromisoformat(args.as_of) if args.as_of else last_day_of_prior_month(date.today())
    universe = read_json(DATA_DIR / "universe.json", {"listings": []})
    by_ticker = {r["ticker"]: r for r in universe["listings"]}

    edgar = get_fundamentals_provider(
        "edgar", user_agent=user_agent(), cache_dir=CACHE_DIR / "facts",
        per_sec=settings["http"]["sec_rate_limit_per_sec"],
    )
    cik_map = edgar.ticker_cik_map()

    print(f"Point-in-time as of {as_of}: only facts filed on or before this date are visible.\n")
    for ticker in [t.strip().upper() for t in args.tickers.split(",") if t.strip()]:
        listing = by_ticker.get(ticker)
        cik = (listing or {}).get("cik") or cik_map.get(ticker)
        if not cik:
            print(f"{ticker}: no CIK\n")
            continue
        raw = edgar.company_facts(cik)
        if not raw:
            print(f"{ticker}: no XBRL facts\n")
            continue
        fs = FactSet(raw, as_of)
        mcap = (listing or {}).get("market_cap")
        result = compute_metrics(fs, market_cap=mcap, tax_clamp=tuple(settings["scoring"]["effective_tax_clamp"]))
        prov = result["provenance"]
        inputs = result["raw_inputs"]

        sector = (listing or {}).get("sector", "?")
        print(f"{ticker:<6} {fs.entity}")
        print(f"       sector={sector}  mcap={money(mcap)}  forms={','.join(sorted(fs.forms)) or '-'}  quarters={fs.quarters_filed}")
        print(f"       fundamentals as of {prov['fundamentals_asof']} (filed {prov['filed']}, {prov['form']}, {prov['basis']})")
        print(f"       EBIT={money(inputs['ebit'])} [{prov['ebit_source']}]  D&A={money(inputs['da'])}  "
              f"OCF={money(inputs['ocf'])}  capex={money(inputs['capex'])}")
        print(f"       assets={money(inputs['assets'])}  equity={money(inputs['equity'])}  "
              f"cash={money(inputs['cash'])}  debt={money(inputs['debt'])} [{prov['debt_source']}]  EV={money(inputs['ev'])}")
        print(f"       effective tax {prov['effective_tax_rate']:.1%} ({prov['tax_rate_source']})")
        for m in METRICS:
            value = result["values"][m["key"]]
            reason = result["missing"].get(m["key"], "")
            print(f"         {m['short']:<12}{fmt(value, m['unit'])}   {reason}")
        sue = standardised_unexpected_earnings(fs)
        print(f"         {'SUE (unused)':<12}{fmt(sue, 'score')}")
        for note in result["notes"]:
            print(f"       note: {note}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
