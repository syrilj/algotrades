from __future__ import annotations

import re
from typing import Optional

from .contracts import Instrument, InstrumentCategory, InstrumentClassification


_CATEGORY_ALIASES = {
    "stock": InstrumentCategory.STOCK,
    "stocks": InstrumentCategory.STOCK,
    "common stock": InstrumentCategory.STOCK,
    "common stocks": InstrumentCategory.STOCK,
    "equity": InstrumentCategory.STOCK,
    "equities": InstrumentCategory.STOCK,
    "etf": InstrumentCategory.ETF,
    "etfs": InstrumentCategory.ETF,
    "exchange traded fund": InstrumentCategory.ETF,
    "exchange traded funds": InstrumentCategory.ETF,
    "fx": InstrumentCategory.FX,
    "forex": InstrumentCategory.FX,
    "foreign exchange": InstrumentCategory.FX,
    "currency pair": InstrumentCategory.FX,
    "currency pairs": InstrumentCategory.FX,
    "crypto": InstrumentCategory.CRYPTO,
    "cryptocurrency": InstrumentCategory.CRYPTO,
    "cryptocurrencies": InstrumentCategory.CRYPTO,
    "digital asset": InstrumentCategory.CRYPTO,
    "digital assets": InstrumentCategory.CRYPTO,
    "commodity": InstrumentCategory.COMMODITY,
    "commodities": InstrumentCategory.COMMODITY,
    "index": InstrumentCategory.INDEX,
    "indices": InstrumentCategory.INDEX,
    "market index": InstrumentCategory.INDEX,
    "market indices": InstrumentCategory.INDEX,
    "future": InstrumentCategory.FUTURE,
    "futures": InstrumentCategory.FUTURE,
    "option": InstrumentCategory.OPTION,
    "options": InstrumentCategory.OPTION,
    "economic": InstrumentCategory.ECONOMICS,
    "economics": InstrumentCategory.ECONOMICS,
    "economic indicator": InstrumentCategory.ECONOMICS,
    "economic indicators": InstrumentCategory.ECONOMICS,
    "bond": InstrumentCategory.BOND,
    "bonds": InstrumentCategory.BOND,
    "government bond": InstrumentCategory.BOND,
    "government bonds": InstrumentCategory.BOND,
    "corporate bond": InstrumentCategory.BOND,
    "corporate bonds": InstrumentCategory.BOND,
    "yield": InstrumentCategory.YIELD,
    "yields": InstrumentCategory.YIELD,
    "bond yield": InstrumentCategory.YIELD,
    "bond yields": InstrumentCategory.YIELD,
    "interest rate": InstrumentCategory.INTEREST_RATE,
    "interest rates": InstrumentCategory.INTEREST_RATE,
    "currency index": InstrumentCategory.CURRENCY_INDEX,
    "currency indices": InstrumentCategory.CURRENCY_INDEX,
}

_TRADABLE_CATEGORIES = {
    InstrumentCategory.STOCK,
    InstrumentCategory.ETF,
    InstrumentCategory.FX,
    InstrumentCategory.CRYPTO,
    InstrumentCategory.COMMODITY,
    InstrumentCategory.INDEX,
    InstrumentCategory.FUTURE,
    InstrumentCategory.OPTION,
}

_CONTEXT_CATEGORIES = {
    InstrumentCategory.ECONOMICS,
    InstrumentCategory.BOND,
    InstrumentCategory.YIELD,
    InstrumentCategory.INTEREST_RATE,
    InstrumentCategory.CURRENCY_INDEX,
}

_ASSET_CLASSES = {
    InstrumentCategory.STOCK: "equity",
    InstrumentCategory.ETF: "equity",
    InstrumentCategory.FX: "fx",
    InstrumentCategory.CRYPTO: "crypto",
    InstrumentCategory.COMMODITY: "commodity",
    InstrumentCategory.INDEX: "index",
    InstrumentCategory.FUTURE: "future",
    InstrumentCategory.OPTION: "option",
    InstrumentCategory.ECONOMICS: "macro",
    InstrumentCategory.BOND: "fixed_income",
    InstrumentCategory.YIELD: "fixed_income",
    InstrumentCategory.INTEREST_RATE: "rates",
    InstrumentCategory.CURRENCY_INDEX: "fx_context",
    InstrumentCategory.UNKNOWN: "unknown",
}


def _category_key(raw_category: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", raw_category.lower())).strip()


def normalize_category(raw_category: str) -> InstrumentCategory:
    return _CATEGORY_ALIASES.get(_category_key(raw_category), InstrumentCategory.UNKNOWN)


def classify_category(
    category: InstrumentCategory,
    explicitly_tradable: Optional[bool] = None,
) -> InstrumentClassification:
    if category == InstrumentCategory.UNKNOWN:
        return InstrumentClassification.UNSUPPORTED
    if explicitly_tradable is True:
        return InstrumentClassification.TRADABLE
    if explicitly_tradable is False:
        return InstrumentClassification.CONTEXT_ONLY
    if category in _TRADABLE_CATEGORIES:
        return InstrumentClassification.TRADABLE
    if category in _CONTEXT_CATEGORIES:
        return InstrumentClassification.CONTEXT_ONLY
    return InstrumentClassification.UNSUPPORTED


def instrument_from_catalog(
    symbol: str,
    name: str,
    category: str,
    explicitly_tradable: Optional[bool] = None,
) -> Instrument:
    normalized = normalize_category(category)
    return Instrument(
        symbol=symbol,
        name=name,
        category=normalized,
        classification=classify_category(normalized, explicitly_tradable),
        asset_class=_ASSET_CLASSES[normalized],
    )
