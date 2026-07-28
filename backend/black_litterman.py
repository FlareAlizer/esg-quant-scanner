"""Black-Litterman allocation with views driven by a GQV factor.

Instead of feeding historical returns straight into the optimiser, we start from
equilibrium returns implied by market caps and tilt them by our own views. View
strength scales with the factor Z-score.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import zscore

logger = logging.getLogger(__name__)


def download_prices(tickers: List[str], period: str = "5y") -> pd.DataFrame:
    """Close prices. auto_adjust is explicit, so the column is 'Close' and already
    adjusted for splits and dividends."""
    raw = yf.download(tickers, period=period, progress=False, auto_adjust=True)
    if raw is None or raw.empty:
        return pd.DataFrame()

    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if isinstance(close, pd.Series):
        close = close.to_frame(name=tickers[0])
    elif list(close.columns) == ["Close"]:
        # With one ticker the column is called "Close" while everything
        # downstream looks it up by ticker.
        close = close.rename(columns={"Close": tickers[0]})

    # ffill only. bfill would leak future prices backwards.
    return close.ffill().dropna(axis=0, how="any")


def calculate_gqv_score(info: Dict) -> Optional[float]:
    """Growth, Quality, Valuation composite.

    Quality gets 0.4 against 0.3 each for the others: it is more persistent over
    time than growth rates. Returns None when there isn't enough data, so a
    company with no numbers doesn't read as a company with bad ones.
    """
    growth = info.get("revenueGrowth")
    roe = info.get("returnOnEquity")
    margins = info.get("profitMargins")
    pe = info.get("trailingPE")

    if all(v is None for v in (growth, roe, margins, pe)):
        return None

    growth = growth or 0.0
    roe = roe or 0.0
    margins = margins or 0.0

    # Earnings yield: cheaper is better. No P/E or a negative one contributes nothing.
    valuation = (1.0 / pe) if (pe and pe > 0) else 0.0

    return 0.3 * growth + 0.4 * (roe + margins) + 0.3 * valuation * 100


def collect_fundamentals(
    tickers: List[str],
    bond_tickers: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Market caps and GQV scores. Bond proxies are skipped: GQV is meaningless for them."""
    bond_tickers = set(bond_tickers or [])
    market_caps: Dict[str, float] = {}
    gqv_raw: Dict[str, Optional[float]] = {}

    for ticker in tickers:
        # Declared per iteration; leaking it between tickers corrupts the scores.
        info: Dict = {}
        market_cap = np.nan

        try:
            obj = yf.Ticker(ticker)
            fast = obj.fast_info
            market_cap = getattr(fast, "market_cap", np.nan)

            if market_cap is None or (isinstance(market_cap, float) and np.isnan(market_cap)):
                info = obj.info or {}
                market_cap = info.get("marketCap", 1e9)

            if ticker not in bond_tickers:
                info = info or (obj.info or {})
                gqv_raw[ticker] = calculate_gqv_score(info)
            else:
                gqv_raw[ticker] = None
        except Exception as exc:
            logger.warning("Не удалось получить данные по %s: %s", ticker, exc)
            market_cap = 1e9  # placeholder, keeps the asset in the prior
            gqv_raw[ticker] = None

            # Yahoo can return marketCap = None: the key exists but holds
            # nothing, so .get()'s default never fires and float(None) throws.
        try:
            market_caps[ticker] = float(market_cap)
        except (TypeError, ValueError):
            logger.warning("Некорректная капитализация у %s (%r) — подставляем заглушку", ticker, market_cap)
            market_caps[ticker] = 1e9

    df = pd.DataFrame(
        {
            "Ticker": list(market_caps.keys()),
            "MarketCap": list(market_caps.values()),
            "GQV_Raw": [gqv_raw.get(t) for t in market_caps],
        }
    )

    # Z-score only over assets that have one. The rest get 0, a neutral view
    # rather than a negative one.
    mask = df["GQV_Raw"].notna()
    df["Z_Score"] = 0.0
    if mask.sum() >= 2:
        df.loc[mask, "Z_Score"] = zscore(df.loc[mask, "GQV_Raw"].astype(float))

    return df, market_caps


def build_views(
    df_gqv: pd.DataFrame,
    market_prior: pd.Series,
    bond_tickers: List[str],
    sensitivity: float = 0.05,
) -> Tuple[Dict[str, float], List[float]]:
    """Turn Z-scores into absolute views.

    sensitivity=0.05 means a Z of +1 shifts expected return 5pp above
    equilibrium. Confidence grows with |Z| but caps at 90%, otherwise the model
    collapses onto a single name.
    """
    bond_set = set(bond_tickers)
    views: Dict[str, float] = {}
    confidences: List[float] = []

    for _, row in df_gqv.iterrows():
        ticker = row["Ticker"]
        if ticker in bond_set or ticker not in market_prior.index:
            continue

        z = float(row["Z_Score"])
        views[ticker] = float(market_prior[ticker]) + z * sensitivity
        confidences.append(0.4 + min(abs(z) * 0.1, 0.5))

    return views, confidences
