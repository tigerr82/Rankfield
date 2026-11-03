"""The data pack: every month Rankfield has scored, as CSV files in one ZIP.

Built from the append-only monthly records, so it is never a separate file to keep in step: the
site's deploy builds it afresh each time, and a new month adds rows without altering old ones.
It is meant to be uploaded to an assistant that can analyse files, which then answers questions
about any company, metric or month by querying it rather than reading it whole.
"""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import date

from .adjusted import adjusted_prices

METHOD_URL = "https://tigerr82.github.io/Rankfield/#/methodology"
FACTORS = ["quality", "growth", "valuation", "health"]
REBUILT_AFTER_DAYS = 7   # a record made more than a week after its scoring date was rebuilt
# August and September 2026 were scored on the current method after the fact (the project began in
# October); their record dates do not show it, so they are named here.
REBUILT_MONTHS = {"2026-08", "2026-09"}


def unranked_record(scores: dict, coverage: dict) -> dict:
    """Who was not ranked in a month, and why: the insufficient-data list and the exits.

    Written once per month beside the monthly record (never rewritten), because the history
    record holds only the ranked companies.
    """
    entries = []
    for row in scores.get("insufficient", []):
        entries.append({
            "ticker": row["ticker"], "name": row.get("name"), "table": row.get("segment"),
            "kind": "insufficient_data", "reason": row.get("reason"),
        })
    for row in (coverage or {}).get("exits", []):
        entries.append({
            "ticker": row["ticker"], "name": row.get("name"), "table": row.get("segment"),
            "kind": row.get("kind") or "left_ranking", "reason": row.get("reason"),
        })
    return {"scoring_date": scores["meta"]["scoring_date"], "entries": entries}


def _csv(header: list[str], rows) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def _built(meta: dict, backtested: bool) -> str:
    if backtested:
        return "backtested"
    if meta.get("scoring_date", "")[:7] in REBUILT_MONTHS:
        return "rebuilt after the fact"
    try:
        gap = (date.fromisoformat(meta["run_date"][:10]) - date.fromisoformat(meta["scoring_date"][:10])).days
    except (KeyError, ValueError):
        return "live"
    return "rebuilt after the fact" if gap > REBUILT_AFTER_DAYS else "live"


