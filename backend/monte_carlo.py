"""Monte Carlo simulation of portfolio value under geometric Brownian motion."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict

import numpy as np

from config import settings


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
    worst_max_drawdown: float     # worst 5% of scenarios

    sharpe: float
    sortino: float

    def as_dict(self) -> Dict[str, Any]:
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
    """Run `n_simulations` paths over `years`.

    mu_annual and vol_annual are portfolio-level annual figures (0.14 = 14%).
    target_cagr is the success threshold for the probability metric.
    """
    if vol_annual <= 0:
        raise ValueError("vol_annual должна быть строго положительной")
    if years < 1:
        raise ValueError("years должен быть >= 1")

    risk_free = settings.risk_free_rate if risk_free is None else risk_free
    seed = settings.random_seed if seed is None else seed

    steps_per_year = settings.trading_days
    total_steps = years * steps_per_year
    dt = 1.0 / steps_per_year

    # Generator instead of np.random.*, so we don't touch numpy's global state.
    rng = np.random.default_rng(seed)

    # Work in logs: more stable than multiplying 2520 factors, and one cumsum
    # gives the whole path.
    z = rng.standard_normal((total_steps, n_simulations))
    log_increments = (mu_annual - 0.5 * vol_annual**2) * dt + vol_annual * np.sqrt(dt) * z

    # Start at 1.0 (normalised capital), then accumulate log increments.
    log_paths = np.vstack([np.zeros((1, n_simulations)), np.cumsum(log_increments, axis=0)])
    price_paths = np.exp(log_paths)  # shape: (total_steps + 1, n_simulations)

    final_values = price_paths[-1]
    cagr = final_values ** (1.0 / years) - 1.0

    prob_above_target = float(np.mean(cagr > target_cagr))

    running_max = np.maximum.accumulate(price_paths, axis=0)
    drawdowns = price_paths / running_max - 1.0  # <= 0 by construction
    max_dd_per_path = drawdowns.min(axis=0)

    # Sharpe straight from the portfolio parameters: the simulation adds no
    # information here, and averaging across paths biases the estimate.
    sharpe = (mu_annual - risk_free) / vol_annual

    # Sortino needs downside deviation, so we slice each path every 252 steps to
    # get realised annual returns.
    yearly_slices = price_paths[::steps_per_year]           # (years + 1, n_sim)
    yearly_returns = yearly_slices[1:] / yearly_slices[:-1] - 1.0
    excess = yearly_returns - risk_free
    downside = np.minimum(excess, 0.0)
    # Divide by all observations but sum only the negative ones. That is the
    # definition of downside deviation (Sortino, 1994).
    downside_dev = float(np.sqrt(np.mean(downside**2)))
    sortino = float(np.mean(excess) / downside_dev) if downside_dev > 1e-9 else float("inf")

    return SimulationResult(
        years=years,
        n_simulations=n_simulations,
        target_cagr=target_cagr,
        median_cagr=float(np.median(cagr)),
        p05_cagr=float(np.percentile(cagr, 5)),
        p95_cagr=float(np.percentile(cagr, 95)),
        prob_above_target=prob_above_target,
        expected_max_drawdown=float(np.mean(max_dd_per_path)),
        worst_max_drawdown=float(np.percentile(max_dd_per_path, 5)),
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
