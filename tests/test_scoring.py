"""PARKS scoring on profiles small enough to compute by hand."""

import pytest

import company_scorer
import sector_config
from company_scorer import normalize, score_company

LLM_BLOCK = {
    "llm_available": True,
    "governance_score": 8.0,
    "innovation_score": 6.0,
    "esg_news_score": 7.0,
    "controversy_risk_score": 4.0,
    "governance_reasoning": "g",
    "esg_reasoning": "e",
    "risk_reasoning": "r",
}


def test_normalize_is_linear_inside_the_band_and_saturates_outside():
    assert normalize(0.15, 0.05, 0.25) == pytest.approx(5.0)
    assert normalize(0.05, 0.05, 0.25) == 0.0
    assert normalize(0.90, 0.05, 0.25) == 10.0
    assert normalize(-1.0, 0.05, 0.25) == 0.0


def test_normalize_inverted_metric_rewards_low_values():
    assert normalize(20.0, 20.0, 200.0, invert=True) == 10.0
    assert normalize(110.0, 20.0, 200.0, invert=True) == pytest.approx(5.0)
    assert normalize(500.0, 20.0, 200.0, invert=True) == 0.0


@pytest.mark.parametrize("missing", [None, "n/a", float("nan")])
def test_normalize_keeps_missing_values_missing(missing):
    assert normalize(missing, 0.0, 1.0) is None


def test_full_profile_on_default_bands():
    # Default bands: ROE 5-25%, margin 5-30%, growth 5-20%, vol 15-60% inv,
    # D/E 20-200 inv, beta 0.8-1.5 inv.
    data = {
        "sector": "Default",
        "return_on_equity": 0.15,   # 5.0
        "profit_margins": 0.30,     # 10.0
        "revenue_growth": 0.125,    # 5.0
        "volatility_1y": 0.15,      # 10.0
        "debt_to_equity": 110.0,    # 5.0
        "beta": 1.5,                # 0.0
        "ai_analysis": LLM_BLOCK,
    }
    result = score_company("X", data)
    parts = {code: block["score"] for code, block in result["components"].items()}

    assert parts["P"] == pytest.approx(7.5)
    assert parts["A"] == pytest.approx(5.0)
    assert parts["R"] == pytest.approx(5.0)
    assert parts["K"] == pytest.approx(7.0)   # (8 + 6) / 2
    assert parts["S"] == pytest.approx(5.0)   # 7 - 4 / 2
    assert result["total_score"] == pytest.approx((7.5 + 5.0 + 5.0 + 7.0 + 5.0) / 5)
    assert result["data_coverage"] == 1.0
    assert result["reliable"] is True
    assert result["sector_band"] == "Default"
    assert result["bucket"].endswith("(среднее качество)")


def test_missing_metric_is_left_out_of_its_component():
    data = {"return_on_equity": 0.25, "profit_margins": None, "ai_analysis": LLM_BLOCK}
    result = score_company("X", data)

    assert result["components"]["P"]["score"] == pytest.approx(10.0)
    assert result["components"]["P"]["coverage"] == "1/2"
    assert result["data_coverage"] == pytest.approx(round(1 / 6, 2))


def test_without_llm_k_and_s_do_not_enter_the_total():
    data = {
        "return_on_equity": 0.25,
        "profit_margins": 0.30,
        "revenue_growth": 0.20,
        "ai_analysis": {"llm_available": False, "governance_score": 5.0, "controversy_risk_score": 9.0},
    }
    result = score_company("X", data)

    assert result["components"]["K"]["score"] is None
    assert result["components"]["S"]["score"] is None
    assert result["components"]["R"]["score"] is None
    # Only P and A were scored, both at the top of their bands. Two components
    # are shown as a number but not turned into a verdict.
    assert result["total_score"] == pytest.approx(10.0)
    assert result["reliable"] is False
    assert result["bucket"] == company_scorer.NO_DATA_BUCKET
    assert result["risk_analysis"]["controversy_risk_score"] is None


def test_asset_with_no_data_has_no_score():
    result = score_company("X", {})

    assert result["total_score"] is None
    assert result["bucket"] == company_scorer.NO_DATA_BUCKET
    assert result["data_coverage"] == 0.0


def test_controversy_penalty_is_capped_at_five_points():
    assert company_scorer.sustainability_score(9.0, 10.0) == pytest.approx(4.0)
    assert company_scorer.sustainability_score(2.0, 10.0) == 0.0


def test_sector_band_changes_the_score():
    # 15% ROE: middle of the Default band, a sixth of the way up for Technology.
    assert normalize(0.15, **sector_config.get_norm_params("Default", "return_on_equity")) == pytest.approx(5.0)
    assert normalize(0.15, **sector_config.get_norm_params("Technology", "return_on_equity")) == pytest.approx(
        10 * 0.05 / 0.30
    )


def test_sector_without_bands_keeps_its_name_and_uses_default_bands():
    data = {"sector": "Consumer Defensive", "industry": "Beverages", "return_on_equity": 0.15}
    result = score_company("KO", data)

    assert result["sector"] == "Consumer Defensive"
    assert result["sector_band"] == "Default"
    assert result["components"]["P"]["score"] == pytest.approx(5.0)

    semis = score_company("NVDA", {"sector": "Technology", "industry": "Semiconductors"})
    assert semis["sector_band"] == "Semiconductors"


def test_sector_resolution():
    assert sector_config.resolve_sector("technology") == "Technology"
    assert sector_config.resolve_sector("Technology", "Semiconductors") == "Semiconductors"
    assert sector_config.resolve_sector("Software") == "Default"
    assert sector_config.resolve_sector(None) == "Default"
    # A sector without its own band for a metric borrows the Default one.
    assert sector_config.get_norm_params("Semiconductors", "debt_to_equity") == sector_config.get_norm_params(
        "Default", "debt_to_equity"
    )
