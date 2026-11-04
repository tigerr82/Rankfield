import json
from datetime import date
from pathlib import Path

from rankfield.facts import FactSet, merge_predecessor_facts
from rankfield.providers.fundamentals_edgar import has_successor_notice


def _facts(entries, name="X"):
    return {"entityName": name, "facts": {"us-gaap": {"Assets": {"label": "Assets", "units": {"USD": entries}}}}}


def _entry(end, val, accn, form="10-Q", filed=None):
    return {"end": end, "val": val, "accn": accn, "form": form, "filed": filed or end, "fy": 2026, "fp": "Q1"}


def test_a_successor_reads_its_predecessors_filings_as_its_own():
    old = _facts([_entry(f"2025-0{m}-28", 100 + m, f"old-{m}") for m in range(1, 8)], "Old Corp")
    new = _facts([_entry("2025-09-28", 109, "new-1"), _entry("2025-10-28", 110, "new-2")], "New Holdings")
    assert FactSet(new, date(2025, 12, 31)).quarters_filed == 2
    merged = merge_predecessor_facts(new, [old])
    assert merged["entityName"] == "New Holdings"
    assert FactSet(merged, date(2025, 12, 31)).quarters_filed == 9


def test_identical_facts_are_kept_once_and_the_inputs_are_not_changed():
    shared = _entry("2025-03-31", 5, "a")
    old, new = _facts([shared]), _facts([dict(shared), _entry("2025-06-30", 6, "b")])
    merged = merge_predecessor_facts(new, [old])
    assert len(merged["facts"]["us-gaap"]["Assets"]["units"]["USD"]) == 2
    assert len(old["facts"]["us-gaap"]["Assets"]["units"]["USD"]) == 1


def test_an_8k12b_marks_a_possible_successor_issuer():
    assert has_successor_notice({"filings": {"recent": {"form": ["8-K", "8-K12B"]}}})
    assert not has_successor_notice({"filings": {"recent": {"form": ["8-K", "10-Q"]}}})
    assert not has_successor_notice(None)


def test_every_configured_successor_names_a_predecessor():
    cfg = json.loads((Path(__file__).resolve().parents[1] / "config" / "successors.json").read_text(encoding="utf-8"))
    for cik, entry in cfg["successors"].items():
        assert len(cik) == 10 and entry["predecessors"] and cik not in entry["predecessors"]
