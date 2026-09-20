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

import math
import re

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
FactSet.LARGEST_WINS.add(tuple(REVENUE))  # the revenue tags nest: take the total
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
    # The taxonomy's singular "Service" spelling; Casey's and PSEG moved to it.
    "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
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
# Interest on borrowings only. InterestExpenseOperating is deliberately absent:
# for a bank it is interest paid on deposits - the cost of its product - and
# adding it back would manufacture an "EBIT" for JPMorgan that means nothing.
INTEREST_EXPENSE = ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt", "InterestAndDebtExpense"]
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
    "PaymentsToAcquireOtherPropertyPlantAndEquipment",
    "PaymentsToAcquireOtherProductiveAssets",
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
# Within each list the first tag that resolves a period wins, so the later
# entries - where companies put convertible, unsecured and senior notes when they
# stop using the general tags (Cadence, Palo Alto Networks, Cloudflare) - fill
# gaps without double counting.
DEBT_LT_NONCURRENT = [
    "LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations",
    "UnsecuredLongTermDebt", "ConvertibleDebtNoncurrent", "SecuredLongTermDebt", "LongTermNotesPayable",
    # Software filers fund themselves with convertible notes and tag them here
    # rather than under any general debt tag: Datadog's $986M at June 2026,
    # DoorDash's $2.7B, HubSpot's. The discovery report had been listing this tag
    # as unmapped for 18 companies a month (1.8). Only tags that hold a filer's
    # whole borrowing belong here - see the note below on the ones that do not.
    "ConvertibleLongTermNotesPayable", "SeniorLongTermNotes",
]
DEBT_LT_CURRENT = [
    "LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent",
    "ConvertibleDebtCurrent", "SeniorNotesCurrent", "NotesPayableCurrent", "UnsecuredDebtCurrent",
    "SecuredDebtCurrent", "LoansPayableCurrent",
    "ConvertibleNotesPayableCurrent",
]
DEBT_SHORT = ["ShortTermBorrowings", "OtherShortTermBorrowings", "CommercialPaper"]
DEBT_LT_TOTAL = [
    "LongTermDebt",
    "SeniorNotes", "UnsecuredDebt", "SecuredDebt", "ConvertibleDebt", "NotesPayable", "LoansPayable",
    "DebtAndCapitalLeaseObligations",
    "ConvertibleNotesPayable",
]
# Tags that hold one slice of a filer's borrowing and are regularly the only one
# it tags: a drawn revolver, other borrowings, subordinated notes, a mortgage
# note. Reading them as total debt understates it badly - CubeSmart's $98M of
# notes and loans payable against some $3B of real debt, Ameriprise's revolver
# reported at zero while its senior notes sit in a tag we do not read. They are
# therefore left unmapped on purpose: they keep a company out of the ranking
# (and out of the debt-free rule below), and the discovery report lists them
# every month so the omission stays visible rather than becoming a wrong number.
DEBT_SLICE_TAGS = frozenset({
    "NotesAndLoansPayable", "SubordinatedDebt", "JuniorSubordinatedNotes", "OtherLongTermDebt",
    "OtherLongTermDebtNoncurrent", "LineOfCredit", "OtherBorrowings",
    "CommercialPaperAtCarryingValue", "LoansPayableToBankCurrent",
})
PARTIAL_DEBT_RATIO = 0.75
# The fallback tags that can hold one class of debt rather than all of it.
DEBT_COMPONENT_TAGS = frozenset({
    "UnsecuredLongTermDebt", "ConvertibleDebtNoncurrent", "SecuredLongTermDebt", "LongTermNotesPayable",
    "SeniorNotes", "UnsecuredDebt", "SecuredDebt", "ConvertibleDebt", "NotesPayable", "LoansPayable",
    "ConvertibleLongTermNotesPayable", "SeniorLongTermNotes", "ConvertibleNotesPayable",
})
ALL_DEBT = DEBT_COMBINED + DEBT_LT_NONCURRENT + DEBT_LT_CURRENT + DEBT_SHORT + DEBT_LT_TOTAL
EPS_DILUTED = ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted", "EarningsPerShareBasic"]

