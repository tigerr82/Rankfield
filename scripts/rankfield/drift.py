"""Month-over-month data drift: what the pipeline lost since the last scoring run.

Companies change the XBRL tags they report under - about 1.6% of inputs a year
switch tag and are absorbed by the fallback chains, and about 0.6% (roughly
three inputs a month across the scored universe) move to a tag no chain reads.
Those do not produce wrong numbers - the freshness rule turns them into gaps -
but left alone the gaps accumulate. This report puts them in front of a person
each month, with the tags the company reports instead, so fixing one is a
one-line change rather than an investigation.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

# A metric that disappears for one of these reasons reflects the company's
# economics, not its tagging, and is not drift.
ECONOMIC_REASONS = ("negative", "zero", "turned negative")


def _is_economic(reason: str) -> bool:
    return any(word in reason.lower() for word in ECONOMIC_REASONS)


def build_drift_report(
    *,
    scoring_date: date,
    prior_scoring_date: date,
    scored_rows: list[dict],
    prior_rows: list[dict] | None,
    eligible_rows: list[dict],
    insufficient_rows: list[dict],
    thresholds: dict,
) -> dict:
    provenance = {r["ticker"]: r.get("provenance") or {} for r in eligible_rows}
    insufficient = {r["ticker"]: r.get("reason") for r in insufficient_rows}
    now = {r["ticker"]: r for r in scored_rows}

    # Tags a company stopped using recently: the actionable ones. A tag last
    # used in 2015 was dealt with long ago; one last used a year ago is news.
    horizon = (scoring_date - timedelta(days=thresholds["recently_abandoned_days"])).isoformat()
    recently_abandoned = [
        {"ticker": t, **s, "candidates": p.get("unmapped_candidates", {})}
        for t, p in sorted(provenance.items())
        for s in p.get("stale_inputs", [])
        if s["last_reported"] >= horizon
    ]

    report = {
        "scoring_date": scoring_date.isoformat(),
        "prior_scoring_date": prior_scoring_date.isoformat(),
        "thresholds": thresholds,
        "scored_now": len(now),
        "recently_abandoned_tags": recently_abandoned,
    }
    if prior_rows is None:
        report.update(status="baseline", scored_prior=None, scored_change_pct=None,
                      dropped_out=[], metrics_lost=[], metrics_lost_economic=[], metrics_lost_by_metric={})
        return report

    before = {r["ticker"]: r for r in prior_rows}
    dropped_out = [
        {"ticker": t,
         "reason": insufficient.get(t) or "no longer eligible (universe, price, filing or liquidity filters)",
         "candidates": provenance.get(t, {}).get("unmapped_candidates", {})}
        for t in sorted(set(before) - set(now))
    ]
    lost, lost_economic = [], []
    for t in sorted(set(before) & set(now)):
        for key, cell in before[t].get("metrics", {}).items():
            if cell.get("pct") is None:
                continue
            if now[t].get("metrics", {}).get(key, {}).get("pct") is not None:
                continue
            reason = now[t].get("missing_reasons", {}).get(key) or "no longer applicable to the segment"
            entry = {"ticker": t, "metric": key, "reason": reason,
                     "candidates": provenance.get(t, {}).get("unmapped_candidates", {})}
            (lost_economic if _is_economic(reason) else lost).append(entry)

    change_pct = round(100.0 * (len(now) - len(before)) / len(before), 2) if before else 0.0
    if change_pct <= -thresholds["block_scored_drop_pct"]:
        status = "block"
    elif change_pct <= -thresholds["warn_scored_drop_pct"] or lost or dropped_out or recently_abandoned:
        status = "warn"
    else:
        status = "ok"
    report.update(
        status=status,
        scored_prior=len(before),
        scored_change_pct=change_pct,
        dropped_out=dropped_out,
        metrics_lost=lost,
        metrics_lost_economic=lost_economic,
        metrics_lost_by_metric=dict(Counter(e["metric"] for e in lost).most_common()),
    )
    return report


def _candidates(c: dict) -> str:
    return "; ".join(f"{family}: {', '.join(tags)}" for family, tags in c.items()) or "-"


def render_issue(report: dict) -> str:
    """Markdown for the GitHub issue the monthly run opens when there is drift."""
    lines = [
        f"## Data drift, scoring date {report['scoring_date']} - status **{report['status']}**",
        "",
        f"Scored: {report['scored_now']} (previous month {report['scored_prior']}, "
        f"change {report['scored_change_pct']}%).",
        "",
    ]
    if report["status"] == "block":
        lines += [
            f"**Publication was blocked**: the scored universe fell by more than "
            f"{report['thresholds']['block_scored_drop_pct']}%. This usually means a taxonomy-wide tag "
            "change. Nothing was committed; fix the tag lists and re-run the workflow.",
            "",
        ]
    sections = [
        ("Companies that dropped out of the ranking", report["dropped_out"],
         lambda e: f"| {e['ticker']} | {e['reason']} | {_candidates(e['candidates'])} |",
         "| Ticker | Reason | Tags reported today that no list reads |"),
        ("Metrics lost since last month (data, not economics)", report["metrics_lost"],
         lambda e: f"| {e['ticker']} | {e['metric']} | {e['reason']} | {_candidates(e['candidates'])} |",
         "| Ticker | Metric | Reason | Tags reported today that no list reads |"),
        ("Tags companies recently stopped using", report["recently_abandoned_tags"],
         lambda e: f"| {e['ticker']} | {e['concept']} | {e['last_reported']} | {_candidates(e['candidates'])} |",
         "| Ticker | Abandoned tag | Last reported | Tags reported today that no list reads |"),
    ]
    for title, rows, fmt, header in sections:
        lines += [f"### {title} ({len(rows)})", ""]
        if rows:
            separator = "|" + "---|" * (header.count("|") - 1)
            lines += [header, separator] + [fmt(e) for e in rows[:100]]
            if len(rows) > 100:
                lines.append(f"\n...and {len(rows) - 100} more in `data/drift_report.json`.")
        else:
            lines.append("None.")
        lines.append("")
    lines += [
        "A candidate tag is added to the matching list in `scripts/rankfield/metrics.py` "
        "(one line, plus a test). Figures from abandoned tags are never used, so nothing "
        "published is wrong in the meantime - only incomplete.",
    ]
    return "\n".join(lines)
