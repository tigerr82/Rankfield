"""The metric definitions, implemented exactly as specified in the brief's appendix.

Every metric below has more than one legitimate industry convention. One
definition is picked, applied everywhere, and published on the methodology page.
Do not substitute a "better" variant here without changing the published text.

Missing means missing. A metric that cannot be computed is None, is logged to
the coverage report with a reason, and its weight is renormalised away at
scoring time. It is never imputed as zero.
"""
from __future__ import annotations

from datetime import timedelta

from .facts import FactSet
from .util import mean, parse_iso, safe_div, stdev

# --------------------------------------------------------------- tag lists
# Prioritised US-GAAP tags per line item; the first that resolves a period wins.

REVENUE = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "RevenuesNetOfInterestExpense",
]
COGS = [
    "CostOfGoodsAndServicesSold",
    "CostOfRevenue",
    "CostOfGoodsSold",
    "CostOfServices",
    # Capital-intensive filers (utilities, energy) commonly tag cost of revenue
    # only in its ex-depreciation form. Accepting it keeps GPOA computable for
    # those sectors; the resolved tag is recorded in provenance so the small
    # definitional difference stays auditable rather than silent.
    "CostOfGoodsAndServicesSoldExcludingDepreciationDepletionAndAmortization",
    "CostOfRevenueExcludingDepreciationDepletionAndAmortization",
    "CostOfGoodsSoldExcludingDepreciationDepletionAndAmortization",
]
GROSS_PROFIT = ["GrossProfit"]
OPERATING_INCOME = ["OperatingIncomeLoss"]
OPERATING_EXPENSES = ["OperatingExpenses", "OperatingCostsAndExpenses"]
COSTS_AND_EXPENSES = ["CostsAndExpenses"]
PRETAX_INCOME = [
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
]
INCOME_TAX = ["IncomeTaxExpenseBenefit", "IncomeTaxExpenseBenefitContinuingOperations"]
NET_INCOME = ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"]
DEPRECIATION_AMORT = [
    "DepreciationDepletionAndAmortization",
    "DepreciationAmortizationAndAccretionNet",
    "DepreciationAndAmortization",
    "Depreciation",
]
OPERATING_CASH_FLOW = [
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
]
CAPEX = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    "PaymentsForCapitalImprovements",
]
ASSETS = ["Assets"]
ASSETS_CURRENT = ["AssetsCurrent"]
LIABILITIES = ["Liabilities"]
# Many filers tag only the balance-sheet total, not total liabilities. The
# difference is exact arithmetic, not a change of definition.
LIABILITIES_AND_EQUITY = ["LiabilitiesAndStockholdersEquity"]
LIABILITIES_CURRENT = ["LiabilitiesCurrent"]
EQUITY = [
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
]
RETAINED_EARNINGS = ["RetainedEarningsAccumulatedDeficit"]
CASH = [
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    "CashAndDueFromBanks",
]
DEBT_COMBINED = ["DebtLongtermAndShorttermCombinedAmount"]
DEBT_LT_NONCURRENT = ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"]
DEBT_LT_CURRENT = ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"]
DEBT_SHORT = ["ShortTermBorrowings", "OtherShortTermBorrowings", "CommercialPaper"]
DEBT_LT_TOTAL = ["LongTermDebt"]
EPS_DILUTED = ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted", "EarningsPerShareBasic"]

# ------------------------------------------------------------- the registry
# `factor` groups metrics for display and weighting; `higher_better` sets the
# direction of the percentile rank.

