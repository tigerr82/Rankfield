"""Hysteresis on the eligibility floors.

A hard floor makes a company hovering at it enter and leave the ranking month
after month on a percent or two, which is noise and not information. A company
that was scored last month therefore stays eligible until it falls clearly below
the line - `ratio` of the floor - while a company not already ranked must clear
the full floor to enter. The line is asymmetric on purpose: easy to stay, hard
to join.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .util import last_day_of_prior_month, month_key


def previous_scored(history_dir: Path, scoring_date: date) -> set[str]:
    """Tickers scored in the month before `scoring_date`; empty if none stored."""
    prior = last_day_of_prior_month(scoring_date.replace(day=1))
    path = Path(history_dir) / f"scores_{month_key(prior)}.json"
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    return {row["ticker"] for rows in payload.get("segments", {}).values() for row in rows}


def clears(value: float | None, floor: float, *, was_scored: bool, ratio: float) -> bool:
    """Whether `value` satisfies a minimum of `floor`, given last month's status."""
    if value is None:
        return False
    if value >= floor:
        return True
    return was_scored and value >= floor * ratio
