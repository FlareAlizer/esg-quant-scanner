"""Portfolio construction via SLSQP.

Two modes: maximise the PARKS score under a volatility cap, or minimise risk for
a target return (Markowitz).
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import minimize

import company_scorer
import data_fetcher
import risk_calculator

logger = logging.getLogger(__name__)

# Scored tickers, so we don't hit the LLM twice for the same asset.
_SCORE_CACHE: Dict[str, Dict[str, Any]] = {}

# Below this a weight is solver noise, not a position.
_DISPLAY_THRESHOLD = 0.001  # 0.1%


def preload_score_cache(ticker: str, score_data: Dict[str, Any]) -> None:
    """Let main.py drop an already-computed score into the cache."""
    if "total_score" in score_data:
        _SCORE_CACHE[ticker.upper()] = score_data


def clear_score_cache() -> None:
    _SCORE_CACHE.clear()


def _get_scored_companies(tickers: Sequence[str]) -> List[Dict[str, Any]]:
    """Scores for the given tickers, fetching whatever is missing."""
    scored: List[Dict[str, Any]] = []
    for ticker in tickers:
        key = ticker.upper()
        if key in _SCORE_CACHE:
            scored.append(_SCORE_CACHE[key])
            continue

        data = data_fetcher.fetch_company_data(key)
        if not data:
            logger.warning("Пропуск %s: нет данных", key)
            continue

        result = company_scorer.score_company(key, data)
        _SCORE_CACHE[key] = result
        scored.append(result)
    return scored


def _clean_weights(
    weights: np.ndarray,
    tickers: Sequence[str],
    threshold: float = _DISPLAY_THRESHOLD,
) -> Dict[str, float]:
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
        for ticker, w in zip(tickers, normalized)
        if w > 0
    }
    # Largest first, so the report reads top down.
    return dict(sorted(result.items(), key=lambda kv: kv[1], reverse=True))


def _feasible_start(n_assets: int, lower: float, upper: float) -> np.ndarray:
    """A starting point inside [lower, upper] that sums to 1.

    Equal weights of 1/n can fall outside the bounds, in which case we take the
    closest feasible point instead. SLSQP often fails to converge from an
    infeasible start.
    """
    equal = 1.0 / n_assets
    if lower <= equal <= upper:
        return np.full(n_assets, equal)

    start = np.clip(np.full(n_assets, equal), lower, upper)
    total = start.sum()
    return start / total if total > 0 else np.full(n_assets, equal)


def _bounds_are_feasible(n_assets: int, lower: float, upper: float) -> bool:
    """Weights can only sum to 1 when n*lower <= 1 <= n*upper."""
    return lower * n_assets <= 1.0 <= upper * n_assets


def _solve(
    objective: Callable[[np.ndarray], float],
    constraints: List[Dict[str, Any]],
    bounds: Tuple[Tuple[float, float], ...],
    initial_guess: np.ndarray,
) -> Optional[Any]:
    """Thin wrapper over scipy.minimize with error logging."""
    try:
        return minimize(
            objective,
            initial_guess,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 1000, "ftol": 1e-9},
        )
    except Exception as exc:
        logger.error("Ошибка солвера: %s", exc)
        return None


def _attempt_ladder(min_weight: float, max_weight: float) -> List[Tuple[float, float]]:
    """Try the caller's bounds first, then progressively looser ones."""
    ladder = [(min_weight, max_weight), (0.0, max_weight), (0.0, 1.0)]
    seen, unique = set(), []
    for pair in ladder:
        if pair not in seen:
            seen.add(pair)
            unique.append(pair)
    return unique


# Mode 1: maximise PARKS score under a volatility cap