METRICS: list[dict] = [
    {"key": "roic", "label": "Return on Invested Capital", "short": "ROIC", "factor": "quality",
     "higher_better": True, "unit": "pct",
     "formula": "NOPAT / average invested capital, where NOPAT = EBIT x (1 - effective tax rate) "
                "and invested capital = total debt + shareholders' equity - cash."},
    {"key": "gpoa", "label": "Gross Profits / Assets", "short": "GPOA", "factor": "quality",
     "higher_better": True, "unit": "pct",
     "formula": "(Revenue - COGS) / total assets (Novy-Marx)."},
    {"key": "earn_var", "label": "Earnings Variability", "short": "EarnVar", "factor": "quality",
     "higher_better": False, "unit": "pct",
     "formula": "Standard deviation of return on assets across the last five fiscal years. "
                "Lower is better, so the percentile is inverted."},
    # Moved from Growth in methodology 1.1. A rising gross-profits-to-assets ratio
    # is a quality signal - the business extracting more from what it owns - which
    # is where Asness et al.'s Quality-Minus-Junk places it. Not ROIC-conditioned.
    {"key": "delta_gpoa", "label": "Change in Gross Profitability", "short": "dGPOA", "factor": "quality",
     "higher_better": True, "unit": "pp",
     "formula": "GPOA in the latest fiscal year minus GPOA three fiscal years earlier, in percentage "
                "points - improving efficiency, not growth."},

    {"key": "ebit_ev", "label": "EBIT / EV", "short": "EBIT/EV", "factor": "valuation",
     "higher_better": True, "unit": "pct",
     "formula": "EBIT / enterprise value. The primary value metric (Gray & Carlisle)."},
    {"key": "ebitda_ev", "label": "EBITDA / EV", "short": "EBITDA/EV", "factor": "valuation",
     "higher_better": True, "unit": "pct",
     "formula": "(EBIT + depreciation & amortisation) / enterprise value."},
    {"key": "fcf_ev", "label": "FCF / EV", "short": "FCF/EV", "factor": "valuation",
     "higher_better": True, "unit": "pct",
     "formula": "(Operating cash flow - capital expenditure) / enterprise value."},

    # Growth is revenue growth alone. Until methodology 1.1 it was averaged with
    # dGPOA, which measures efficiency rather than growth: a company holding its
    # asset base flat while selling a little more scored as a fast grower, so a
    # 10.5% revenue grower outscored 12.5% and 16.1% growers on "Growth".
    {"key": "rev_growth", "label": "Revenue Growth (3-yr CAGR)", "short": "Rev CAGR", "factor": "growth",
     "higher_better": True, "unit": "pct",
     "formula": "Three-year compound annual growth rate of revenue. ROIC-conditioned: inverted where "
                "ROIC is at or below the hurdle, so expansion that destroys value is not rewarded."},

    {"key": "debt_equity", "label": "Debt / Equity", "short": "D/E", "factor": "health",
     "higher_better": False, "unit": "x",
     "formula": "Total debt / total shareholders' equity. Null when equity is negative."},
    {"key": "net_debt_ebitda", "label": "Net Debt / EBITDA", "short": "ND/EBITDA", "factor": "health",
     "higher_better": False, "unit": "x",
     "formula": "(Total debt - cash) / EBITDA. Null when EBITDA is zero or negative - a negative "
                "multiple must never rank as cheap."},
    {"key": "altman_z", "label": "Altman Z-score (Z'')", "short": "Altman Z", "factor": "health",
     "higher_better": True, "unit": "score",
     "formula": "Z'' = 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4, the non-manufacturing variant. "
                "Safe > 2.6, grey 1.1-2.6, distress < 1.1."},
]

METRIC_KEYS = [m["key"] for m in METRICS]
METRICS_BY_KEY = {m["key"]: m for m in METRICS}

FACTORS = [
    {"key": "quality", "label": "Quality", "short": "Quality", "price_dependent": False},
    {"key": "growth", "label": "Growth", "short": "Growth", "price_dependent": False},
    {"key": "valuation", "label": "Value", "short": "Value", "price_dependent": True},
    {"key": "health", "label": "Financial Health", "short": "Health", "price_dependent": False},
]
FACTOR_KEYS = [f["key"] for f in FACTORS]


def _val(fact: dict | None):
    return fact["val"] if fact and fact.get("val") is not None else None


def _sum_present(*values):
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def total_debt(fs: FactSet, on_or_before=None):
    """Total debt, composed from whichever tags the filer actually uses.

    Returns (value, how) so the resolution path is auditable in the coverage
    report - filers disagree about whether `LongTermDebt` includes the current
    portion, and that disagreement is worth recording rather than hiding.
    """
    combined = _val(fs.instant(DEBT_COMBINED, on_or_before))
    if combined is not None:
        return combined, "combined-tag"
    lt_noncurrent = _val(fs.instant(DEBT_LT_NONCURRENT, on_or_before))
    lt_current = _val(fs.instant(DEBT_LT_CURRENT, on_or_before))
    short = _val(fs.instant(DEBT_SHORT, on_or_before))
    if lt_noncurrent is not None:
        return _sum_present(lt_noncurrent, lt_current, short), "noncurrent+current+short"
    lt_total = _val(fs.instant(DEBT_LT_TOTAL, on_or_before))
    if lt_total is not None:
        return _sum_present(lt_total, short), "longtermdebt+short"
    partial = _sum_present(lt_current, short)
    if partial is not None:
        return partial, "current+short-only"
    return None, "unresolved"