# Every tag some list above reads, and the name patterns used to spot a tag a
# company has moved to that none of them reads yet.
KNOWN_TAGS = frozenset(
    tag for name, value in list(globals().items())
    if name.isupper() and isinstance(value, list) for tag in value if isinstance(tag, str)
)
CANDIDATE_FAMILIES = {
    "debt": re.compile(r"(Debt|Notes|Borrowing|LoansPayable|CommercialPaper|LineOfCredit|Subordinated)"),
    "operating_income": re.compile(r"(OperatingIncome|InterestExpense)"),
    "cost_of_revenue": re.compile(r"^Costs?Of"),
    "capex": re.compile(r"^PaymentsToAcquire"),
    "operating_cash_flow": re.compile(r"^NetCashProvidedByUsedInOperating"),
}
CANDIDATE_NOISE = re.compile(
    r"(Receivable|Proceeds|Repayment|FairValue|Maturit|Unamortized|Discount|Premium|Securities|"
    r"Investment|Extinguishment|Covenant|Rate|Weighted|Number|Face|Principal|Increase|Decrease|"
    r"Gain|Loss|Allowance|Capacity|Guarantee|Instrument|Business|Intangible|Marketable|"
    r"Share|Compensation|InterestExpenseOperating|Deposits|"
    # cash flows, averages and footnote disclosures are not balance-sheet debt
    r"Payments|Average|Disclosure|Adjustments|Conversion|Issuance|Unused|Commitment|Remaining|Maximum)"
)
# A name that, if the company has ever filed it, means we cannot conclude the
# company is debt-free - even where it resolves to nothing today. The noise half
# is deliberately narrow: an unused facility or a preferred-share conversion is
# not a borrowing, but anything that could be one keeps debt unresolved.
DEBT_LIKE_EVER = re.compile(
    r"(Debt|Borrowing|NotesPayable|LoansPayable|LineOfCredit|CommercialPaper|Subordinated|SeniorNotes)"
)
DEBT_LIKE_NOISE = re.compile(
    # "liabilities other than long-term debt" is Intuitive Surgical saying it has
    # none; a trading-securities line is an asset, not a borrowing.
    r"(LiabilitiesOtherThan|TradingSecurities|"
    r"AvailableForSale|DebtSecurities|HeldToMaturity|Lease|StockIssued|Interest|"
    r"Proceeds|Repayment|Payments|Extinguishment|Conversion|Issuance|Adjustments|"
    r"Capacity|Unused|Commitment|Remaining|Maximum|Percentage|Ratio|Average|Disclosure|"
    r"Covenant|FairValue|Maturit|Unamortized|Discount|Premium|Weighted|Number|Face|Pledged)"
)

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
     "formula": "How far return on assets swings over five years: twelve-month earnings ending at the "
                "latest quarter and at each anniversary before it, each over total assets at the same date "
                "(fallback: the last five fiscal years). Where the five points trend upward, the standard "
                "deviation around that trend line, so steady improvement is not instability; otherwise the "
                "plain standard deviation, so a steady decline is. Lower is better, so the percentile is "
                "inverted."},
    # Moved from Growth in methodology 1.1. A rising gross-profits-to-assets ratio
    # is a quality signal - the business extracting more from what it owns - which
    # is where Asness et al.'s Quality-Minus-Junk places it. Not ROIC-conditioned.
    {"key": "delta_gpoa", "label": "Change in Gross Profitability", "short": "dGPOA", "factor": "quality",
     "higher_better": True, "unit": "pp",
     "formula": "Three-year change in gross profits over assets, from the trend line through every "
                "quarter (twelve-month gross profit over total assets at the same quarter end), in "
                "percentage points - improving efficiency, not growth. Fallback: the latest fiscal year "
                "minus the fiscal year three years earlier."},

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
    {"key": "rev_growth", "label": "Revenue Growth (3-yr trend)", "short": "Rev trend", "factor": "growth",
     "higher_better": True, "unit": "pct",
     "formula": "Annual growth rate of the trend line through the last three years of trailing-twelve-"
                "month revenue, one point per quarter - current to the latest 10-Q. Where the quarterly "
                "history cannot support it (under nine points, a base below $50M, or quarters that "
                "disagree with the restated annual report), the three-fiscal-year CAGR. ROIC-conditioned: "
                "at or below the hurdle the score is capped at 50 and faster growth scores lower - "
                "value-destroying expansion is never rewarded, and neither is shrinking. Capped by the "
                "latest year: if trailing-twelve-month revenue fell against the twelve months before, "
                "growth is at most that decline."},
    # Since methodology 1.6. Every other metric is a level or a multi-year change,
    # so a business whose profits were collapsing right now could still rank at the
    # top: Cal-Maine's quarterly operating income went from $636M to a $59M loss as
    # egg prices normalised while it ranked 20th. Across the operating universe the
    # direction of operating income over the last year ranked +0.24 with the
    # year's share-price move; the score, which could not see it, ranked -0.02.
    {"key": "op_inc_change", "label": "Operating Income Change (latest year)", "short": "OpInc chg",
     "factor": "growth", "higher_better": True, "unit": "pp",
     "not_for_segments": ["pre_revenue"], "coverage_optional": True,
     "formula": "Four times the median of the last four quarters' change in operating income against the "
                "same quarter a year earlier, over average total assets - the latest year's direction of "
                "profit, one bad or one-off quarter unable to set it alone. Each quarter and its year-ago "
                "comparative come from the latest filing, so restatements cannot mix bases. ROIC-"
                "conditioned like all Growth metrics. Not applied to pre-revenue companies."},

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

    A tag the filer has abandoned resolves to None in `FactSet.instant`, so a
    combined tag last used in 2015 falls through to today's components instead
    of standing in for today's debt.
    """
    combined = fs.instant(DEBT_COMBINED, on_or_before)
    noncurrent = fs.instant(DEBT_LT_NONCURRENT, on_or_before)
    lt_total = fs.instant(DEBT_LT_TOTAL, on_or_before)
    lt_current = _val(fs.instant(DEBT_LT_CURRENT, on_or_before))
    short = _val(fs.instant(DEBT_SHORT, on_or_before))
    # Every path that includes long-term debt, as (date, priority, value, name).
    # The most recent balance sheet wins and priority only breaks ties: a
    # combined-debt figure from the 10-K must not stand in for the components in
    # a newer 10-Q (Lilly, UnitedHealth, Verizon read their December debt at the
    # end of June). A current-portion-only path is never "complete", so it stays
    # the last resort however recent - it would drop the long-term debt.
    complete = []
    if _val(combined) is not None:
        complete.append((combined["end"], 0, combined["val"], "combined-tag", combined["concept"]))
    if _val(noncurrent) is not None:
        complete.append((noncurrent["end"], 1, _sum_present(noncurrent["val"], lt_current, short),
                         "noncurrent+current+short", noncurrent["concept"]))
    if _val(lt_total) is not None:
        complete.append((lt_total["end"], 2, _sum_present(lt_total["val"], short), "longtermdebt+short",
                         lt_total["concept"]))
    if complete:
        # Newest first. A total tag always wins - a smaller newer total is a
        # repayment (CSW Industrials went from $166M to nothing in 2024). A
        # component tag far below an older total is a part standing in for the
        # whole: TeraWulf's June 2026 convertible notes ($1.1B) against its March
        # total ($3.1B), so the older total is kept.
        ordered = sorted(complete, key=lambda c: (c[0], -c[1]), reverse=True)
        for i, (_, _, value, how, concept) in enumerate(ordered):
            if concept in DEBT_COMPONENT_TAGS and any(
                    value < PARTIAL_DEBT_RATIO * older[2] for older in ordered[i + 1:]):
                continue
            return value, how
    partial = _sum_present(lt_current, short)
    if partial is not None:
        return partial, "current+short-only"
    # No debt tag is current. If the last one the company ever reported said
    # zero, it has simply stopped tagging a line it no longer has (Palantir,
    # Arista, Copart). A non-zero last value proves nothing about today, so that
    # stays unresolved rather than being guessed.
    limit = (on_or_before or fs.as_of).isoformat()
    last = []
    for concept in ALL_DEBT:
        rows = [f for f in fs.instants([concept]) if f["end"] <= limit and f["val"] is not None]
        if rows:
            last.append(rows[-1])
    if last:
        newest = max(f["end"] for f in last)
        if all(f["val"] == 0 for f in last if f["end"] == newest):
            return 0.0, "last-reported-zero"
    # Never borrowed at all. A company with a current, complete balance sheet
    # that has never tagged a borrowing anywhere in its filing history is
    # equity-funded, not silent: clinical-stage biotechs, Intuitive Surgical,
    # Reddit, Duolingo. Absent debt is zero for them (1.8). Guarded by the
    # whole history, so a filer whose debt sits in a tag we do not map - or who
    # repaid one we do - stays unresolved rather than being flattered.
    if (not last and fs.reference_end is not None
            and _val(fs.instant(EQUITY, on_or_before)) is not None
            and _val(fs.instant(ASSETS, on_or_before)) is not None
            and not any(fs.instants([concept]) for concept in DEBT_SLICE_TAGS)
            and not fs.ever_reported(DEBT_LIKE_EVER, noise=DEBT_LIKE_NOISE)):
        return 0.0, "no debt tag ever filed"
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
    # Many large companies present no operating-income line at all - Johnson &
    # Johnson, Lilly, Merck, Pfizer, TJX - and go straight to pre-tax income.
    # Pre-tax income plus interest expense is the textbook EBIT. Interest is
    # often tagged only in the annual report, so it may come from the last
    # fiscal year while pre-tax income is trailing; both must still be current.
    pretax = fs.ttm(PRETAX_INCOME)
    interest = fs.ttm(INTEREST_EXPENSE)
    if pretax and interest and None not in (pretax["val"], interest["val"]):
        return pretax["val"] + interest["val"], pretax, "derived: pretax income + interest expense"
    return None, revenue, "unresolved"


# Items a filer tags as one-off, in both directions. Only balances a company
# states itself: nothing is estimated, and nothing untagged is guessed at.
# Within each family the largest value in the window is taken rather than the
# sum, because the tags nest - AssetImpairmentCharges can already contain the
# goodwill line - and double counting would be worse than under-adjusting.
ONE_OFF_GAINS = [
    "GainLossOnSaleOfBusiness", "GainLossOnDispositionOfBusiness",
    "GainLossOnDispositionOfAssets", "GainLossOnDispositionOfAssets1",
    "GainLossOnSaleOfOtherAssets", "GainLossOnSaleOfPropertyPlantEquipment",
    "GainLossRelatedToLitigationSettlement", "DeconsolidationGainOrLossAmount",
    "BusinessCombinationBargainPurchaseGainRecognizedAmount",
]
ONE_OFF_CHARGES = [
    "GoodwillImpairmentLoss", "AssetImpairmentCharges", "TangibleAssetImpairmentCharges",
    "ImpairmentOfIntangibleAssetsExcludingGoodwill", "ImpairmentOfIntangibleAssetsFinitelived",
    "ImpairmentOfIntangibleAssetsIndefinitelivedExcludingGoodwill",
    "ImpairmentOfLongLivedAssetsHeldAndUsed", "RestructuringCharges",
    "RestructuringSettlementAndImpairmentProvisions", "RestructuringCostsAndAssetImpairmentCharges",
]
ONE_OFF_MATERIAL = 0.25      # of trailing EBIT, or of revenue where EBIT is near zero
ONE_OFF_CONFIRM = 0.5        # how much of the item the operating line must show
ONE_OFF_WINDOW = 370         # days: the item must fall inside the trailing year


def _one_off_amount(fs: FactSet, concepts: list[str], ref) -> tuple[float, str | None, str | None]:
    """The largest positive amount tagged under any of `concepts` whose period
    ends inside the trailing year."""
    best = (0.0, None, None)
    for concept in concepts:
        for fact in fs.durations([concept]):
            val, end = fact.get("val"), fact.get("end")
            if not val or val <= 0 or not end:
                continue
            if 0 <= (ref - parse_iso(end)).days <= ONE_OFF_WINDOW and val > best[0]:
                best = (val, concept, end)
    return best


def _shows_in_operating_income(fs: FactSet, amount: float, sign: int) -> bool:
    """Evidence the item passed through operating income rather than below it,
    or than being a footnote disclosure: some quarter of the trailing year moved
    against the same quarter a year earlier by at least half of it, in the right
    direction. A gain booked below the operating line is already outside EBIT and
    must not be deducted twice; an expected-cost disclosure never moved anything.
    """
    quarters = quarterly_series(fs, OPERATING_INCOME)
    if len(quarters) < 8:
        return False
    for end, val in quarters[-4:]:
        prior = [v for e, v in quarters if 350 <= (end - e).days <= 380]
        if not prior:
            continue
        move = (val - prior[-1]) * sign
        if move >= ONE_OFF_CONFIRM * amount and (sign < 0 or val >= amount):
            return True
    return False


def normalised_ebit(fs: FactSet, ebit: float | None) -> tuple[float | None, str | None]:
    """EBIT with the one-off items the company tagged taken back out, in both
    directions.

    A year holding a large disposal gain and a larger write-down is two
    distortions, not one: strip only the gain and a profitable business reads as
    a loss-maker. Both are removed together or neither is, and the net
    adjustment must be material and visible in the operating line before it is
    applied. Returns (ebit, note) with note None when nothing was adjusted.
    """
    ref = fs.reference_end
    if ebit is None or ref is None:
        return ebit, None
    gain, gain_tag, gain_end = _one_off_amount(fs, ONE_OFF_GAINS, ref)
    charge, charge_tag, charge_end = _one_off_amount(fs, ONE_OFF_CHARGES, ref)
    if gain and not _shows_in_operating_income(fs, gain, +1):
        gain, gain_tag = 0.0, None
    if charge and not _shows_in_operating_income(fs, charge, -1):
        charge, charge_tag = 0.0, None
    net = charge - gain
    if not net:
        return ebit, None
    # Materiality against EBIT, or against revenue where EBIT is near zero - a
    # company at break-even has no meaningful EBIT to take a percentage of.
    revenue = _val(fs.ttm(REVENUE))
    base = max(abs(ebit), 0.02 * (revenue or 0.0))
    if base <= 0 or abs(net) < ONE_OFF_MATERIAL * base:
        return ebit, None
    parts = []
    if gain_tag:
        parts.append(f"a tagged one-off gain of {gain / 1e6:,.0f}M ({gain_tag}, {gain_end})")
    if charge_tag:
        parts.append(f"a tagged one-off charge of {charge / 1e6:,.0f}M ({charge_tag}, {charge_end})")
    return ebit + net, ("normalised for " + " and ".join(parts)
                        + f": {ebit / 1e6:,.0f}M -> {(ebit + net) / 1e6:,.0f}M")


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


TREND_YEARS = 3
TREND_MIN_POINTS = 9            # quarterly TTM points inside the window
TREND_MIN_BASE = 50_000_000     # below this, growth off a near-zero base is noise
RESTATEMENT_TOLERANCE = 0.05    # quarters vs the restated annual report


def quarterly_series(fs: FactSet, concepts: list[str]) -> list[tuple]:
    """(quarter end, 3-month value), reported quarters preferred over those
    derived from year-to-date figures. A 3-month fact carrying the full-year
    figure for the same date - L3Harris and NiSource tag their annual revenue
    that way in the 10-K - is a tagging error and is dropped."""
    facts = [f for f in fs.durations(concepts) if f["val"] is not None]
    annual: dict[str, list[float]] = {}
    for f in facts:
        if 330 <= (parse_iso(f["end"]) - parse_iso(f["start"])).days <= 400:
            annual.setdefault(f["end"], []).append(f["val"])
    best: dict[str, tuple] = {}
    for f in facts + FactSet._synthesize_tails(facts):
        if not 80 <= (parse_iso(f["end"]) - parse_iso(f["start"])).days <= 100:
            continue
        if not f.get("synthetic") and any(abs(f["val"] - a) <= 0.01 * abs(a) for a in annual.get(f["end"], [])):
            continue
        rank = (not f.get("synthetic"), f["filed"])
        if f["end"] not in best or rank > best[f["end"]][0]:
            best[f["end"]] = (rank, f)
    return sorted((parse_iso(end), entry[1]["val"]) for end, entry in best.items())


def quarterly_revenue(fs: FactSet) -> list[tuple]:
    return quarterly_series(fs, REVENUE)


def ttm_points(q: list[tuple]) -> list[tuple]:
    """(quarter end, trailing-twelve-month sum) wherever four consecutive quarters exist."""
    return [(q[i][0], sum(v for _, v in q[i - 3:i + 1]))
            for i in range(3, len(q)) if (q[i][0] - q[i - 3][0]).days <= 300]


def quarters_match_annual(fs: FactSet, q: list[tuple], concepts: list[str], since) -> bool:
    """Quarterly comparatives are not restated after a spin-off or disposal; the
    annual report restates three years. Every fiscal year from `since` must agree
    with the sum of its quarters, or the quarters describe a different company
    (GE before and after GE Vernova)."""
    for fy in fs.annual_series(concepts, 5):
        fy_end = parse_iso(fy["end"])
        if fy_end < since or not fy["val"]:
            continue
        inside = [v for e, v in q if fy_end - timedelta(days=355) < e <= fy_end + timedelta(days=10)]
        if len(inside) == 4 and abs(sum(inside) - fy["val"]) > RESTATEMENT_TOLERANCE * abs(fy["val"]):
            return False
    return True


def _slope_per_year(points: list[tuple], transform=lambda v: v) -> float:
    xs = [(e - points[0][0]).days / 365.25 for e, _ in points]
    ys = [transform(v) for _, v in points]
    mx, my = mean(xs), mean(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)


def _assets_at(fs: FactSet, when) -> float | None:
    fact = fs.instant_near(ASSETS, when.isoformat(), tolerance_days=10)
    return fact["val"] if fact and fact["val"] else None


def revenue_trend(fs: FactSet) -> tuple[float | None, str | None]:
    """Annual growth rate of the least-squares trend of log TTM revenue over
    the last three years, one point per quarter. Returns (value, None) or
    (None, why it could not be computed)."""
    ref = fs.reference_end
    q = quarterly_revenue(fs)
    ttm = ttm_points(q)
    if not ttm or ref is None or (ref - ttm[-1][0]).days > 120:
        return None, "no current quarterly revenue series"
    end = ttm[-1][0]
    points = [(e, v) for e, v in ttm if (end - e).days <= 365 * TREND_YEARS + 30]
    if len(points) < TREND_MIN_POINTS:
        return None, f"only {len(points)} quarterly points"
    if any(v <= 0 for _, v in points):
        return None, "non-positive revenue in the window"
    if points[0][1] < TREND_MIN_BASE:
        return None, "revenue base under $50M"
    # every fiscal year whose quarters feed the window, including the three
    # quarters before it that the first trailing point reaches back to
    if not quarters_match_annual(fs, q, REVENUE, points[0][0] - timedelta(days=280)):
        return None, "quarters disagree with the restated annual report"
    return math.exp(_slope_per_year(points, math.log)) - 1, None


def revenue_latest_year_change(fs: FactSet) -> float | None:
    """Trailing-twelve-month revenue against the twelve months before, from the
    same quarterly series as the trend; None where there is no current series."""
    ttm = ttm_points(quarterly_revenue(fs))
    if len(ttm) < 5 or fs.reference_end is None or (fs.reference_end - ttm[-1][0]).days > 120:
        return None
    end, now = ttm[-1]
    prior = [v for e, v in ttm if 350 <= (end - e).days <= 380]
    return (now - prior[-1]) / prior[-1] if prior and prior[-1] > 0 else None


def operating_income_change(fs: FactSet) -> tuple[float | None, str]:
    """The latest year's direction of operating income: four times the median
    of the last four quarters' change against the same quarter a year earlier,
    over average total assets. The median keeps one quarter - an impairment, a
    settlement - from setting it; scaling by assets keeps a near-zero base from
    turning a small change into +900%."""
    ref = fs.reference_end
    q = quarterly_series(fs, OPERATING_INCOME)
    if not q or ref is None or (ref - q[-1][0]).days > 120:
        return None, "no current quarterly operating income"
    changes = []
    for end, value in q[-4:]:
        prior = [v for e, v in q if 355 <= (end - e).days <= 375]
        if not prior:
            return None, f"no year-ago comparative for the quarter ending {end}"
        changes.append(value - prior[-1])
    if len(changes) < 4:
        return None, "fewer than four quarters of operating income"
    since = q[-8][0] if len(q) >= 8 else q[0][0]
    if not quarters_match_annual(fs, q, OPERATING_INCOME, since):
        return None, "quarters disagree with the restated annual report"
    now, year_ago = _assets_at(fs, q[-1][0]), _assets_at(fs, q[-1][0] - timedelta(days=365))
    if not now or not year_ago or now + year_ago <= 0:
        return None, "total assets unavailable at the quarter ends"
    middle = sorted(changes)[1:3]          # the median of four
    return 4 * (middle[0] + middle[1]) / 2 / ((now + year_ago) / 2), ""


def gpoa_trend(fs: FactSet) -> tuple[float | None, str | None]:
    """Change in gross profitability over three years, current to the latest
    quarter: the least-squares trend of TTM gross profit over total assets at
    the same quarter end, one point per quarter, expressed as the three-year
    change. Numerator and denominator always share a date, so the calendar
    artifact that once made Alphabet's decline read -13.4pp cannot return."""
    ref = fs.reference_end
    revenue_q = quarterly_revenue(fs)
    cogs_q = dict(quarterly_series(fs, COGS))
    gross = [(e, v - cogs_q[e]) for e, v in revenue_q if e in cogs_q]
    via_cogs = len(gross) >= TREND_MIN_POINTS + 3
    if not via_cogs:
        gross = quarterly_series(fs, GROSS_PROFIT)
    ttm = ttm_points(gross)
    if not ttm or ref is None or (ref - ttm[-1][0]).days > 120:
        return None, "no current quarterly gross profit"
    end = ttm[-1][0]
    points = []
    for e, gp in ttm:
        if (end - e).days <= 365 * TREND_YEARS + 30:
            assets = _assets_at(fs, e)
            if assets and assets > 0:
                points.append((e, gp / assets))
    if len(points) < TREND_MIN_POINTS:
        return None, f"only {len(points)} quarterly points"
    # A quarter whose gross profit is several times its assets is a tagging
    # error (Calumet and Smurfit Westrock each have a near-zero assets figure).
    if any(abs(v) > 3 for _, v in points):
        return None, "implausible quarterly figures"
    since = points[0][0] - timedelta(days=280)
    if not quarters_match_annual(fs, revenue_q, REVENUE, since) or (
            via_cogs and not quarters_match_annual(fs, sorted(cogs_q.items()), COGS, since)):
        return None, "quarters disagree with the restated annual report"
    # The twelve-month gross profit at each fiscal year end must equal the annual
    # report's. Asbury's early quarters tag a small part of cost of sales, so its
    # quarterly "gross profit" was nearly its revenue while the 10-K said 17%.
    ttm_at = dict(ttm)
    revenues = {f["end"]: f["val"] for f in fs.annual_series(REVENUE, 5)}
    annual_cogs = {f["end"]: f["val"] for f in fs.annual_series(COGS, 5)}
    annual_gp = {f["end"]: f["val"] for f in fs.annual_series(GROSS_PROFIT, 5)}
    for fy_end_iso, revenue in revenues.items():
        fy_end = parse_iso(fy_end_iso)
        if fy_end < since or not revenue:
            continue
        expected = (revenue - annual_cogs[fy_end_iso]) if via_cogs and fy_end_iso in annual_cogs \
            else annual_gp.get(fy_end_iso)
        quarterly = next((v for e, v in ttm_at.items() if abs((e - fy_end).days) <= 10), None)
        if expected is not None and quarterly is not None and abs(quarterly - expected) > RESTATEMENT_TOLERANCE * abs(revenue):
            return None, "quarters disagree with the restated annual report"
    return _slope_per_year(points) * TREND_YEARS, None


