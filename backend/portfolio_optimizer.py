"""Portfolio construction via SLSQP.

Two modes: minimise risk for a target return (Markowitz), or maximise the PARKS
score under a volatility cap. Both are long-only by default and treat the weight
bounds as hard constraints: an infeasible request is rejected with a reason
instead of being quietly relaxed.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import numpy as np
from scipy.optimize import minimize

import company_scorer
import data_fetcher
import risk_calculator

logger = logging.getLogger(__name__)

# Scored tickers, so we don't hit the LLM twice for the same asset.
_SCORE_CACHE: dict[str, dict[str, Any]] = {}

# Below this a weight is solver noise, not a position.
_DISPLAY_THRESHOLD = 0.001  # 0.1%

# Slack for checking a solution against its constraints.
_TOL = 1e-6


class InfeasibleError(ValueError):
    """The constraints cannot all hold at once."""


def preload_score_cache(ticker: str, score_data: dict[str, Any]) -> None:
    """Let main.py drop an already-computed score into the cache."""
    if "total_score" in score_data:
        _SCORE_CACHE[ticker.upper()] = score_data


def clear_score_cache() -> None:
    _SCORE_CACHE.clear()


def _get_scored_companies(tickers: Sequence[str]) -> list[dict[str, Any]]:
    """Scores for the given tickers, fetching whatever is missing."""
    scored: list[dict[str, Any]] = []
    for ticker in tickers:
        key = ticker.upper()
        if key not in _SCORE_CACHE:
            _SCORE_CACHE[key] = company_scorer.score_company(key, data_fetcher.fetch_company_data(key))
        scored.append(_SCORE_CACHE[key])
    return scored


def _clean_weights(
    weights: np.ndarray,
    tickers: Sequence[str],
    threshold: float = _DISPLAY_THRESHOLD,
) -> dict[str, float]:
    """Drop noise weights and renormalise the rest to 100%.

    The renormalisation matters: without it the discarded fractions just vanish
    and the reported weights no longer describe the portfolio the return and risk
    were computed on.
    """
    weights = np.asarray(weights, dtype=float)
    filtered = np.where(weights >= threshold, weights, 0.0)

    total = filtered.sum()
    if total <= 0:
        return {}

    normalized = filtered / total
    result = {
        ticker: round(float(w) * 100, 2)
        for ticker, w in zip(tickers, normalized, strict=True)
        if w > 0
    }
    # Largest first, so the report reads top down.
    return dict(sorted(result.items(), key=lambda kv: kv[1], reverse=True))


def check_bounds(n_assets: int, lower: float, upper: float) -> None:
    """Weights in [lower, upper] can only sum to 1 when n*lower <= 1 <= n*upper."""
    if lower > upper:
        raise InfeasibleError(f"Минимальная доля {lower:.0%} больше максимальной {upper:.0%}.")
    if lower * n_assets > 1.0 + _TOL:
        raise InfeasibleError(
            f"Минимум {lower:.0%} на {n_assets} активов даёт сумму {lower * n_assets:.0%} > 100%."
        )
    if upper * n_assets < 1.0 - _TOL:
        raise InfeasibleError(
            f"Максимум {upper:.0%} на {n_assets} активов даёт сумму {upper * n_assets:.0%} < 100%: "
            f"нужен --max-weight не меньше {1 / n_assets:.0%}."
        )


def max_return_under_bounds(mu: np.ndarray, lower: float, upper: float) -> float:
    """Highest w @ mu reachable with sum(w) = 1 and lower <= w <= upper.

    Everyone starts at the lower bound, then the remaining budget goes to the
    highest-return assets first, each up to its cap. With a 25% cap this is the
    mean of the top four, not the best single asset.
    """
    mu = np.asarray(mu, dtype=float)
    check_bounds(len(mu), lower, upper)

    weights = np.full(len(mu), lower)
    budget = 1.0 - weights.sum()
    for i in np.argsort(mu)[::-1]:
        add = min(upper - lower, budget)
        weights[i] += add
        budget -= add
        if budget <= 0:
            break
    return float(weights @ mu)


def _solve(objective, jac, constraints, n_assets: int, lower: float, upper: float) -> np.ndarray:
    # Equal weights always satisfy feasible uniform bounds: lower <= 1/n <= upper
    # is the feasibility condition itself.
    start = np.full(n_assets, 1.0 / n_assets)
    result = minimize(
        objective,
        start,
        jac=jac,
        method="SLSQP",
        bounds=[(lower, upper)] * n_assets,
        constraints=constraints,
        options={"maxiter": 1000, "ftol": 1e-12},
    )
    if not result.success:
        raise InfeasibleError(f"Солвер не сошёлся: {result.message}")

    weights = np.clip(result.x, lower, upper)
    return weights / weights.sum()


def min_variance_weights(
    cov: np.ndarray,
    mu: np.ndarray,
    target_return: float,
    lower: float = 0.0,
    upper: float = 1.0,
) -> np.ndarray:
    """Markowitz: minimise w' Sigma w subject to sum(w) = 1, w @ mu >= target.

    The return constraint is an inequality, so a target below the return of the
    minimum-variance portfolio simply yields that portfolio. The objective is the
    variance rather than the volatility: same minimiser, but a quadratic with an
    exact gradient, which SLSQP handles better than a square root.
    """
    cov = np.asarray(cov, dtype=float)
    mu = np.asarray(mu, dtype=float)
    n = len(mu)

    best = max_return_under_bounds(mu, lower, upper)
    if target_return > best + _TOL:
        raise InfeasibleError(
            f"Цель {target_return:.1%} недостижима: при долях {lower:.0%}-{upper:.0%} "
            f"максимум по пулу {best:.1%}."
        )

    constraints = [
        {"type": "eq", "fun": lambda w: w.sum() - 1.0, "jac": lambda w: np.ones(n)},
        {"type": "ineq", "fun": lambda w: w @ mu - target_return, "jac": lambda w: mu},
    ]
    return _solve(lambda w: 0.5 * w @ cov @ w, lambda w: cov @ w, constraints, n, lower, upper)


def max_score_weights(
    cov: np.ndarray,
    scores: np.ndarray,
    max_volatility: float,
    lower: float = 0.0,
    upper: float = 1.0,
) -> np.ndarray:
    """Maximise w @ scores subject to sum(w) = 1, sqrt(w' Sigma w) <= max_volatility."""
    cov = np.asarray(cov, dtype=float)
    scores = np.asarray(scores, dtype=float)
    n = len(scores)
    check_bounds(n, lower, upper)

    # The cap is written on the variance to keep the constraint smooth.
    constraints = [
        {"type": "eq", "fun": lambda w: w.sum() - 1.0, "jac": lambda w: np.ones(n)},
        {"type": "ineq", "fun": lambda w: max_volatility**2 - w @ cov @ w, "jac": lambda w: -2.0 * cov @ w},
    ]
    # scipy only minimises, so maximising the score means minimising its negation.
    weights = _solve(lambda w: -(w @ scores), lambda w: -scores, constraints, n, lower, upper)

    vol = float(np.sqrt(weights @ cov @ weights))
    if vol > max_volatility + 1e-4:
        raise InfeasibleError(
            f"Риск {max_volatility:.1%} недостижим при долях {lower:.0%}-{upper:.0%}: "
            f"лучшее найденное {vol:.1%}."
        )
    return weights


def _portfolio_stats(weights: np.ndarray, tickers: Sequence[str], risk) -> dict[str, Any]:
    """Report on the cleaned weights. On the raw ones the numbers would describe
    a portfolio that differs from the printed one.

    The drift w @ mu is a continuously compounded rate; the return shown to the
    user is the matching effective annual rate exp(drift) - 1.
    """
    cleaned = _clean_weights(weights, tickers)
    w = np.array([cleaned.get(t, 0.0) / 100 for t in tickers])
    drift = float(w @ risk.expected_returns)
    return {
        "optimized_weights_pct": cleaned,
        "expected_portfolio_drift": drift,
        "achieved_portfolio_return": round(float(np.expm1(drift)), 4),
        "expected_portfolio_volatility": round(float(np.sqrt(w @ risk.cov_matrix @ w)), 4),
        "n_assets": len(tickers),
    }


def optimize_mean_variance(
    tickers: Sequence[str],
    target_return: float,
    max_weight: float = 0.30,
    min_weight: float = 0.0,
) -> dict[str, Any]:
    """Minimise volatility subject to expected return >= target_return.

    target_return is an effective annual rate (0.14 = 14% a year) and is
    converted to a drift, ln(1 + target), for the solver.

    On failure returns {"error": reason}; when the target is the problem the
    dict also carries "max_feasible_return" so the caller can lower it.
    """
    logger.info(
        "MVO: цель %.1f%%, веса %.0f%%-%.0f%%",
        target_return * 100, min_weight * 100, max_weight * 100,
    )

    risk = risk_calculator.calculate_risk_model(tickers)
    if not risk.is_valid:
        return {"error": "Нет достаточных исторических данных."}

    try:
        best_drift = max_return_under_bounds(risk.expected_returns, min_weight, max_weight)
    except InfeasibleError as exc:
        return {"error": str(exc)}

    best = float(np.expm1(best_drift))
    if target_return > best + _TOL:
        return {
            "error": (
                f"Цель {target_return:.1%} недостижима: при долях {min_weight:.0%}-{max_weight:.0%} "
                f"максимум по пулу {best:.1%}."
            ),
            "max_feasible_return": best,
        }

    try:
        # min() guards the exact-maximum case against rounding in log1p/expm1.
        target_drift = min(float(np.log1p(target_return)), best_drift)
        weights = min_variance_weights(
            risk.cov_matrix, risk.expected_returns, target_drift, min_weight, max_weight
        )
    except InfeasibleError as exc:
        return {"error": str(exc)}

    return {**_portfolio_stats(weights, risk.tickers, risk), "target_return": round(target_return, 4)}


def optimize_by_score(
    tickers: Sequence[str],
    volatility_threshold: float = 0.20,
    max_weight: float = 0.30,
    min_weight: float = 0.0,
) -> dict[str, Any]:
    """Maximise the weighted PARKS score subject to a volatility cap."""
    logger.info(
        "PARKS-оптимизация: риск <= %.1f%%, веса %.0f%%-%.0f%%",
        volatility_threshold * 100, min_weight * 100, max_weight * 100,
    )

    # A total built on one or two components is not a ranking signal.
    score_map = {
        item["ticker"]: item["total_score"] for item in _get_scored_companies(tickers) if item["reliable"]
    }
    risk = risk_calculator.calculate_risk_model(list(score_map))
    if not risk.is_valid:
        return {"error": "Недостаточно активов с историческими данными (нужно минимум 2)."}

    # risk.tickers is a subset of the scored ones: tickers without enough price
    # history were dropped along the way.
    scores = np.array([score_map[t] for t in risk.tickers])
    try:
        weights = max_score_weights(risk.cov_matrix, scores, volatility_threshold, min_weight, max_weight)
    except InfeasibleError as exc:
        return {"error": str(exc)}

    stats = _portfolio_stats(weights, risk.tickers, risk)
    w = np.array([stats["optimized_weights_pct"].get(t, 0.0) / 100 for t in risk.tickers])
    return {
        **stats,
        "expected_portfolio_score": round(float(w @ scores), 2),
        "max_volatility_target": volatility_threshold,
    }