def _gross_profit(fs: FactSet):
    """Returns (value, anchoring fact, how it resolved)."""
    revenue = fs.ttm(REVENUE)
    cogs = fs.ttm(COGS)
    if revenue and cogs and revenue["val"] is not None and cogs["val"] is not None:
        return revenue["val"] - cogs["val"], revenue, f"Rev - {cogs['concept']}"
    direct = fs.ttm(GROSS_PROFIT)
    if direct and direct["val"] is not None:
        return direct["val"], direct, "GrossProfit"
    return None, revenue, "unresolved"


def _ebit(fs: FactSet):
    """EBIT is rarely tagged. Operating income is the accepted approximation;
    where it is absent, derive it from the income statement."""
    op = fs.ttm(OPERATING_INCOME)
    if op and op["val"] is not None:
        return op["val"], op, "OperatingIncomeLoss"
    revenue = fs.ttm(REVENUE)
    cogs = fs.ttm(COGS)
    opex = fs.ttm(OPERATING_EXPENSES)
    if revenue and cogs and opex and None not in (revenue["val"], cogs["val"], opex["val"]):
        return revenue["val"] - cogs["val"] - opex["val"], revenue, "derived: Rev - COGS - OpEx"
    costs = fs.ttm(COSTS_AND_EXPENSES)
    if revenue and costs and None not in (revenue["val"], costs["val"]):
        return revenue["val"] - costs["val"], revenue, "derived: Rev - CostsAndExpenses"
    return None, revenue, "unresolved"


def _effective_tax_rate(fs: FactSet, clamp: tuple[float, float]) -> tuple[float, str]:
    tax = fs.ttm(INCOME_TAX)
    pretax = fs.ttm(PRETAX_INCOME)
    lo, hi = clamp
    if tax and pretax and pretax["val"] not in (None, 0) and pretax["val"] > 0:
        rate = tax["val"] / pretax["val"]
        return min(max(rate, lo), hi), "reported"
    # Loss-making or untagged: fall back to the US statutory rate rather than
    # dropping ROIC entirely. Documented on the methodology page.
    return 0.21, "statutory-fallback"


def _annual_gpoa(fs: FactSet, years_back: int):
    """GPOA computed from a fiscal year `years_back` years ago, aligned on
    period end dates."""
    revenues = fs.annual_series(REVENUE, 6)
    if len(revenues) <= years_back:
        return None
    target = revenues[years_back]
    cogs_rows = {f["end"]: f for f in fs.annual_series(COGS, 6)}
    cogs = cogs_rows.get(target["end"])
    if cogs is None:
        near = [f for f in fs.annual_series(COGS, 6)
                if abs((parse_iso(f["end"]) - parse_iso(target["end"])).days) <= 20]
        cogs = near[0] if near else None
    assets = fs.instant_near(ASSETS, target["end"])
    if not cogs or not assets or target["val"] is None:
        return None
    return safe_div(target["val"] - cogs["val"], assets["val"])


