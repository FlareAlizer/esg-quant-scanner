"""The simulated process is one lognormal, so every quantile has a closed form."""

import math

import numpy as np
import pandas as pd
import pytest

import monte_carlo
import risk_calculator

Z05 = -1.6448536269514722  # 5% quantile of the standard normal


def test_cagr_quantiles_match_the_lognormal_closed_form():
    mu, vol, years = 0.10, 0.20, 4
    res = monte_carlo.run_simulation(mu, vol, years=years, n_simulations=40_000, seed=8)

    growth = mu - 0.5 * vol**2             # 0.08 per year in logs
    spread = Z05 * vol / math.sqrt(years)  # 5% quantile of the mean annual log return
    assert res.median_cagr == pytest.approx(math.expm1(growth), abs=2e-3)
    assert res.p05_cagr == pytest.approx(math.expm1(growth + spread), abs=4e-3)
    assert res.p95_cagr == pytest.approx(math.expm1(growth - spread), abs=4e-3)

    # A target placed exactly on the median is beaten half of the time.
    res = monte_carlo.run_simulation(
        mu, vol, years=years, n_simulations=40_000, seed=8, target_cagr=math.expm1(growth)
    )
    assert res.prob_above_target == pytest.approx(0.5, abs=0.01)


def test_single_asset_simulation_reproduces_its_historical_cagr():
    # Estimating a GBM from one price series and simulating it back must give
    # the realised growth as the median outcome, with no extra drag.
    rng = np.random.default_rng(3)
    r = rng.normal(0.0004, 0.015, 756)
    prices = pd.DataFrame({"A": 100 * np.exp(np.concatenate([[0.0], r]).cumsum())})
    prices["B"] = prices["A"]

    model = risk_calculator.estimate_from_prices(prices, 252)
    mu, vol = model.expected_returns[0], math.sqrt(model.cov_matrix[0, 0])
    res = monte_carlo.run_simulation(mu, vol, years=3, n_simulations=40_000, seed=11)

    historical_cagr = (prices["A"].iloc[-1] / prices["A"].iloc[0]) ** (252 / 756) - 1
    assert res.median_cagr == pytest.approx(historical_cagr, abs=3e-3)


def test_sharpe_uses_the_risk_free_rate():
    res = monte_carlo.run_simulation(0.10, 0.20, years=1, n_simulations=100, risk_free=0.04, seed=1)
    # Both rates continuously compounded: (0.10 - ln 1.04) / 0.20
    assert res.sharpe == pytest.approx((0.10 - math.log(1.04)) / 0.20)
    assert res.sharpe == pytest.approx(0.3039, abs=1e-4)


def test_drawdowns_are_losses_and_ordered():
    res = monte_carlo.run_simulation(0.08, 0.25, years=2, n_simulations=5_000, seed=5)

    assert -1.0 < res.worst_max_drawdown < res.expected_max_drawdown < 0.0


def test_almost_riskless_path_has_no_drawdown_and_infinite_sortino():
    res = monte_carlo.run_simulation(0.10, 1e-9, years=2, n_simulations=10, risk_free=0.0, seed=1)

    assert res.median_cagr == pytest.approx(math.expm1(0.10), abs=1e-6)
    assert res.expected_max_drawdown == pytest.approx(0.0, abs=1e-6)
    assert res.sortino == float("inf")


def test_seed_makes_runs_reproducible_across_batch_boundaries():
    kwargs = dict(mu_annual=0.07, vol_annual=0.15, years=1, n_simulations=4_500)
    first = monte_carlo.run_simulation(seed=123, **kwargs)

    assert first == monte_carlo.run_simulation(seed=123, **kwargs)
    assert first != monte_carlo.run_simulation(seed=124, **kwargs)


@pytest.mark.parametrize("bad", [dict(vol_annual=0.0), dict(years=0), dict(n_simulations=0)])
def test_invalid_arguments_raise(bad):
    with pytest.raises(ValueError):
        monte_carlo.run_simulation(**{"mu_annual": 0.1, "vol_annual": 0.2, **bad})
