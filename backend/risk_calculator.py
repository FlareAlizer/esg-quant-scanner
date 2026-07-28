"""Covariance matrix and expected returns from price history."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Sequence

import numpy as np
import pandas as pd

import data_fetcher
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class RiskModel:
    """Everything is aligned to the same ticker ordering."""

    tickers: List[str]
    cov_matrix: np.ndarray        # annual covariance, (n, n)
    expected_returns: np.ndarray  # annual expected return, (n,)

    @property
    def is_valid(self) -> bool:
        return len(self.tickers) >= 2

    @property
    def n_assets(self) -> int:
        return len(self.tickers)


def calculate_risk_model(
    tickers: Sequence[str],
    period: str = "3y",
    min_coverage: float = 0.8,
) -> RiskModel:
    """Covariance and expected returns from price history.

    3 years of history is a compromise: enough observations for a stable
    covariance, still responsive to a regime change.

    min_coverage is the share of non-missing observations a ticker needs to stay
    in the pool.
    """
    tickers = [t.strip().upper() for t in tickers if t and t.strip()]
    if len(tickers) < 2:
        logger.error("Нужно минимум 2 тикера, получено %d", len(tickers))
        return RiskModel([], np.array([]), np.array([]))

    logger.info("Загрузка истории (%s) для %d тикеров", period, len(tickers))
    prices = data_fetcher.get_historical_prices(tickers, period=period)

    if prices.empty:
        logger.error("Не удалось загрузить исторические цены")
        return RiskModel([], np.array([]), np.array([]))

    # A single ticker arrives as a Series.
    if isinstance(prices, pd.Series):
        prices = prices.to_frame()

    # Drop columns with too many gaps. Requiring full coverage here would throw
    # out every ticker that IPO'd after the start of the window.
    coverage = prices.notna().mean()
    kept = coverage[coverage >= min_coverage].index.tolist()
    dropped = sorted(set(prices.columns) - set(kept))
    if dropped:
        logger.warning("Исключены (покрытие < %.0f%%): %s", min_coverage * 100, ", ".join(dropped))

    prices = prices[kept]

    # Fill internal gaps (weekends, local exchange holidays), then drop rows
    # where some asset is still missing.
    prices = prices.ffill().dropna(axis=0, how="any")

    if prices.shape[1] < 2 or len(prices) < 60:
        logger.error(
            "Недостаточно данных после очистки: %d активов, %d наблюдений",
            prices.shape[1], len(prices),
        )
        return RiskModel([], np.array([]), np.array([]))

    # Log returns are additive in time, so covariance and the 252 scaling are
    # well defined on them.
    log_returns = np.log(prices / prices.shift(1)).dropna()

    annual_log_mean = log_returns.mean() * settings.trading_days
    # Back to simple returns. Skipping this reads 30% log as 30% simple when it
    # is really about 35%.
    annual_expected_returns = np.expm1(annual_log_mean)

    annual_cov = log_returns.cov() * settings.trading_days

    ordered_tickers = list(annual_cov.columns)
    logger.info(
        "Риск-модель готова: %d активов, ковариация %s",
        len(ordered_tickers), annual_cov.shape,
    )

    return RiskModel(
        tickers=ordered_tickers,
        cov_matrix=annual_cov.values,
        # reindex keeps the order in sync with the covariance matrix.
        expected_returns=annual_expected_returns.reindex(ordered_tickers).values,
    )