def one_off_quarters(fs: FactSet) -> dict:
    """Per quarter end, the net one-off amount the company tagged for it -
    charges positive, gains negative - across its whole reported history.

    Variability looks back five years, so an impairment three years ago matters
    as much as one last quarter. Within a family the largest amount for the
    quarter is taken, never the sum, because the tags nest.
    """
    net: dict = {}
    for concepts, sign in ((ONE_OFF_CHARGES, 1.0), (ONE_OFF_GAINS, -1.0)):
        family: dict = {}
        for concept in concepts:
            for end, val in quarterly_series(fs, [concept]):
                if val and val > 0 and val > family.get(end, 0.0):
                    family[end] = val
        for end, val in family.items():
            net[end] = net.get(end, 0.0) + sign * val
    return net


ONE_OFF_RECURRENCE = 1 / 3     # of the periods measured: beyond this it is how the business runs
ONE_OFF_VS_TYPICAL = 1.0       # of the period earnings a company typically reports


def _qualifying_periods(periods: list, items: dict, tax_rate: float) -> dict:
    """Which of the measured periods hold an item big enough to distort them.

    Three things have to hold. The item is worth at least a quarter of that
    period's earnings, and at least as much as the company's typical period
    earnings - a $50M charge against a $400M quarter is an ordinary cost of
    doing business, a $6.7B one is an event. And the earnings line has to move
    with it, so a footnote disclosure changes nothing.
    """
    if not periods:
        return {}
    typical = median_abs([val for _, val in periods]) or 0.0
    by_end = dict(periods)
    out = {}
    for end, val in periods:
        after_tax = (items.get(end) or 0.0) * (1 - tax_rate)
        if not after_tax or abs(after_tax) < max(ONE_OFF_MATERIAL * abs(val),
                                                 ONE_OFF_VS_TYPICAL * typical):
            continue
        prior = next((v for e, v in by_end.items() if 350 <= (end - e).days <= 380), None)
        if prior is None or (prior - val) * (1 if after_tax > 0 else -1) < 0.5 * abs(after_tax):
            continue
        out[end] = after_tax
    # Recurring by definition: a filer tagging one in most periods is not having
    # events, it is describing how it operates, and removing them would flatter
    # it against a company that restructured once.
    if len(out) > max(1, len(periods) * ONE_OFF_RECURRENCE):
        return {}
    return out


