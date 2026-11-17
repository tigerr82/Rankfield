"""Research measures recorded beside each month's rank. None of them is scored.

Three candidates the literature ties to later returns and the four factors do not contain:
net buyback yield, earnings accruals, and price momentum (momentum is cut from the price
series in fetch_prices.py). They are stored so that a year of history can show whether adding
one would improve the ranking. They change no score and no rank, and a methodology version
that used one would apply only to months after it was adopted.

Definitions, chosen once like the metrics in metrics.py:

  net_payout_yield  (common stock repurchased - common stock issued for cash), trailing twelve
                    months, over market cap. Positive = the company returned equity to its
                    holders, negative = it raised equity. Share-based pay shows up only as far
                    as the company sells shares, so it is a partial view of dilution.
                    Cash-flow dollars are split-proof, which a share count is not.
  accruals          (net income - operating cash flow), trailing twelve months, over average
                    total assets (latest and a year earlier). High = more of the profit is
                    accounting rather than cash. Meaningless for banks and insurers: read it by
                    table.
"""
from __future__ import annotations

from datetime import timedelta

from .facts import FactSet
from .metrics import ASSETS, NET_INCOME, OPERATING_CASH_FLOW
from .util import parse_iso, safe_div

REPURCHASE = ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity"]
ISSUANCE = ["ProceedsFromIssuanceOfCommonStock", "ProceedsFromIssuanceOrSaleOfEquity"]


def _val(fact: dict | None):
    return fact["val"] if fact and fact.get("val") is not None else None


def shadow_metrics(fs: FactSet, market_cap: float | None) -> dict:
    """{values: {net_payout_yield, accruals}, sources: {...}}; a measure that cannot be
    computed is None with its reason, never zero."""
    values: dict[str, float | None] = {"net_payout_yield": None, "accruals": None}
    sources: dict[str, str] = {}

    ocf_fact = fs.ttm(OPERATING_CASH_FLOW)
    bought = _val(fs.ttm(REPURCHASE))
    sold = _val(fs.ttm(ISSUANCE))
    if not market_cap:
        sources["net_payout_yield"] = "market cap unavailable"
    elif ocf_fact is None:
        sources["net_payout_yield"] = "no cash-flow statement resolved"
    else:
        # A filer tags a line only in a period it has an amount, so with a cash-flow statement
        # on file and neither line tagged, the company bought and sold no stock that year.
        values["net_payout_yield"] = ((bought or 0.0) - (sold or 0.0)) / market_cap
        sources["net_payout_yield"] = (
            "repurchases less issuance, trailing twelve months" if (bought is not None or sold is not None)
            else "neither repurchases nor issuance tagged: treated as none"
        )

    income_fact = fs.ttm(NET_INCOME)
    assets_fact = fs.instant(ASSETS)
    if income_fact is None or ocf_fact is None or assets_fact is None:
        sources["accruals"] = "net income, operating cash flow or total assets unavailable"
    elif income_fact.get("end") != ocf_fact.get("end"):
        sources["accruals"] = "net income and cash flow cover different periods"
    else:
        prior = _val(fs.instant_near(ASSETS, (parse_iso(assets_fact["end"]) - timedelta(days=365)).isoformat()))
        average = (assets_fact["val"] + prior) / 2 if prior else assets_fact["val"]
        values["accruals"] = safe_div(income_fact["val"] - ocf_fact["val"], average) if average and average > 0 else None
        sources["accruals"] = "(net income - operating cash flow) over average assets" if prior else \
            "(net income - operating cash flow) over closing assets (no prior-year balance sheet)"
        if values["accruals"] is None:
            sources["accruals"] = "assets zero or negative"
    return {"values": values, "sources": sources}