def compute_metrics(fs: FactSet, *, market_cap: float, tax_clamp=(0.0, 0.35)) -> dict:
    """Raw metric values plus provenance for one company.

    Returns {values, missing, provenance, notes, fundamentals_asof}.
    """
    values: dict[str, float | None] = {k: None for k in METRIC_KEYS}
    missing: dict[str, str] = {}
    notes: list[str] = []

    assets_fact = fs.instant(ASSETS)
    assets = _val(assets_fact)
    equity = _val(fs.instant(EQUITY))
    cash = _val(fs.instant(CASH))
    liabilities = _val(fs.instant(LIABILITIES))
    if liabilities is None:
        balance_total = _val(fs.instant(LIABILITIES_AND_EQUITY))
        if balance_total is not None and _val(fs.instant(EQUITY)) is not None:
            liabilities = balance_total - _val(fs.instant(EQUITY))
    assets_current = _val(fs.instant(ASSETS_CURRENT))
    liabilities_current = _val(fs.instant(LIABILITIES_CURRENT))
    retained = _val(fs.instant(RETAINED_EARNINGS))
    debt, debt_path = total_debt(fs)

    ebit, ebit_fact, ebit_path = _ebit(fs)
    da = _val(fs.ttm(DEPRECIATION_AMORT))
    ocf = _val(fs.ttm(OPERATING_CASH_FLOW))
    capex = _val(fs.ttm(CAPEX))
    gross_profit, revenue_fact, gp_source = _gross_profit(fs)
    tax_rate, tax_path = _effective_tax_rate(fs, tax_clamp)

    asof_fact = ebit_fact or revenue_fact or assets_fact
    provenance = {
        "fundamentals_asof": (asof_fact or {}).get("end"),
        "filed": (asof_fact or {}).get("filed"),
        "accn": (asof_fact or {}).get("accn"),
        "form": (asof_fact or {}).get("form"),
        "basis": (asof_fact or {}).get("basis"),
        "ebit_source": ebit_path,
        "debt_source": debt_path,
        "gross_profit_source": gp_source,
        "tax_rate_source": tax_path,
        "effective_tax_rate": round(tax_rate, 4),
    }

    # ---------------------------------------------------------- Quality
    # ROIC: NOPAT over AVERAGE invested capital (open + close) / 2.
    if ebit is not None and debt is not None and equity is not None:
        close_ic = debt + equity - (cash or 0.0)
        prior_end = (parse_iso(assets_fact["end"]) - timedelta(days=365)).isoformat() if assets_fact else None
        open_ic = None
        if prior_end:
            prior_debt, _ = total_debt(fs, on_or_before=parse_iso(prior_end))
            prior_equity = _val(fs.instant_near(EQUITY, prior_end))
            prior_cash = _val(fs.instant_near(CASH, prior_end))
            if prior_debt is not None and prior_equity is not None:
                open_ic = prior_debt + prior_equity - (prior_cash or 0.0)
        avg_ic = (close_ic + open_ic) / 2 if open_ic is not None else close_ic
        if open_ic is None:
            notes.append("ROIC uses closing invested capital only (no comparable prior balance sheet).")
        nopat = ebit * (1 - tax_rate)
        roic = safe_div(nopat, avg_ic) if avg_ic and avg_ic > 0 else None
        if roic is None:
            missing["roic"] = "invested capital zero or negative"
        values["roic"] = roic
    else:
        missing["roic"] = "EBIT, debt or equity unavailable"

    if gross_profit is not None and assets:
        values["gpoa"] = safe_div(gross_profit, assets)
        if values["gpoa"] is None:
            missing["gpoa"] = "total assets zero"
    else:
        missing["gpoa"] = "gross profit or total assets unavailable"

    net_income_years = fs.annual_series(NET_INCOME, 5)
    roas = []
    for row in net_income_years:
        a = fs.instant_near(ASSETS, row["end"])
        r = safe_div(row["val"], _val(a)) if a else None
        if r is not None:
            roas.append(r)
    if len(roas) >= 5:
        values["earn_var"] = stdev(roas)
    else:
        missing["earn_var"] = f"fewer than 5 fiscal years of earnings ({len(roas)})"

    # ------------------------------------------------------------ Value
    ev = None
    if market_cap and debt is not None:
        ev = market_cap + debt - (cash or 0.0)
    if ev is None:
        # Name the input that is actually absent. These reasons are published in
        # the coverage report and on the stock page, so a wrong one sends
        # somebody debugging the wrong thing.
        if not market_cap and debt is None:
            cause = "market cap and total debt both unavailable"
        elif not market_cap:
            cause = "market cap unavailable"
        else:
            cause = "total debt unresolved"
        for k in ("ebit_ev", "ebitda_ev", "fcf_ev"):
            missing[k] = f"enterprise value unavailable ({cause})"
    elif ev <= 0:
        for k in ("ebit_ev", "ebitda_ev", "fcf_ev"):
            missing[k] = "negative enterprise value"
    else:
        if ebit is not None:
            values["ebit_ev"] = ebit / ev  # a true negative is kept: genuinely poor
        else:
            missing["ebit_ev"] = "EBIT unavailable"
        if ebit is not None and da is not None:
            values["ebitda_ev"] = (ebit + da) / ev
        else:
            missing["ebitda_ev"] = "EBIT or D&A unavailable"
        if ocf is not None and capex is not None:
            values["fcf_ev"] = (ocf - capex) / ev
        elif ocf is not None:
            missing["fcf_ev"] = "capital expenditure unavailable"
        else:
            missing["fcf_ev"] = "operating cash flow unavailable"

    # ----------------------------------------------------------- Growth
    # Both endpoints come from the ANNUAL series, so the comparison is
    # like-for-like.
    #
    # Using the trailing-twelve-month GPOA as the near endpoint looked fresher
    # but compared unlike things: the TTM figure divides by the latest
    # quarter-end balance sheet, while the historical figure divides by a fiscal
    # year-end one. For a December filer scored in August that is a balance
    # sheet six months newer, so any company growing its asset base was
    # penalised for the calendar rather than for its economics - Alphabet's
    # decline read -13.4pp instead of -2.5pp. Microsoft, whose fiscal year ends
    # in June, was unaffected, which is what identified the artifact: the
    # distortion tracked the fiscal calendar, not the business.
    gpoa_now = _annual_gpoa(fs, 0)
    gpoa_then = _annual_gpoa(fs, 3)
    if gpoa_now is not None and gpoa_then is not None:
        values["delta_gpoa"] = gpoa_now - gpoa_then
    else:
        missing["delta_gpoa"] = "fewer than 4 fiscal years of revenue/COGS/assets"

    revenues = fs.annual_series(REVENUE, 4)
    if len(revenues) >= 4 and revenues[3]["val"] and revenues[3]["val"] > 0 and revenues[0]["val"] is not None:
        ratio = revenues[0]["val"] / revenues[3]["val"]
        values["rev_growth"] = (ratio ** (1 / 3)) - 1 if ratio > 0 else None
        if values["rev_growth"] is None:
            missing["rev_growth"] = "revenue turned negative"
    else:
        missing["rev_growth"] = "fewer than 4 fiscal years of revenue"

    # --------------------------------------------------- Financial Health
    if debt is None:
        missing["debt_equity"] = "total debt unresolved"
        missing["net_debt_ebitda"] = "total debt unresolved"
    elif equity is None:
        missing["debt_equity"] = "shareholders' equity unavailable"
    elif equity <= 0:
        missing["debt_equity"] = "negative shareholders' equity"
    else:
        values["debt_equity"] = debt / equity

    ebitda = (ebit + da) if (ebit is not None and da is not None) else None
    if debt is not None:
        if ebitda is None:
            missing["net_debt_ebitda"] = "EBITDA unavailable"
        elif ebitda <= 0:
            missing["net_debt_ebitda"] = "EBITDA zero or negative"
        else:
            values["net_debt_ebitda"] = (debt - (cash or 0.0)) / ebitda

    z_inputs = {
        "working_capital": (assets_current - liabilities_current)
        if None not in (assets_current, liabilities_current) else None,
        "retained": retained,
        "ebit": ebit,
        "equity": equity,
        "liabilities": liabilities,
        "assets": assets,
    }
    if all(v is not None for v in z_inputs.values()) and assets:
        x1 = z_inputs["working_capital"] / assets
        x2 = retained / assets
        x3 = ebit / assets
        x4 = safe_div(equity, liabilities)
        if x4 is None:
            missing["altman_z"] = "total liabilities zero"
        else:
            values["altman_z"] = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
    else:
        absent = [k for k, v in z_inputs.items() if v is None]
        missing["altman_z"] = "missing " + ", ".join(absent)

    return {
        "values": values,
        "missing": missing,
        "provenance": provenance,
        "notes": notes,
        "raw_inputs": {
            "assets": assets, "equity": equity, "cash": cash, "debt": debt,
            "ebit": ebit, "da": da, "ocf": ocf, "capex": capex,
            "gross_profit": gross_profit, "market_cap": market_cap, "ev": ev,
        },
    }


def standardised_unexpected_earnings(fs: FactSet) -> float | None:
    """SUE, per the appendix.

    Implemented and tested, but NOT part of any factor: the factor structure is
    fixed at 3-4 metrics each and none of the four includes an earnings-surprise
    term. Kept here so the formula exists in one place if a future version
    weights it.
    """
    quarterly = [
        f for f in fs.durations(EPS_DILUTED)
        if f["val"] is not None and 80 <= (parse_iso(f["end"]) - parse_iso(f["start"])).days <= 100
    ]
    quarterly.sort(key=lambda f: f["end"])
    if len(quarterly) < 13:
        return None
    eps = [f["val"] for f in quarterly]
    yoy = [eps[i] - eps[i - 4] for i in range(4, len(eps))]
    if len(yoy) < 9:
        return None
    drift = mean(yoy[-9:-1])
    surprises = [yoy[i] - drift for i in range(len(yoy) - 8, len(yoy))]
    sd = stdev(surprises)
    floor = max(0.01 * abs(eps[-1]), 0.01)
    sd = max(sd or 0.0, floor)
    return (yoy[-1] - drift) / sd
