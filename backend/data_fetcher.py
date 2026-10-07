"""Market data access.

Anything computable or structured (prices, volatility, reported fundamentals)
comes from Yahoo Finance. Anything that needs interpretation (fundamentals Yahoo
lacks for ADRs and ETFs, reputational risk) goes to the LLM agent in
llm_analyzer.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from typing import Any

import pandas as pd
import yfinance as yf

import llm_analyzer
import sector_config

logger = logging.getLogger(__name__)

# (tickers, period) -> DataFrame. Stops the same Yahoo request going out two or
# three times in a single run.
_PRICE_CACHE: dict[tuple, pd.DataFrame] = {}


def safe_float(value: Any) -> float | None:
    """Coerce to float, returning None for anything that isn't a finite number."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in {"", "nan", "none", "null", "n/a"}:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def get_historical_prices(tickers: Iterable[str], period: str = "5y") -> pd.DataFrame:
    """Adjusted close prices as a date x ticker frame.

    yfinance hands back three different shapes depending on the call: flat
    columns for one ticker, a MultiIndex for several, and no 'Adj Close' at all
    under auto_adjust. Normalise all of them here.
    """
    tickers = [t.strip().upper() for t in tickers if t and t.strip()]
    if not tickers:
        return pd.DataFrame()

    cache_key = (tuple(sorted(tickers)), period)
    if cache_key in _PRICE_CACHE:
        return _PRICE_CACHE[cache_key].copy()

    try:
        raw = yf.download(
            tickers,
            period=period,
            progress=False,
            auto_adjust=True,  # already adjusted for splits and dividends
            threads=True,
        )
    except Exception as exc:  # network failures, Yahoo parse errors
        logger.warning("Не удалось скачать цены (%s): %s", ", ".join(tickers), exc)
        return pd.DataFrame()

    if raw is None or raw.empty:
        return pd.DataFrame()

    if isinstance(raw.columns, pd.MultiIndex):
        # Several tickers: slice 'Close' off the first level.
        if "Close" not in raw.columns.get_level_values(0):
            return pd.DataFrame()
        close = raw["Close"]
    elif "Close" in raw.columns:
        # One ticker: wrap the Series into a frame named after it.
        close = raw[["Close"]].rename(columns={"Close": tickers[0]})
    else:
        return pd.DataFrame()

    if isinstance(close, pd.Series):
        close = close.to_frame(name=tickers[0])

    _PRICE_CACHE[cache_key] = close.copy()
    return close


def compute_annualized_volatility(ticker: str, period: str = "1y", trading_days: int = 252) -> float | None:
    """Annualised volatility: std of daily returns times sqrt(252).

    Computed, not asked of the LLM. There is an exact formula and the model has
    no edge here.
    """
    prices = get_historical_prices([ticker], period=period)
    if prices.empty or ticker not in prices.columns:
        return None

    daily_returns = prices[ticker].pct_change().dropna()
    # Under ~20 observations the std estimate is noise.
    if len(daily_returns) < 20:
        return None

    return float(daily_returns.std() * math.sqrt(trading_days))


# Scored metrics. Fractions (0.15 = 15%), except debt_to_equity, which is in
# percent as Yahoo reports it. The values name the matching Yahoo .info fields.
_YAHOO_FIELDS = {
    "beta": "beta",
    "return_on_equity": "returnOnEquity",
    "profit_margins": "profitMargins",
    "revenue_growth": "revenueGrowth",
    "debt_to_equity": "debtToEquity",
}

_ASSET_TYPES = {"equity": "stock", "etf": "etf", "mutualfund": "fund"}


def fetch_yahoo_fundamentals(ticker: str) -> dict[str, Any]:
    """Fundamentals from Yahoo's quote summary. Gaps stay None; {} if the call fails.

    Yahoo covers ordinary US stocks well and returns next to nothing for ETFs
    and many ADRs. Those gaps are what the LLM agent is for.
    """
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as exc:  # noqa: BLE001  yfinance raises anything from KeyError to HTTP errors
        logger.warning("Yahoo не отдал профиль %s: %s", ticker, exc)
        return {}

    data: dict[str, Any] = {metric: safe_float(info.get(field)) for metric, field in _YAHOO_FIELDS.items()}
    # ETFs carry beta under a different key.
    if data["beta"] is None:
        data["beta"] = safe_float(info.get("beta3Year"))

    data["name"] = info.get("longName") or info.get("shortName")
    data["sector"] = info.get("sector")
    data["industry"] = info.get("industry")
    data["asset_type"] = _ASSET_TYPES.get(str(info.get("quoteType", "")).lower(), "unknown")
    return data


def fetch_company_data(ticker: str) -> dict[str, Any]:
    """Build an asset profile for company_scorer.score_company.

    Yahoo first, then the LLM agent for whatever Yahoo left empty. Missing
    metrics stay None. The scorer distinguishes "no data" from "bad value", and
    that distinction is what keeps the final number honest.
    """
    ticker = ticker.strip().upper()
    logger.info("Сбор данных по %s", ticker)

    yahoo = fetch_yahoo_fundamentals(ticker)
    asset_type = yahoo.get("asset_type", "unknown")

    web: dict[str, Any] = {}
    if any(yahoo.get(metric) is None for metric in _YAHOO_FIELDS):
        web = llm_analyzer.fetch_fundamentals_from_web(ticker, asset_type)

    data: dict[str, Any] = {
        "ticker": ticker,
        "name": yahoo.get("name") or web.get("name") or ticker,
        # Picks the normalisation band in sector_config.
        "sector": sector_config.resolve_sector(yahoo.get("sector") or web.get("sector"), yahoo.get("industry")),
        "asset_type": asset_type,
        "volatility_1y": compute_annualized_volatility(ticker),
        "ai_analysis": llm_analyzer.analyze_governance_esg_risk(ticker),
    }
    for metric in _YAHOO_FIELDS:
        value = yahoo.get(metric)
        data[metric] = value if value is not None else safe_float(web.get(metric))

    logger.info(
        "%s -> сектор=%s ROE=%s beta=%s vol=%s",
        ticker, data["sector"], data["return_on_equity"], data["beta"], data["volatility_1y"],
    )
    return data


def clear_cache() -> None:
    """Drop the price cache. Useful in tests and long sessions."""
    _PRICE_CACHE.clear()