def build_pack(records: dict[str, dict], unranked: dict[str, dict], current: dict, generated: str) -> bytes:
    """`records`: month -> history record. `unranked`: month -> unranked_record. `current`:
    the display payload (scores_full), whose prices are restated weekly and so are used for
    the latest month."""
    months = sorted(records)
    latest = months[-1] if months else None
    specs = {m["key"]: m for m in current.get("metrics", [])}
    seg_label = {s["key"]: s["label"] for s in current.get("segments_meta", [])}
    now_price = {}
    for rows in current.get("segments", {}).values():
        for r in rows:
            now_price[r["ticker"]] = r

    adjusted = adjusted_prices(records, now_price)
    month_rows, score_rows, metric_rows, company_rows = [], [], [], {}
    for month in months:
        rec = records[month]
        meta = rec["meta"]
        counts = {k: v for k, v in meta.get("counts", {}).items() if k != "insufficient"}
        have_unranked = month in unranked
        month_rows.append([
            month, meta["scoring_date"], meta.get("weights_version"),
            _built(meta, rec.get("backtested", False)), sum(counts.values()),
            "yes" if have_unranked else "not recorded",
        ])
        for table, rows in rec["segments"].items():
            for r in rows:
                restated = now_price.get(r["ticker"]) if month == latest else None
                price = restated["price"] if restated else r.get("price")
                change = restated["price_change_pct"] if restated else r.get("price_change_pct")
                f = r.get("factors") or {}
                score_rows.append([
                    month, meta["scoring_date"], r["ticker"], r.get("name"), seg_label.get(table, table),
                    r.get("peer_group") or "", r.get("sector") or "", r.get("rank"), r.get("composite"),
                    *[f.get(k) for k in FACTORS], r.get("rank_change"), r.get("composite_change"),
                    int(bool(r.get("is_new"))), price, adjusted[month].get(r["ticker"]), change, r.get("market_cap"), r.get("coverage"),
                    r.get("fundamentals_asof"), r.get("form"), r.get("filed"), r.get("weights_version"),
                ])
                for key, cell in (r.get("metrics") or {}).items():
                    spec = specs.get(key, {})
                    metric_rows.append([month, r["ticker"], key, spec.get("factor"), cell.get("raw"),
                                        cell.get("pct"), cell.get("basis")])
                company_rows[r["ticker"]] = [r["ticker"], r.get("name"), r.get("exchange"), r.get("cik"),
                                             r.get("sector") or "", seg_label.get(table, table)]

    not_ranked = []
    for month in months:
        for e in unranked.get(month, {}).get("entries", []):
            not_ranked.append([month, e["ticker"], e.get("name"), seg_label.get(e.get("table"), e.get("table")),
                               e.get("kind"), e.get("reason")])

    dictionary = [[m["key"], m["label"], m["factor"], m["unit"],
                   "higher" if m["higher_better"] else "lower", m["formula"],
                   ";".join(m.get("not_for_segments") or [])] for m in current.get("metrics", [])]

    files = {
        "README.txt": _readme(months, generated),
        "months.csv": _csv(["month", "scoring_date", "method_version", "built", "companies_ranked",
                            "not_ranked_recorded"], month_rows),
        "metrics_dictionary.csv": _csv(["metric", "label", "factor", "unit", "better_when", "formula",
                                        "not_scored_for_tables"], dictionary),
        "companies.csv": _csv(["ticker", "name", "exchange", "cik", "sector", "table"],
                              sorted(company_rows.values())),
        "scores_monthly.csv": _csv(
            ["month", "scoring_date", "ticker", "name", "table", "peer_group", "sector", "rank", "composite",
             "quality", "growth", "value", "health", "rank_change", "composite_change", "first_time_ranked",
             "price", "price_adjusted", "price_change_pct", "market_cap", "metric_coverage", "fundamentals_asof", "form",
             "filed", "method_version"], score_rows),
        "metrics_monthly.csv": _csv(["month", "ticker", "metric", "factor", "raw_value", "sector_percentile",
                                     "basis"], metric_rows),
        "not_ranked_monthly.csv": _csv(["month", "ticker", "name", "table", "kind", "reason"], not_ranked),
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, text in files.items():
            z.writestr(name, text)
    return out.getvalue()


def _readme(months: list[str], generated: str) -> str:
    span = f"{months[0]} to {months[-1]}" if months else "no months yet"
    return f"""Rankfield data pack - {span}. Generated {generated}.
Method: {METHOD_URL}

READ THIS FIRST
Rankfield scores are relative rankings within a company's own table and sector or peer group.
They are not recommendations and nothing here is investment advice. An assistant can misread
numbers or sound more certain than the data allows; check anything that matters against the method.

WHAT IS HERE
  months.csv              one row per scored month: method version, whether it was scored on time
                          ("live"), rebuilt after the fact, or backtested, and how many were ranked.
  metrics_dictionary.csv  every metric: factor, unit, whether higher or lower is better, formula,
                          and the tables it is not scored for.
  companies.csv           one row per company ever ranked.
  scores_monthly.csv      one row per company per month: table, rank, composite, the four factor
                          scores (quality, growth, value, health), rank change, price, price_adjusted, market cap.
  metrics_monthly.csv     one row per company per month per metric: raw value and sector percentile.
  not_ranked_monthly.csv  companies that were not ranked in a month and why (where recorded; see
                          months.csv, column not_ranked_recorded).

HOW TO READ IT
  - Scores and percentiles run 0-100 and are relative: 90 means better than about 90% of the
    company's cohort, not a good absolute level.
  - Rank 1 is best within its table (operating, banks, insurers, brokers and managers, REITs,
    pre-revenue). Ranks are not comparable across tables, and table sizes change by month.
  - A metric absent for a company in a month was not scored for its table or could not be computed.
  - Compare months only within the same method_version, or say that the method changed.
  - Months marked "rebuilt after the fact" were scored later on the same method, from the data
    available then; treat them as weaker evidence than live months.
  - price is the close on the scoring date as recorded then. After a split or spin-off an older
    price is on the old basis, so a drop between two months may be a split, not a loss. The latest
    month's price is restated weekly.
  - price_adjusted puts every month on the newest basis (split- and dividend-adjusted), chained
    from the prior-month price each later run re-read. Use it, never price, for returns between
    months. It is empty where the chain cannot be linked (a gap in a company's months).

EXAMPLE QUESTIONS
  - How did the ROIC percentile of MU, NVDA and AMD change month by month?
  - Which companies improved their Value score for three months in a row?
  - Why did this company's rank change since last month? Compare its factor scores.
"""
