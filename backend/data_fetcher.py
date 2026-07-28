"""Market data access.

Anything computable (prices, volatility) comes from Yahoo Finance. Anything that
needs interpretation (fundamentals for ADRs and ETFs, reputational risk) goes to
the LLM agent in llm_analyzer.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import yfinance as yf

import llm_analyzer

logger = logging.getLogger(__name__)

# (tickers, period) -> DataFrame. Stops the same Yahoo request going out two or
# three times in a single run.
_PRICE_CACHE: Dict[tuple, pd.DataFrame] = {}


def safe_float(value: Any) -> Optional[float]:
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


def compute_annualized_volatility(ticker: str, period: str = "1y", trading_days: int = 252) -> Optional[float]:
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


def fetch_company_data(ticker: str) -> Dict[str, Any]:
    """Build an asset profile for company_scorer.score_company.

    Missing metrics stay None. The scorer distinguishes "no data" from "bad
    value", and that distinction is what keeps the final number honest.
    """
    ticker = ticker.strip().upper()
    logger.info("Сбор данных по %s", ticker)

    fundamentals = llm_analyzer.fetch_fundamentals_from_web(ticker)
    risks = llm_analyzer.analyze_governance_esg_risk(ticker)

    # Sector picks the normalisation band in sector_config.
    sector = (fundamentals.get("sector") or "").strip() or "Default"

    data: Dict[str, Any] = {
        "ticker": ticker,
        "name": fundamentals.get("name") or ticker,
        "sector": sector,
        "asset_type": fundamentals.get("asset_type", "unknown"),
        "beta": safe_float(fundamentals.get("beta")),
        "return_on_equity": safe_float(fundamentals.get("roe")),
        "profit_margins": safe_float(fundamentals.get("margin")),
        "revenue_growth": safe_float(fundamentals.get("growth")),
        "debt_to_equity": safe_float(fundamentals.get("debt")),
        "volatility_1y": compute_annualized_volatility(ticker),
        "ai_analysis": risks,
    }

    logger.info(
        "%s -> сектор=%s ROE=%s beta=%s vol=%s",
        ticker, sector, data["return_on_equity"], data["beta"], data["volatility_1y"],
    )
    return data


def clear_cache() -> None:
    """Drop the price cache. Useful in tests and long sessions."""
    _PRICE_CACHE.clear()