def optimize_by_score(
    tickers: Sequence[str],
    volatility_threshold: float = 0.20,
    max_weight: float = 0.30,
    min_weight: float = 0.0,
) -> Dict[str, Any]:
    """Maximise the weighted quality score subject to a volatility cap."""
    logger.info(
        "PARKS-оптимизация: риск <= %.1f%%, веса %.0f%%-%.0f%%",
        volatility_threshold * 100, min_weight * 100, max_weight * 100,
    )

    scored = _get_scored_companies(tickers)
    if not scored:
        return {"error": "Нет данных для скоринга."}

    score_map = {item["ticker"]: item["total_score"] for item in scored}
    risk = risk_calculator.calculate_risk_model(list(score_map.keys()))
    if not risk.is_valid:
        return {"error": "Недостаточно активов с историческими данными (нужно минимум 2)."}

    # An asset needs both a score and price history.
    final_tickers = [t for t in risk.tickers if t in score_map]
    if len(final_tickers) < 2:
        return {"error": "После пересечения скоров и истории цен осталось менее 2 активов."}

    # np.ix_ keeps row i and column i pointing at the same ticker.
    index_of = {t: i for i, t in enumerate(risk.tickers)}
    idx = [index_of[t] for t in final_tickers]
    cov = risk.cov_matrix[np.ix_(idx, idx)]
    scores = np.array([score_map[t] for t in final_tickers])
    n = len(final_tickers)

    # scipy only minimises, so maximising the score means minimising its negation.
    def objective(w: np.ndarray) -> float:
        return -float(w @ scores)

    def portfolio_vol(w: np.ndarray) -> float:
        return float(np.sqrt(w @ cov @ w))

    constraints = [
        {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
        {"type": "ineq", "fun": lambda w: volatility_threshold - portfolio_vol(w)},
    ]

    for lower, upper in _attempt_ladder(min_weight, max_weight):
        if not _bounds_are_feasible(n, lower, upper):
            logger.warning("Границы [%.2f, %.2f] несовместимы с %d активами", lower, upper, n)
            continue

        result = _solve(objective, constraints, tuple((lower, upper) for _ in range(n)),
                        _feasible_start(n, lower, upper))

        if result is not None and result.success:
            w = result.x
            return {
                "optimized_weights_pct": _clean_weights(w, final_tickers),
                "expected_portfolio_score": round(float(w @ scores), 2),
                "expected_portfolio_volatility": round(portfolio_vol(w), 4),
                "max_volatility_target": volatility_threshold,
                "n_assets": n,
                # The bounds actually used can differ from the ones requested if
                # the ladder kicked in. Report both, so nothing claims a
                # constraint the solution doesn't respect.
                "requested_bounds": (min_weight, max_weight),
                "applied_bounds": (lower, upper),
            }

    return {"error": "Не удалось найти решение при заданных ограничениях."}


# Mode 2: mean-variance (Markowitz)

def optimize_mean_variance(
    tickers: Sequence[str],
    target_return: float,
    max_weight: float = 0.30,
    min_weight: float = 0.0,
) -> Dict[str, Any]:
    """Minimise volatility subject to return >= target_return."""
    logger.info(
        "MVO: цель %.1f%%, веса %.0f%%-%.0f%%",
        target_return * 100, min_weight * 100, max_weight * 100,
    )

    risk = risk_calculator.calculate_risk_model(tickers)
    if not risk.is_valid:
        return {"error": "Нет достаточных исторических данных."}

    cov, mu, n = risk.cov_matrix, risk.expected_returns, risk.n_assets

    # A portfolio is a convex combination, so no set of weights beats the best
    # single asset. Targets above that are unreachable by construction.
    max_achievable = float(np.max(mu))
    if target_return > max_achievable:
        logger.warning(
            "Цель %.1f%% недостижима (максимум по пулу %.1f%%) — понижаем",
            target_return * 100, max_achievable * 100,
        )
        target_return = max_achievable * 0.99

    def objective(w: np.ndarray) -> float:
        return float(np.sqrt(w @ cov @ w))

    constraints = [
        {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
        {"type": "ineq", "fun": lambda w: float(w @ mu) - target_return},
    ]

    for lower, upper in _attempt_ladder(min_weight, max_weight):
        if not _bounds_are_feasible(n, lower, upper):
            logger.warning("Границы [%.2f, %.2f] несовместимы с %d активами", lower, upper, n)
            continue

        result = _solve(objective, constraints, tuple((lower, upper) for _ in range(n)),
                        _feasible_start(n, lower, upper))

        if result is not None and result.success:
            w = result.x
            # Recompute on the cleaned weights. On the raw ones the report would
            # describe a portfolio nobody can actually buy.
            cleaned = _clean_weights(w, risk.tickers)
            w_clean = np.array([cleaned.get(t, 0.0) / 100 for t in risk.tickers])

            return {
                "optimized_weights_pct": cleaned,
                "achieved_portfolio_return": round(float(w_clean @ mu), 4),
                "expected_portfolio_volatility": round(float(np.sqrt(w_clean @ cov @ w_clean)), 4),
                "target_return": round(target_return, 4),
                "n_assets": n,
                # See optimize_by_score: requested and applied bounds can differ.
                "requested_bounds": (min_weight, max_weight),
                "applied_bounds": (lower, upper),
            }

    return {"error": "Не удалось собрать портфель под заданную доходность."}
