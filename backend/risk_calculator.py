"""Covariance matrix and expected returns from price history."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

import data_fetcher
from config import settings

logger = logging.getLogger(__name__)

# Below this many daily observations the covariance estimate is noise.
MIN_OBSERVATIONS = 60


@dataclass
class RiskModel:
    """Everything is aligned to the same ticker ordering."""

    tickers: list[str]
    cov_matrix: np.ndarray        # annual covariance of log returns, (n, n)
    expected_returns: np.ndarray  # annual arithmetic drift, (n,)

    @property
    def is_valid(self) -> bool:
        return len(self.tickers) >= 2

    @property
    def n_assets(self) -> int:
        return len(self.tickers)


_EMPTY = RiskModel([], np.empty((0, 0)), np.empty(0))


def estimate_from_prices(prices: pd.DataFrame, trading_days: int | None = None) -> RiskModel:
    """Annualised drift and covariance from a clean date x ticker price frame.

    Works on daily log returns r_t = ln(P_t / P_{t-1}):

        cov = sample covariance of r (ddof=1) * trading_days
        m   = mean(r) * trading_days          annual log growth, ln(1 + CAGR)
        mu  = m + diag(cov) / 2               arithmetic drift

    Under geometric Brownian motion a log return over dt is distributed
    N((mu - sigma^2/2) dt, sigma^2 dt), so the mean of log returns estimates
    mu - sigma^2/2, not mu. Mean-variance needs mu: portfolio drift is linear
    in it (w @ mu), while log growth is not linear in the weights. The
    volatility drag is taken off once, at portfolio level, in monte_carlo.
    """
    trading_days = settings.trading_days if trading_days is None else trading_days

    # A zero or negative price gives inf or NaN here; that is caught below.
    with np.errstate(divide="ignore", invalid="ignore"):
        log_returns = np.log(prices / prices.shift(1)).dropna(how="any")
        if log_returns.shape[1] < 1 or len(log_returns) < 2:
            return _EMPTY

        cov = log_returns.cov() * trading_days
        log_growth = log_returns.mean() * trading_days
        drift = log_growth + 0.5 * np.diag(cov.values)

    if not (np.isfinite(cov.values).all() and np.isfinite(drift.values).all()):
        logger.error("В ценах есть нули или отрицательные значения: доходности не определены")
        return _EMPTY

    tickers = [str(c) for c in cov.columns]
    return RiskModel(tickers=tickers, cov_matrix=cov.values, expected_returns=drift.values)


def calculate_risk_model(
    tickers: Sequence[str],
    period: str = "3y",
    min_coverage: float = 0.8,
) -> RiskModel:
    """Download prices, clean them and estimate the risk model.

    3 years of history is a compromise: enough observations for a stable
    covariance, still responsive to a regime change.

    min_coverage is the share of non-missing observations a ticker needs to stay
    in the pool.
    """
    tickers = [t.strip().upper() for t in tickers if t and t.strip()]
    if len(tickers) < 2:
        logger.error("Нужно минимум 2 тикера, получено %d", len(tickers))
        return _EMPTY

    logger.info("Загрузка истории (%s) для %d тикеров", period, len(tickers))
    prices = data_fetcher.get_historical_prices(tickers, period=period)

    if prices.empty:
        logger.error("Не удалось загрузить исторические цены")
        return _EMPTY

    # Drop columns with too many gaps. Requiring full coverage here would throw
    # out every ticker that IPO'd after the start of the window.
    coverage = prices.notna().mean()
    kept = coverage[coverage >= min_coverage].index.tolist()
    dropped = sorted(set(prices.columns) - set(kept))
    if dropped:
        logger.warning("Исключены (покрытие < %.0f%%): %s", min_coverage * 100, ", ".join(dropped))

    # Fill internal gaps (local exchange holidays), then drop rows where some
    # asset is still missing.
    prices = prices[kept].ffill().dropna(axis=0, how="any")

    if prices.shape[1] < 2 or len(prices) < MIN_OBSERVATIONS:
        logger.error(
            "Недостаточно данных после очистки: %d активов, %d наблюдений",
            prices.shape[1], len(prices),
        )
        return _EMPTY

    model = estimate_from_prices(prices)
    logger.info("Риск-модель готова: %d активов, %d наблюдений", model.n_assets, len(prices) - 1)
    return model
