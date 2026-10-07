"""Hand-checkable cases for the estimator and the optimiser."""

import numpy as np
import pandas as pd
import pytest

import portfolio_optimizer as po
import risk_calculator


def _prices(log_returns: dict[str, list[float]]) -> pd.DataFrame:
    """Price frame that produces exactly the given daily log returns."""
    frame = pd.DataFrame(log_returns)
    start = pd.DataFrame([[0.0] * frame.shape[1]], columns=frame.columns)
    return 100.0 * np.exp(pd.concat([start, frame], ignore_index=True).cumsum())


def test_constant_growth_has_no_variance_and_drift_equals_log_growth():
    model = risk_calculator.estimate_from_prices(_prices({"A": [0.001] * 10, "B": [0.002] * 10}), 252)

    assert model.tickers == ["A", "B"]
    np.testing.assert_allclose(model.cov_matrix, 0.0, atol=1e-18)
    np.testing.assert_allclose(model.expected_returns, [0.252, 0.504])


def test_covariance_is_sample_covariance_annualised():
    # r = [a, -a, a, -a]: mean 0, sample variance 4a^2 / 3.
    a = 0.01
    model = risk_calculator.estimate_from_prices(
        _prices({"A": [a, -a, a, -a], "B": [-a, a, -a, a]}), 252
    )

    var = 252 * 4 * a**2 / 3
    np.testing.assert_allclose(model.cov_matrix, [[var, -var], [-var, var]])
    # Zero log growth, so the drift is the variance correction alone.
    np.testing.assert_allclose(model.expected_returns, [var / 2, var / 2])


def test_drift_is_log_growth_plus_half_variance():
    rng = np.random.default_rng(0)
    r = rng.normal(0.0005, 0.02, 500)
    model = risk_calculator.estimate_from_prices(_prices({"A": list(r), "B": list(r[::-1])}), 252)

    expected = 252 * r.mean() + 0.5 * 252 * r.var(ddof=1)
    assert model.expected_returns[0] == pytest.approx(expected)


def test_non_positive_prices_are_rejected():
    prices = pd.DataFrame({"A": [1.0, 0.0, 1.0], "B": [1.0, 2.0, 3.0]})
    assert not risk_calculator.estimate_from_prices(prices, 252).is_valid


def test_min_variance_of_two_uncorrelated_assets():
    # Weights are inversely proportional to the variances: (0.01, 0.04) / 0.05.
    cov = np.diag([0.04, 0.01])
    w = po.min_variance_weights(cov, np.array([0.05, 0.05]), target_return=0.0)

    np.testing.assert_allclose(w, [0.2, 0.8], atol=1e-6)
    assert w @ cov @ w == pytest.approx(0.008, abs=1e-9)


def test_binding_return_target_fixes_two_asset_weights():
    # 0.10 w + 0.20 (1 - w) = 0.16  =>  w = 0.4
    cov = np.diag([0.01, 0.09])
    w = po.min_variance_weights(cov, np.array([0.10, 0.20]), target_return=0.16)

    np.testing.assert_allclose(w, [0.4, 0.6], atol=1e-6)


def test_weights_respect_bounds_and_sum_to_one():
    rng = np.random.default_rng(1)
    a = rng.normal(size=(6, 6))
    cov = a @ a.T / 100
    mu = np.linspace(0.02, 0.20, 6)
    w = po.min_variance_weights(cov, mu, target_return=0.12, lower=0.05, upper=0.30)

    assert w.sum() == pytest.approx(1.0)
    assert w.min() >= 0.05 - 1e-9
    assert w.max() <= 0.30 + 1e-9
    assert w @ mu >= 0.12 - 1e-6


def test_singular_covariance_still_solves():
    # Two identical assets: any split between them has the same risk.
    cov = np.array([[0.04, 0.04, 0.0], [0.04, 0.04, 0.0], [0.0, 0.0, 0.01]])
    w = po.min_variance_weights(cov, np.array([0.1, 0.1, 0.1]), target_return=0.0)

    assert w.sum() == pytest.approx(1.0)
    assert w[0] + w[1] == pytest.approx(0.2, abs=1e-5)
    assert w[2] == pytest.approx(0.8, abs=1e-5)