def median_abs(values: list[float]) -> float:
    ordered = sorted(abs(v) for v in values if v is not None)
    if not ordered:
        return 0.0
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def normalised_quarterly_earnings(fs: FactSet, tax_rate: float) -> tuple[list[tuple], int]:
    """Quarterly net income with tagged one-off items taken out, after tax.

    A write-down is not instability: Molson Coors' single impairment quarter
    made a steady brewer read as erratic as a memory-chip cycle. The item is
    removed only where the earnings line actually shows it - the quarter differs
    from the same quarter a year earlier by at least half the after-tax amount,
    in the direction of the item - so a footnote disclosure changes nothing.
    """
    quarters = quarterly_series(fs, NET_INCOME)
    items = one_off_quarters(fs)
    if not items or not quarters:
        return quarters, 0
    # Only the periods the metric reads: five twelve-month windows, so the last
    # twenty-one quarters. An impairment in 2014 is not this company's story.
    window = quarters[-21:]
    adjustments = _qualifying_periods(window, items, tax_rate)
    if not adjustments:
        return quarters, 0
    return [(end, val + adjustments.get(end, 0.0)) for end, val in quarters], len(adjustments)


def normalised_annual_earnings(fs: FactSet, tax_rate: float) -> tuple[list[dict], int]:
    """The five fiscal years of net income, with tagged one-off items taken out
    after tax. The fiscal-year fallback carries the companies whose quarterly
    history has a gap - Molson Coors and Kroger among them - and a $3.6B
    write-down distorts a fiscal year exactly as it distorts a quarter."""
    years = fs.annual_series(NET_INCOME, 5)
    items: dict = {}
    for concepts, sign in ((ONE_OFF_CHARGES, 1.0), (ONE_OFF_GAINS, -1.0)):
        family: dict = {}
        for concept in concepts:
            for row in fs.annual_series([concept], 6):
                val = row.get("val")
                if val and val > 0 and val > family.get(row["end"], 0.0):
                    family[row["end"]] = val
        for end, val in family.items():
            items[end] = items.get(end, 0.0) + sign * val
    if not items:
        return years, 0
    dated = [(parse_iso(row["end"]), row["val"]) for row in years if row.get("val") is not None]
    adjustments = _qualifying_periods(dated, {parse_iso(e): v for e, v in items.items()}, tax_rate)
    if not adjustments:
        return years, 0
    out = []
    for row in years:
        shift = adjustments.get(parse_iso(row["end"])) if row.get("val") is not None else None
        out.append({**row, "val": row["val"] + shift} if shift else row)
    return out, len(adjustments)


