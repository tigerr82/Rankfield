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


class FactSet:
    def __init__(self, facts_json: dict, as_of: date):
        self.as_of = as_of
        self.entity = facts_json.get("entityName")
        self._facts = facts_json.get("facts") or {}
        self._cache: dict[tuple, list[dict]] = {}
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

    def durations(self, concepts: list[str]) -> list[dict]:
        """Duration facts, merged across the tag priority list per period.

        Higher-priority tags win a period; lower-priority tags only fill periods
        the higher ones never reported. This handles filers that switched tags
        mid-history without abandoning the priority order.
        """
        key = ("dur", tuple(concepts))
        if key in self._cache:
            return self._cache[key]
        merged: dict[tuple, dict] = {}
        for concept in concepts:
            rows = [f for f in self._observations(concept) if f.get("start") and f.get("end")]
            for period, fact in self._latest_per_period(rows).items():
                merged.setdefault(period, fact)
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
        """Latest balance-sheet value at or before a date."""
        limit = (on_or_before or self.as_of).isoformat()
        rows = [f for f in self.instants(concepts) if f["end"] <= limit and f["val"] is not None]
        return rows[-1] if rows else None

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
            return {
                "val": total,
                "start": min(f["start"] for f in used),
                "end": latest_end,
                "filed": newest["filed"],
                "accn": newest["accn"],
                "form": newest["form"],
                "concept": used[0]["concept"],
                "basis": "fy" if stitched_from_one_annual else "ttm",
            }
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