def test_max_return_accounts_for_the_weight_cap():
    mu = np.array([0.30, 0.10, 0.10])
    assert po.max_return_under_bounds(mu, 0.0, 1.0) == pytest.approx(0.30)
    assert po.max_return_under_bounds(mu, 0.0, 0.5) == pytest.approx(0.20)
    # 10% floor everywhere, the remaining 70% goes to the best asset.
    assert po.max_return_under_bounds(mu, 0.1, 1.0) == pytest.approx(0.8 * 0.30 + 0.2 * 0.10)


def test_unreachable_target_is_an_error_not_a_relaxed_cap():
    cov = np.diag([0.04, 0.01, 0.01])
    with pytest.raises(po.InfeasibleError, match="недостижима"):
        po.min_variance_weights(cov, np.array([0.30, 0.10, 0.10]), target_return=0.25, upper=0.5)


@pytest.mark.parametrize(("lower", "upper"), [(0.0, 0.25), (0.4, 1.0), (0.6, 0.5)])
def test_incompatible_bounds_are_rejected(lower, upper):
    with pytest.raises(po.InfeasibleError):
        po.check_bounds(3, lower, upper)


def test_max_score_puts_everything_allowed_into_the_best_score():
    cov = np.diag([0.01, 0.01, 0.01])
    w = po.max_score_weights(cov, np.array([9.0, 5.0, 1.0]), max_volatility=1.0, upper=0.6)

    np.testing.assert_allclose(w, [0.6, 0.4, 0.0], atol=1e-6)


def test_max_score_volatility_cap_binds():
    # Best score is the risky asset. 0.09 w^2 <= 0.15^2  =>  w <= 0.5
    cov = np.diag([0.09, 0.0])
    w = po.max_score_weights(cov, np.array([9.0, 1.0]), max_volatility=0.15)

    np.testing.assert_allclose(w, [0.5, 0.5], atol=1e-4)


def test_clean_weights_renormalises():
    cleaned = po._clean_weights(np.array([0.6, 0.3995, 0.0005]), ["A", "B", "C"])

    assert list(cleaned) == ["A", "B"]
    assert sum(cleaned.values()) == pytest.approx(100.0, abs=0.02)


@pytest.fixture
def two_asset_model(monkeypatch):
    model = risk_calculator.RiskModel(["A", "B"], np.diag([0.01, 0.09]), np.array([0.10, 0.20]))
    monkeypatch.setattr(risk_calculator, "calculate_risk_model", lambda tickers: model)
    return model


def test_target_return_is_an_effective_annual_rate(two_asset_model):
    # A 16% target means a drift of ln(1.16), reached at w_B = (ln 1.16 - 0.10) / 0.10.
    result = po.optimize_mean_variance(["A", "B"], target_return=0.16, max_weight=1.0)

    w_b = (np.log(1.16) - 0.10) / 0.10
    assert result["optimized_weights_pct"]["B"] == pytest.approx(100 * w_b, abs=0.01)
    assert result["achieved_portfolio_return"] == pytest.approx(0.16, abs=1e-4)
    assert np.expm1(result["expected_portfolio_drift"]) == pytest.approx(0.16, abs=1e-4)


def test_unreachable_target_reports_the_best_reachable_return(two_asset_model):
    result = po.optimize_mean_variance(["A", "B"], target_return=0.50, max_weight=0.6)

    best = np.expm1(0.6 * 0.20 + 0.4 * 0.10)
    assert "недостижима" in result["error"]
    assert result["max_feasible_return"] == pytest.approx(best)

    # Asking for exactly that maximum must work and keep the 60% cap.
    retry = po.optimize_mean_variance(["A", "B"], target_return=result["max_feasible_return"], max_weight=0.6)
    assert retry["optimized_weights_pct"] == {"B": 60.0, "A": 40.0}


def test_incompatible_bounds_surface_as_an_error(two_asset_model):
    result = po.optimize_mean_variance(["A", "B"], target_return=0.05, max_weight=0.3)

    assert "error" in result
    assert "max_feasible_return" not in result