def roa_variability(fs: FactSet, tax_rate: float = 0.0) -> tuple[float | None, str | None, int]:
    """Standard deviation of return on assets over five years, current to the
    latest quarter: five non-overlapping twelve-month windows ending at the
    latest quarter and at each anniversary before it, each divided by total
    assets at its own end. Fiscal years alone ended up to a year before the
    scoring date for 80% of companies."""
    ref = fs.reference_end
    quarters, normalised = normalised_quarterly_earnings(fs, tax_rate)
    ttm = ttm_points(quarters)
    if not ttm or ref is None or (ref - ttm[-1][0]).days > 120:
        return None, "no current quarterly earnings", 0
    end = ttm[-1][0]
    roas = []
    for k in range(5):
        target = end - timedelta(days=round(365.25 * k))
        near = [(abs((e - target).days), e, v) for e, v in ttm if abs((e - target).days) <= 20]
        if not near:
            return None, f"no twelve-month earnings ending near {target}", 0
        _, e, v = min(near)
        assets = _assets_at(fs, e)
        if not assets or assets <= 0:
            return None, f"no balance sheet at {e}", 0
        roas.append(v / assets)
    return variability_around_rising_trend(roas[::-1]), None, normalised


def variability_around_rising_trend(roas: list[float]) -> float:
    """How far return on assets swings, oldest point first.

    Around the mean, steady improvement read as instability: Palantir's ROA
    climbing from -16% to 26% scored as erratic as a memory-chip cycle. Where the
    trend rises, only the swings around the trend line count (residual standard
    deviation, three degrees of freedom), so steady growth is stable. Where it
    falls, the decline is itself the instability and the plain standard
    deviation stands - a steady slide from 23% to 5% is not a stable business.
    """
    xs = range(len(roas))
    mx, my = mean(xs), mean(roas)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, roas)) / sum((x - mx) ** 2 for x in xs)
    if slope <= 0:
        return stdev(roas)
    residuals = [y - (my + slope * (x - mx)) for x, y in zip(xs, roas)]
    return math.sqrt(sum(r * r for r in residuals) / (len(roas) - 2))


