"""Monte Carlo simulation of portfolio value under geometric Brownian motion.

The portfolio is simulated as one process with drift w @ mu and volatility
sqrt(w' Sigma w). For assets that follow correlated GBMs this is exactly the
value of a portfolio rebalanced back to the weights w at every step, so no
per-asset paths (and no Cholesky factor) are needed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from config import settings

# Paths per batch. Keeps memory flat: 2000 paths x 2520 steps is about 40 MB
# per array, whatever --simulations is.
_BATCH = 2000


@dataclass
class SimulationResult:
    """Simulation output. A dataclass rather than a dict so a typo in a key name
    fails loudly instead of quietly returning None."""

    years: int
    n_simulations: int
    target_cagr: float

    median_cagr: float
    p05_cagr: float           # 5th percentile
    p95_cagr: float           # 95th percentile
    prob_above_target: float  # share of paths beating the target

    expected_max_drawdown: float  # mean max drawdown across paths
    worst_max_drawdown: float     # 5th percentile of max drawdown

    sharpe: float
    sortino: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_simulation(
    mu_annual: float,
    vol_annual: float,
    years: int = 10,
    n_simulations: int = 10_000,
    target_cagr: float = 0.14,
    risk_free: float | None = None,
    seed: int | None = None,
) -> SimulationResult:
    """Run `n_simulations` daily paths over `years`.

    mu_annual is the arithmetic drift of the portfolio (the mu of
    dS/S = mu dt + sigma dW), as produced by risk_calculator; vol_annual is
    sigma. Log value then grows at mu - sigma^2/2 per year, so the median CAGR
    is exp(mu - sigma^2/2) - 1 and sits below mu: that gap is the volatility
    drag.

    target_cagr is the success threshold for the probability metric.
    seed=None takes RANDOM_SEED from the settings.
    """
    if vol_annual <= 0:
        raise ValueError("vol_annual должна быть строго положительной")
    if years < 1:
        raise ValueError("years должен быть >= 1")
    if n_simulations < 1:
        raise ValueError("n_simulations должен быть >= 1")

    risk_free = settings.risk_free_rate if risk_free is None else risk_free
    seed = settings.random_seed if seed is None else seed

    steps_per_year = settings.trading_days
    total_steps = years * steps_per_year
    dt = 1.0 / steps_per_year
    step_drift = (mu_annual - 0.5 * vol_annual**2) * dt
    step_vol = vol_annual * np.sqrt(dt)

    # Generator instead of np.random.*, so we don't touch numpy's global state.
    rng = np.random.default_rng(seed)

    final_log = np.empty(n_simulations)
    max_drawdown = np.empty(n_simulations)
    yearly_returns = np.empty((years, n_simulations))

    for start in range(0, n_simulations, _BATCH):
        stop = min(start + _BATCH, n_simulations)

        # Work in logs: one cumsum gives the whole path, and the scheme is exact
        # for GBM at any step size. Capital starts at 1.0, i.e. log value 0.
        log_paths = step_drift + step_vol * rng.standard_normal((total_steps, stop - start))
        np.cumsum(log_paths, axis=0, out=log_paths)

        final_log[start:stop] = log_paths[-1]

        # Running peak, counting the starting capital as the first peak.
        peak = np.maximum(np.maximum.accumulate(log_paths, axis=0), 0.0)
        max_drawdown[start:stop] = np.expm1(log_paths - peak).min(axis=0)  # <= 0

        year_end = log_paths[steps_per_year - 1 :: steps_per_year]  # (years, batch)
        year_start = np.vstack([np.zeros((1, stop - start)), year_end[:-1]])
        yearly_returns[:, start:stop] = np.expm1(year_end - year_start)

    cagr = np.expm1(final_log / years)

    # Sharpe straight from the portfolio parameters: the simulation adds no
    # information here, and averaging across paths biases the estimate.
    sharpe = (mu_annual - risk_free) / vol_annual

    # Sortino on simulated calendar-year returns with the risk-free rate as the
    # minimum acceptable return. Downside deviation divides by all observations
    # but sums only the shortfalls (Sortino & Price, 1994).
    excess = yearly_returns - risk_free
    downside_dev = float(np.sqrt(np.mean(np.minimum(excess, 0.0) ** 2)))
    sortino = float(np.mean(excess) / downside_dev) if downside_dev > 1e-9 else float("inf")

    return SimulationResult(
        years=years,
        n_simulations=n_simulations,
        target_cagr=target_cagr,
        median_cagr=float(np.median(cagr)),
        p05_cagr=float(np.percentile(cagr, 5)),
        p95_cagr=float(np.percentile(cagr, 95)),
        prob_above_target=float(np.mean(cagr > target_cagr)),
        expected_max_drawdown=float(np.mean(max_drawdown)),
        worst_max_drawdown=float(np.percentile(max_drawdown, 5)),
        sharpe=float(sharpe),
        sortino=sortino,
    )


def print_report(res: SimulationResult) -> None:
    """Print the report to stdout."""
    line = "=" * 62
    print(f"\n📊 MONTE CARLO REPORT — горизонт {res.years} лет, {res.n_simulations:,} путей")
    print(line)

    pos_pct = res.prob_above_target * 100
    icon = "🔥" if pos_pct > 60 else ("🙂" if pos_pct > 40 else "⚠️")
    print(f"🎯 P(CAGR > {res.target_cagr:.0%}){'':<18} {icon} {pos_pct:5.1f}%")
    print(f"📈 Медианный CAGR{'':<26} {res.median_cagr * 100:6.2f}%")
    print(f"   ├─ пессимистичный (5%){'':<20} {res.p05_cagr * 100:6.2f}%")
    print(f"   └─ оптимистичный (95%){'':<20} {res.p95_cagr * 100:6.2f}%")
    print("-" * 62)
    print(f"📉 Ожидаемая макс. просадка{'':<16} {res.expected_max_drawdown * 100:6.2f}%")
    print(f"💀 Стресс-сценарий (худшие 5%){'':<13} {res.worst_max_drawdown * 100:6.2f}%")
    print("-" * 62)
    print(f"💎 Sharpe Ratio{'':<28} {res.sharpe:6.2f}")
    print(f"🛡️  Sortino Ratio{'':<27} {res.sortino:6.2f}")
    print(line)
