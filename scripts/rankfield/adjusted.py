"""Month-end prices on one common basis, so a split or a spin-off is not read as a collapse.

Each monthly record stores the price as it stood on that run, and also `prior_price`: the previous
month-end re-read from the same run's adjusted series. The ratio between that and the price the
previous record stored is exactly what the later run learned about the earlier month (a split, a
spin-off, dividends paid since). Chaining those ratios back from the newest month puts every month
on today's basis. Records are never rewritten; the adjusted series is derived from them each time.
"""
from __future__ import annotations


def _rows(record: dict) -> dict[str, dict]:
    return {r["ticker"]: r for seg in record.get("segments", {}).values() for r in seg}


def _positive(value) -> bool:
    return isinstance(value, (int, float)) and value > 0


def adjusted_prices(records: dict[str, dict], latest_rows: dict[str, dict] | None = None) -> dict[str, dict[str, float | None]]:
    """month -> ticker -> price on the newest basis, or None where the chain cannot be linked.

    `latest_rows` (ticker -> row of the current payload) replaces the newest month's price and
    prior price with the weekly-restated ones, so a split after the monthly run is also caught.
    A company missing from a month in between, or a month without a usable prior price, breaks the
    chain: the months before the break are left None rather than guessed.
    """
    months = sorted(records)
    rows = {m: _rows(records[m]) for m in months}
    out: dict[str, dict[str, float | None]] = {m: {} for m in months}
    tickers = {t for m in months for t in rows[m]}
    for ticker in tickers:
        cum: float | None = 1.0
        seen_later = False
        for i in range(len(months) - 1, -1, -1):
            month = months[i]
            row = rows[month].get(ticker)
            if row is None:
                if seen_later:
                    cum = None
                continue
            if i == len(months) - 1 and latest_rows and ticker in latest_rows:
                row = {**row, "price": latest_rows[ticker].get("price"), "prior_price": latest_rows[ticker].get("prior_price")}
            price = row.get("price")
            out[month][ticker] = round(price * cum, 4) if cum is not None and _positive(price) else None
            seen_later = True
            if cum is None or i == 0:
                continue
            before = rows[months[i - 1]].get(ticker)
            if before is not None and _positive(before.get("price")) and _positive(row.get("prior_price")):
                cum *= row["prior_price"] / before["price"]
            elif before is not None:
                cum = None
    return out
