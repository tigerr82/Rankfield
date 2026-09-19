"""Point-in-time view over one company's XBRL facts.

Everything here obeys one rule: when scoring as of date D, only facts with
`filed <= D` exist. Restatements filed after D are invisible, which is what
makes a past score reproducible.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from .util import parse_iso

ANNUAL_MIN, ANNUAL_MAX = 330, 400

# Only financial reports may supply a figure.
#
# Since 2023 the SEC's pay-versus-performance rule puts several years of company
# net income into proxy statements (DEF 14A), XBRL-tagged - and often at the
# wrong scale. G-III's FY2024 net income, $176,168,000 in its 10-K, arrives from
# its 2026 proxy as 174,740. Because the most recently filed value for a period
# wins, those proxies silently replaced audited 10-K figures for 26 scored
# companies (Medtronic, FedEx, Arista among them): net income collapsed ~1000x,
# return on assets flattened to zero, and their earnings looked perfectly stable.
FINANCIAL_REPORT_FORMS = frozenset({
    "10-K", "10-K/A", "10-KT", "10-KT/A",
    "10-Q", "10-Q/A", "10-QT", "10-QT/A",
    "20-F", "20-F/A", "40-F", "40-F/A",
})
QUARTER_MIN, QUARTER_MAX = 80, 100

# A figure older than this, counted back from the company's latest balance sheet,
# is treated as not reported.
#
# EDGAR keeps every fact ever filed, including tags a company stopped using years
# ago, and a lookup by tag priority used to return that tag's last value however
# old it was. Microsoft's total debt resolved to $31.8B from a 2015 10-Q - a tag
# it has not used since - instead of $40.3B from its 2026 10-K; Johnson & Johnson's
# operating income dated from March 2015; Deere's gross profit was 2026 revenue
# less 2018 cost of goods sold. 557 of 1,368 scored companies carried at least one
# such figure. 300 days admits the oldest legitimate input - a figure tagged only
# in the annual report, read three quarters into the next fiscal year - and
# nothing a year stale.
MAX_INPUT_AGE_DAYS = 300
# A trailing figure stitched from quarters proves the company tags that line
# quarterly, so it must reach the latest quarter (one quarter of slack for 52/53
# week calendars and a late tag). H.B. Fuller's operating income stopped three
# quarters before its latest 10-Q; 300 days would have let it through.
MAX_QUARTERLY_LAG_DAYS = 120
# The latest balance sheet is the latest date at least this many balance-sheet
# tags share - not the date of one named tag. Cinemark stopped tagging
# consolidated Assets in 2022 while filing full balance sheets since, which
# anchored every age check to 2022.
BALANCE_SHEET_MIN_TAGS = 5


class FactSet:
    def __init__(self, facts_json: dict, as_of: date, max_input_age_days: int = MAX_INPUT_AGE_DAYS):
        self.as_of = as_of
        self.max_input_age_days = max_input_age_days
        self.entity = facts_json.get("entityName")
        self._facts = facts_json.get("facts") or {}
        self._cache: dict[tuple, list] = {}
        self._stale: dict[str, str] = {}
        self.forms: set[str] = set()
        self._quarters_filed = 0
        self._scan_forms()

    # -------------------------------------------------------------- setup

    def _scan_forms(self) -> None:
        """Which filing types this company uses, and how many distinct periodic
        reports it has on record - used by the structural-hygiene filters
        (20-F filers, and companies with too little history for growth metrics).
        """
        seen: set[tuple[str, str]] = set()
        gaap = self._facts.get("us-gaap") or {}
        probe = gaap.get("Assets") or gaap.get("Liabilities") or gaap.get("StockholdersEquity") or {}
        for unit_facts in (probe.get("units") or {}).values():
            for f in unit_facts:
                if f.get("filed") and parse_iso(f["filed"]) <= self.as_of:
                    form = f.get("form") or ""
                    self.forms.add(form)
                    if form in ("10-K", "10-Q", "20-F", "40-F"):
                        seen.add((form, f.get("accn", "")))
        self._quarters_filed = len(seen)

    @property
    def quarters_filed(self) -> int:
        return self._quarters_filed

    @property
    def files_domestic_forms(self) -> bool:
        """10-K/10-Q filers are period-on-period comparable; 20-F/40-F filers
        report on a different cadence and are not."""
        return bool({"10-K", "10-Q"} & self.forms)

    # ---------------------------------------------------------- freshness

    @property
    def reference_end(self) -> date | None:
        """Period end of the latest balance sheet on file at D: the date every
        current input's age is measured from.

        A balance-sheet date must predate the filing that reports it; that
        discards typos such as H.B. Fuller's deferred-tax facts dated 2105.
        """
        key = ("reference_end",)
        if key not in self._cache:
            limit = self.as_of.isoformat()
            tags_per_end: dict[str, set[str]] = defaultdict(set)
            for concept, node in (self._facts.get("us-gaap") or {}).items():
                for rows in (node.get("units") or {}).values():
                    for f in rows:
                        end, filed = f.get("end"), f.get("filed")
                        if (f.get("start") or not end or not filed or f.get("val") is None
                                or f.get("form") not in FINANCIAL_REPORT_FORMS
                                or filed > limit or end > filed):
                            continue
                        tags_per_end[end].add(concept)
            ends = [e for e, tags in tags_per_end.items() if len(tags) >= BALANCE_SHEET_MIN_TAGS]
            self._cache[key] = [parse_iso(max(ends)) if ends else None]
        return self._cache[key][0]

    @property
    def stale_inputs(self) -> list[dict]:
        """Every figure rejected as too old, newest rejection per tag - the audit
        trail for the coverage report."""
        return [{"concept": c, "last_reported": e} for c, e in sorted(self._stale.items())]

    def current_tags(self, pattern, *, exclude=frozenset(), noise=None, limit: int = 5) -> list[str]:
        """US-GAAP tags this company reported for its latest period whose names
        match `pattern` - largest value first. Used to suggest where a figure
        went when the tag it used to live under stops resolving."""
        ref = self.reference_end
        if ref is None:
            return []
        sizes: dict[str, float] = {}
        for concept, node in (self._facts.get("us-gaap") or {}).items():
            if concept in exclude or not pattern.search(concept) or (noise and noise.search(concept)):
                continue
            for rows in (node.get("units") or {}).values():
                for f in rows:
                    if (f.get("val") and f.get("end") and f.get("filed")
                            and f.get("form") in FINANCIAL_REPORT_FORMS
                            and parse_iso(f["filed"]) <= self.as_of
                            and abs((parse_iso(f["end"]) - ref).days) <= 10):
                        sizes[concept] = max(sizes.get(concept, 0.0), abs(f["val"]))
        return [c for c, _ in sorted(sizes.items(), key=lambda kv: -kv[1])[:limit]]

    def _fresh(self, fact: dict | None, anchor: date | None = None, max_age: int | None = None) -> dict | None:
        """The fact, unless it is too old to describe `anchor` (by default the
        latest balance sheet), in which case the caller sees nothing and falls
        through to its next resolution path."""
        if fact is None:
            return None
        anchor = anchor or self.reference_end
        if anchor is None:
            return fact  # no balance sheet on file to measure an age against
        max_age = self.max_input_age_days if max_age is None else min(max_age, self.max_input_age_days)
        if parse_iso(fact["end"]) >= anchor - timedelta(days=max_age):
            return fact
        concept = fact.get("concept") or "?"
        if fact["end"] > self._stale.get(concept, ""):
            self._stale[concept] = fact["end"]
        return None

    # ------------------------------------------------------------ lookups

    def _observations(self, concept: str) -> list[dict]:
        key = ("obs", concept)
        if key in self._cache:
            return self._cache[key]
        out: list[dict] = []
        for taxonomy in ("us-gaap", "ifrs-full", "dei"):
            node = (self._facts.get(taxonomy) or {}).get(concept)
            if not node:
                continue
            for unit, rows in (node.get("units") or {}).items():
                if unit not in ("USD", "pure", "shares"):
                    continue
                for f in rows:
                    filed = f.get("filed")
                    if not filed or parse_iso(filed) > self.as_of:
                        continue  # not yet public at the scoring date
                    if f.get("form") not in FINANCIAL_REPORT_FORMS:
                        continue  # proxy statements and the like are not financial reports
                    out.append(
                        {
                            "concept": concept,
                            "start": f.get("start"),
                            "end": f.get("end"),
                            "val": f.get("val"),
                            "filed": filed,
                            "accn": f.get("accn"),
                            "form": f.get("form"),
                        }
                    )
            break
        self._cache[key] = out
        return out

    @staticmethod
    def _latest_per_period(rows: list[dict]) -> dict[tuple, dict]:
        """One value per (start, end): the most recently filed one available at D."""
        best: dict[tuple, dict] = {}
        for f in rows:
            key = (f.get("start"), f.get("end"))
            prev = best.get(key)
            if prev is None or f["filed"] > prev["filed"]:
                best[key] = f
        return best

    # Tag lists whose members nest rather than substitute - total revenue
    # contains revenue from contracts with customers - so for a period the
    # largest value is the total. Registered by the metric layer. By priority,
    # Green Plains resolved to its $0.19B contracts subset instead of $2.09B
    # total revenue, United Rentals to $3.7B instead of $16.4B (rental income is
    # lease revenue, outside the contracts tag), 71 companies in all.
    LARGEST_WINS: set[tuple[str, ...]] = set()

    def durations(self, concepts: list[str]) -> list[dict]:
        """Duration facts, merged across the tag priority list per period.

        Higher-priority tags win a period; lower-priority tags only fill periods
        the higher ones never reported. This handles filers that switched tags
        mid-history without abandoning the priority order. For a nested list
        (LARGEST_WINS) the largest value reported for the period wins instead.
        """
        key = ("dur", tuple(concepts))
        if key in self._cache:
            return self._cache[key]
        largest = tuple(concepts) in self.LARGEST_WINS
        merged: dict[tuple, dict] = {}
        candidates: dict[tuple, list[dict]] = defaultdict(list)
        for concept in concepts:
            rows = [f for f in self._observations(concept) if f.get("start") and f.get("end")]
            for period, fact in self._latest_per_period(rows).items():
                if largest:
                    candidates[period].append(fact)
                else:
                    merged.setdefault(period, fact)
        # Nested tags: the largest - but only among the tags of the most recent
        # filing to report the period. A tag last reported before a restatement
        # describes a different company: Crane NXT's 2022 "Revenues" ($3.4B) is
        # pre-separation Crane, while its restated 2022 is $1.3B.
        for period, facts in candidates.items():
            valued = [f for f in facts if f["val"] is not None] or facts
            newest = max(f["filed"] for f in valued)
            merged[period] = max((f for f in valued if f["filed"] == newest),
                                 key=lambda f: f["val"] if f["val"] is not None else float("-inf"))
        out = sorted(merged.values(), key=lambda f: (f["end"], f["start"]))
        self._cache[key] = out
        return out

    def instants(self, concepts: list[str]) -> list[dict]:
        key = ("inst", tuple(concepts))
        if key in self._cache:
            return self._cache[key]
        merged: dict[tuple, dict] = {}
        for concept in concepts:
            rows = [f for f in self._observations(concept) if not f.get("start") and f.get("end")]
            for period, fact in self._latest_per_period(rows).items():
                merged.setdefault(period, fact)
        out = sorted(merged.values(), key=lambda f: f["end"])
        self._cache[key] = out
        return out

    # ------------------------------------------------------- derived views

    def instant(self, concepts: list[str], on_or_before: date | None = None) -> dict | None:
        """Latest balance-sheet value at or before a date - or None when the
        latest value on file is too old to describe that date."""
        limit = (on_or_before or self.as_of).isoformat()
        rows = [f for f in self.instants(concepts) if f["end"] <= limit and f["val"] is not None]
        return self._fresh(rows[-1], on_or_before) if rows else None

    def instant_near(self, concepts: list[str], target: str, tolerance_days: int = 45) -> dict | None:
        """Balance-sheet value closest to a target period end, for pairing a
        balance-sheet item with a fiscal year whose label may differ."""
        t = parse_iso(target)
        best, best_gap = None, None
        for f in self.instants(concepts):
            if f["val"] is None:
                continue
            gap = abs((parse_iso(f["end"]) - t).days)
            if gap <= tolerance_days and (best_gap is None or gap < best_gap):
                best, best_gap = f, gap
        return best

    def annual_series(self, concepts: list[str], count: int = 6) -> list[dict]:
        """Fiscal-year duration facts, newest first, aligned on period END dates
        rather than fiscal-year labels (fiscal-year changes make labels unsafe)."""
        annual: dict[str, dict] = {}
        for f in self.durations(concepts):
            if f["val"] is None:
                continue
            length = (parse_iso(f["end"]) - parse_iso(f["start"])).days
            if ANNUAL_MIN <= length <= ANNUAL_MAX:
                prev = annual.get(f["end"])
                if prev is None or f["filed"] > prev["filed"]:
                    annual[f["end"]] = f
        rows = sorted(annual.values(), key=lambda f: f["end"], reverse=True)
        # collapse near-duplicate year ends (52/53-week fiscal calendars)
        out: list[dict] = []
        for f in rows:
            if out and abs((parse_iso(out[-1]["end"]) - parse_iso(f["end"])).days) < 200:
                continue
            out.append(f)
        # A series whose newest year is stale belongs to an abandoned tag: its
        # "latest" year is not the company's latest year, so none of it is usable.
        if out and self._fresh(out[0]) is None:
            return []
        return out[:count]

    def ttm(self, concepts: list[str]) -> dict | None:
        """Trailing twelve months, tiled from the most recent reported periods.

        Prefers fresh quarterly/year-to-date coverage over the last annual
        report: scoring in September against a fiscal year that ended eleven
        months ago would be needlessly stale.
        """
        facts = [f for f in self.durations(concepts) if f["val"] is not None]
        if not facts:
            return None
        facts = facts + self._synthesize_tails(facts)
        by_end: dict[str, list[dict]] = defaultdict(list)
        for f in facts:
            by_end[f["end"]].append(f)

        latest_end = max(by_end)
        total = 0.0
        covered = 0
        used: list[dict] = []
        cursor = parse_iso(latest_end)
        for _ in range(6):
            candidates: list[dict] = []
            for end_iso, group in by_end.items():
                if abs((parse_iso(end_iso) - cursor).days) <= 4:
                    candidates.extend(group)
            remaining = 366 - covered
            fitting = [
                f for f in candidates
                if (parse_iso(f["end"]) - parse_iso(f["start"])).days <= remaining + 12
            ]
            if not fitting:
                break
            pick = max(fitting, key=lambda f: (parse_iso(f["end"]) - parse_iso(f["start"])).days)
            length = (parse_iso(pick["end"]) - parse_iso(pick["start"])).days
            total += pick["val"]
            covered += length
            used.append(pick)
            cursor = parse_iso(pick["start"]) - timedelta(days=1)
            if covered >= 350:
                break
        if used and 350 <= covered <= 380:
            newest = max(used, key=lambda f: f["filed"])
            # A single annual fact satisfies the window without any stitching, so
            # it is the last annual report rather than a trailing figure built
            # from quarters. Label it for what it is: the same data reached via
            # the fallback below would otherwise be described differently, and
            # this label is shown to users as provenance.
            stitched_from_one_annual = len(used) == 1 and covered >= ANNUAL_MIN
            max_age = None if stitched_from_one_annual else MAX_QUARTERLY_LAG_DAYS
            return self._fresh({
                "val": total,
                "start": min(f["start"] for f in used),
                "end": latest_end,
                "filed": newest["filed"],
                "accn": newest["accn"],
                "form": newest["form"],
                "concept": used[0]["concept"],
                "basis": "fy" if stitched_from_one_annual else "ttm",
            }, max_age=max_age)
        annual = self.annual_series(concepts, 1)
        if annual:
            return {**annual[0], "basis": "fy"}
        return None

    @staticmethod
    def _synthesize_tails(facts: list[dict]) -> list[dict]:
        """Derive the missing stub period when a filer tags only year-to-date
        figures: a full year minus the nine-month year-to-date is Q4."""
        by_start: dict[str, list[dict]] = defaultdict(list)
        for f in facts:
            by_start[f["start"]].append(f)
        out: list[dict] = []
        for group in by_start.values():
            group = sorted(group, key=lambda f: f["end"])
            for i, shorter in enumerate(group):
                for longer in group[i + 1:]:
                    tail_days = (parse_iso(longer["end"]) - parse_iso(shorter["end"])).days
                    if not (QUARTER_MIN <= tail_days <= ANNUAL_MAX):
                        continue
                    out.append(
                        {
                            "concept": longer["concept"],
                            "start": (parse_iso(shorter["end"]) + timedelta(days=1)).isoformat(),
                            "end": longer["end"],
                            "val": longer["val"] - shorter["val"],
                            "filed": max(longer["filed"], shorter["filed"]),
                            "accn": longer["accn"],
                            "form": longer["form"],
                            "synthetic": True,
                        }
                    )
        return out
