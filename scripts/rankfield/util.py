"""HTTP with rate limiting/retries, date helpers, and the scoring maths.

Kept dependency-light on purpose: `requests` plus the standard library. The
statistical work here (winsorize, percentile rank) is a few lines each, so
pandas/numpy would be weight without benefit in a job that runs monthly.
"""
from __future__ import annotations

import math
import threading
import time
from datetime import date, datetime, timedelta
from typing import Iterable, Sequence

import requests

# ---------------------------------------------------------------- http


class RateLimiter:
    """Simple token-free limiter: never more than `per_sec` starts per second."""

    def __init__(self, per_sec: float):
        self._min_gap = 1.0 / per_sec if per_sec > 0 else 0.0
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next:
                time.sleep(self._next - now)
                now = time.monotonic()
            self._next = now + self._min_gap


def http_json(
    url: str,
    *,
    user_agent: str,
    limiter: RateLimiter | None = None,
    timeout: int = 45,
    retries: int = 4,
    allow_404: bool = False,
):
    """GET JSON with backoff. Returns None on an allowed 404."""
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    last_err: Exception | None = None
    for attempt in range(retries):
        if limiter:
            limiter.wait()
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 404 and allow_404:
                return None
            if resp.status_code in (429, 502, 503, 504):
                time.sleep(min(2 ** attempt, 20))
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001 - retried below, raised at the end
            last_err = exc
            time.sleep(min(2 ** attempt, 20))
    if allow_404:
        return None
    raise RuntimeError(f"GET failed after {retries} attempts: {url} ({last_err})")


# ---------------------------------------------------------------- dates


def parse_iso(s: str) -> date:
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def last_day_of_prior_month(run_day: date) -> date:
    """Scoring date = the last calendar day of the month before the run."""
    first_of_this = run_day.replace(day=1)
    return first_of_this - timedelta(days=1)


def month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def shift_months(d: date, months: int) -> date:
    y, m = d.year, d.month + months
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


# ---------------------------------------------------------------- maths


def percentile_of(values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile of a sorted-able sequence. q in 0..100."""
    xs = sorted(v for v in values if v is not None and _finite(v))
    if not xs:
        return float("nan")
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * (q / 100.0)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return xs[int(pos)]
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def winsorize(values: Sequence[float], lo_pct: float, hi_pct: float) -> list[float]:
    """Clip to the [lo_pct, hi_pct] percentiles so one extreme cannot distort ranking."""
    clean = [v for v in values if v is not None and _finite(v)]
    if len(clean) < 3:
        return list(values)
    lo = percentile_of(clean, lo_pct)
    hi = percentile_of(clean, hi_pct)
    out = []
    for v in values:
        if v is None or not _finite(v):
            out.append(None)
        else:
            out.append(min(max(v, lo), hi))
    return out


def percentile_ranks(values: Sequence[float | None], higher_better: bool) -> list[float | None]:
    """Rank each value against its cohort, 0..100 (100 = best).

    Ties share the average rank. Missing values stay missing — never imputed,
    never scored as zero.
    """
    idx = [i for i, v in enumerate(values) if v is not None and _finite(v)]
    n = len(idx)
    out: list[float | None] = [None] * len(values)
    if n == 0:
        return out
    if n == 1:
        out[idx[0]] = 50.0
        return out
    # Best first: descending when a high value is good, ascending when a low
    # one is (debt/equity, earnings variability). ordered[0] scores 100.
    ordered = sorted(idx, key=lambda i: values[i], reverse=higher_better)
    # average rank across ties
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[ordered[j + 1]] == values[ordered[i]]:
            j += 1
        avg_pos = (i + j) / 2.0
        pct = 100.0 * (1.0 - avg_pos / (n - 1))
        for k in range(i, j + 1):
            out[ordered[k]] = round(pct, 1)
        i = j + 1
    return out


def mean(xs: Iterable[float]) -> float | None:
    xs = [x for x in xs if x is not None and _finite(x)]
    return sum(xs) / len(xs) if xs else None


def stdev(xs: Iterable[float]) -> float | None:
    xs = [x for x in xs if x is not None and _finite(x)]
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def safe_div(num, den):
    """Zero or missing denominator -> None. Never zero, never infinity."""
    if num is None or den is None:
        return None
    try:
        if den == 0:
            return None
        out = num / den
    except (TypeError, ZeroDivisionError):
        return None
    return out if _finite(out) else None


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
