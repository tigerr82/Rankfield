"""Data-source adapters.

Every external fetch in this project goes through one of these. Each provider
implements a small, documented interface so swapping a source is a one-file
change rather than a rewrite:

    UniverseProvider.fetch()        -> list[Listing]
    FundamentalsProvider.facts(cik) -> dict  (raw point-in-time facts)
    PriceProvider.history(ticker)   -> PriceSeries

Select by name so the choice is configuration, not code.
"""
from __future__ import annotations

from .fundamentals_edgar import EdgarFundamentals
from .prices_stooq import StooqPrices
from .prices_yahoo import YahooPrices
from .universe_nasdaq import NasdaqUniverse

_UNIVERSE = {"nasdaq": NasdaqUniverse}
_FUNDAMENTALS = {"edgar": EdgarFundamentals}
_PRICES = {"yahoo": YahooPrices, "stooq": StooqPrices}


def get_universe_provider(name: str = "nasdaq", **kw):
    return _UNIVERSE[name](**kw)


def get_fundamentals_provider(name: str = "edgar", **kw):
    return _FUNDAMENTALS[name](**kw)


def get_price_provider(name: str = "yahoo", **kw):
    return _PRICES[name](**kw)