MAX_MARGIN_SWING = 0.5


def _annual_revenue(fs: FactSet, years_back: int) -> float:
    revenues = fs.annual_series(REVENUE, 6)
    return revenues[years_back]["val"] or 0.0 if len(revenues) > years_back else 0.0


def _annual_gross_margin(fs: FactSet, years_back: int) -> float | None:
    """Gross margin in the fiscal year `years_back` years ago, cost and revenue
    matched on period end - the comparability check behind the dGPOA fallback."""
    revenues = fs.annual_series(REVENUE, 6)
    if len(revenues) <= years_back or not revenues[years_back]["val"]:
        return None
    target = revenues[years_back]
    cogs = next((f for f in fs.annual_series(COGS, 6)
                 if abs((parse_iso(f["end"]) - parse_iso(target["end"])).days) <= 20), None)
    if cogs is None:
        return None
    return (target["val"] - cogs["val"]) / target["val"]


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
    ebit, one_off_note = normalised_ebit(fs, ebit)
    if one_off_note:
        ebit_path += "; " + one_off_note
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

    # Current to the latest quarter where the quarterly history supports it;
    # otherwise the five completed fiscal years, as before methodology 1.4.
    variability, variability_reason, normalised_quarters = roa_variability(fs, tax_rate)
    if variability is not None:
        values["earn_var"] = variability
        provenance["earn_var_source"] = "5 twelve-month windows to the latest quarter" + (
            f", with {normalised_quarters} quarter{'s' if normalised_quarters > 1 else ''} "
            "normalised for tagged one-off items (after tax)" if normalised_quarters else "")
    else:
        net_income_years, normalised_years = normalised_annual_earnings(fs, tax_rate)
        roas = []
        for row in net_income_years:
            a = fs.instant_near(ASSETS, row["end"])
            r = safe_div(row["val"], _val(a)) if a else None
            if r is not None:
                roas.append(r)
        if len(roas) >= 5:
            values["earn_var"] = variability_around_rising_trend(roas[::-1])
            provenance["earn_var_source"] = f"5 fiscal years ({variability_reason})" + (
                f", with {normalised_years} year{'s' if normalised_years > 1 else ''} "
                "normalised for tagged one-off items (after tax)" if normalised_years else "")
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
    #
    # Since methodology 1.4 the primary measure is the quarterly trend, whose
    # every point pairs a twelve-month gross profit with the balance sheet at
    # the same date - like-for-like, and current. The fiscal-year comparison is
    # the fallback. On fiscal years alone Micron read -3.0pp (peak FY2022 to
    # FY2025) while its gross margin rose from 56% to 85% over three quarters.
    trend, trend_reason = gpoa_trend(fs)
    if trend is not None:
        values["delta_gpoa"] = trend
        provenance["delta_gpoa_source"] = "3-year quarterly trend"
    else:
        gpoa_now = _annual_gpoa(fs, 0)
        gpoa_then = _annual_gpoa(fs, 3)
        margins = (_annual_gross_margin(fs, 0), _annual_gross_margin(fs, 3))
        if gpoa_now is None or gpoa_then is None:
            missing["delta_gpoa"] = "fewer than 4 fiscal years of revenue/COGS/assets"
        elif None not in margins and abs(margins[0] - margins[1]) > MAX_MARGIN_SWING \
                and _annual_revenue(fs, 0) >= TREND_MIN_BASE and _annual_revenue(fs, 3) >= TREND_MIN_BASE:
            # A gross margin that moves 50+ points in three years is a change of
            # cost tag, not of business: Asbury's 2022 cost of sales is tagged as a
            # $0.9B component (a "94% margin" car dealer), its 2025 as $14.9B.
            missing["delta_gpoa"] = (f"cost of revenue not comparable across fiscal years "
                                     f"(gross margin {margins[1]:.0%} then {margins[0]:.0%})")
        else:
            values["delta_gpoa"] = gpoa_now - gpoa_then
            provenance["delta_gpoa_source"] = f"fiscal years ({trend_reason})"

    # Growth is the trend of trailing revenue, current to the latest quarter.
    # Completed fiscal years alone lag by up to a year: scored on 31 August 2026,
    # Micron's latest 10-K covered the year to August 2025, so its three-year
    # CAGR (peak FY2022 to FY2025) read 6.7% while trailing revenue had grown
    # from $37B to $90B. The annual CAGR remains the fallback.
    trend, trend_reason = revenue_trend(fs)
    if trend is not None:
        values["rev_growth"] = trend
        provenance["growth_source"] = "3-year quarterly trend"
    else:
        provenance["growth_source"] = f"3-fiscal-year CAGR ({trend_reason})"
        revenues = fs.annual_series(REVENUE, 4)
        if len(revenues) >= 4 and revenues[3]["val"] and revenues[3]["val"] > 0 and revenues[0]["val"] is not None:
            ratio = revenues[0]["val"] / revenues[3]["val"]
            values["rev_growth"] = (ratio ** (1 / 3)) - 1 if ratio > 0 else None
            if values["rev_growth"] is None:
                missing["rev_growth"] = "revenue turned negative"
        else:
            missing["rev_growth"] = f"no quarterly trend ({trend_reason}) and fewer than 4 fiscal years of revenue"
            provenance["growth_source"] = f"unresolved ({trend_reason})"

    # A three-year trend can read a collapse as growth: Cal-Maine's revenue peaked
    # with egg prices and fell 32% in the latest year, yet the line through three
    # years still rose 13%. When the latest year shrank, growth is the average of the
    # trend and that year, so a collapse still scores near the bottom while a 1%
    # dip costs little (1.7; the 1.6 hard cap let a 1% dip erase a 17% trend).
    latest_year = revenue_latest_year_change(fs)
    if values["rev_growth"] is not None and latest_year is not None and latest_year < values["rev_growth"] \
            and latest_year < 0:
        trend_growth = values["rev_growth"]
        values["rev_growth"] = (trend_growth + latest_year) / 2
        provenance["growth_source"] += (
            f"; revenue fell {latest_year:+.1%} in the latest year, so growth is the average of"
            f" that and the trend ({trend_growth:+.1%} -> {values['rev_growth']:+.1%})"
        )

    change, change_reason = operating_income_change(fs)
    if change is not None:
        values["op_inc_change"] = change
    else:
        missing["op_inc_change"] = change_reason

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

    # Name every figure rejected as stale, so a metric missing because the filer
    # abandoned a tag can be told apart from one it never reported.
    provenance["stale_inputs"] = fs.stale_inputs
    provenance["latest_balance_sheet"] = fs.reference_end.isoformat() if fs.reference_end else None
    # For each input that did not resolve, the tags this company reports today
    # that no list here reads - the candidates the monthly drift report puts in
    # front of a person, so a tag switch costs a one-line change, not a search.
    unresolved_families = [
        family for family, value in (
            ("debt", debt), ("operating_income", ebit), ("cost_of_revenue", gross_profit),
            ("capex", capex), ("operating_cash_flow", ocf),
        ) if value is None
    ]
    provenance["unmapped_candidates"] = {
        family: tags for family in unresolved_families
        if (tags := fs.current_tags(CANDIDATE_FAMILIES[family], exclude=KNOWN_TAGS, noise=CANDIDATE_NOISE))
    }
    if fs.stale_inputs:
        notes.append(
            "Ignored figures from tags this company no longer reports under: "
            + ", ".join(f"{s['concept']} (last reported {s['last_reported']})" for s in fs.stale_inputs)
            + "."
        )

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
