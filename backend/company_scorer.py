"""PARKS scoring: maps heterogeneous metrics onto a single 0-10 scale.

    P  Profitability   ROE, net margin
    A  Acceleration    revenue growth
    R  Resilience      volatility, D/E, beta
    K  Knowledge       governance and innovation (LLM)
    S  Sustainability  ESG profile less a controversy penalty (LLM)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

import sector_config


def normalize(
    value: Optional[float],
    min_val: float,
    max_val: float,
    invert: bool = False,
) -> Optional[float]:
    """Map a metric onto a 0-10 scale.

    Returns None when there is no data. Callers must drop the metric from the
    average rather than substituting zero: "unknown" is not "worst in class".
    """
    if value is None:
        return None

    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN
        return None

    # Degenerate band in the config: return mid-scale instead of dividing by zero.
    if max_val == min_val:
        return 5.0

    if invert:
        score = (max_val - value) / (max_val - min_val)
    else:
        score = (value - min_val) / (max_val - min_val)

    # Clamp so values outside the band saturate rather than blow up.
    return float(np.clip(score * 10, 0.0, 10.0))


def _average(values: List[Optional[float]], default: float = 5.0) -> tuple[float, int, int]:
    """Mean over the metrics we actually have.

    Returns (mean, covered, requested). With nothing covered we fall back to a
    neutral 5.0 and report zero coverage.
    """
    present = [v for v in values if v is not None]
    if not present:
        return default, 0, len(values)
    return float(np.mean(present)), len(present), len(values)


def assign_bucket(score: float) -> str:
    """Map a 0-10 score to an investment bucket."""
    if score >= 8.5:
        return "🔥 Core Investment (высочайшее качество)"
    if score >= 7.0:
        return "🟢 Strong Buy (высокое качество)"
    if score >= 5.5:
        return "🟡 Hold / Neutral (среднее качество)"
    if score >= 4.0:
        return "🟠 Underperform (низкое качество)"
    return "🔴 Avoid (критический риск)"


def _score_sustainability(esg_score: float, controversy_risk: float) -> Dict[str, Any]:
    """Base ESG score less a controversy penalty.

    Risk comes in on a 0-10 scale where 0 is safe. Halving it caps the penalty at
    5 points: a scandal can halve the score but not erase an objectively decent
    ESG profile.
    """
    penalty = controversy_risk / 2.0
    final = float(np.clip(esg_score - penalty, 0.0, 10.0))
    return {
        "score": final,
        "details": f"База ESG: {esg_score:.1f} − штраф за риск: {penalty:.1f} (риск {controversy_risk:.1f}/10)",
    }


def score_company(ticker: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Score an asset. Takes the dict produced by data_fetcher.fetch_company_data."""
    sector = data.get("sector") or "Default"
    components: Dict[str, Dict[str, Any]] = {}
    covered_total = 0
    requested_total = 0

    # P: profitability
    roe = normalize(data.get("return_on_equity"), **sector_config.get_norm_params(sector, "return_on_equity"))
    margin = normalize(data.get("profit_margins"), **sector_config.get_norm_params(sector, "profit_margins"))
    p_score, cov, req = _average([roe, margin])
    covered_total, requested_total = covered_total + cov, requested_total + req
    components["P"] = {
        "name": "Profitability",
        "score": p_score,
        "coverage": f"{cov}/{req}",
        "details": f"ROE: {_fmt(roe)}, маржа: {_fmt(margin)}",
    }

    # A: growth
    growth = normalize(data.get("revenue_growth"), **sector_config.get_norm_params(sector, "revenue_growth"))
    a_score, cov, req = _average([growth])
    covered_total, requested_total = covered_total + cov, requested_total + req
    components["A"] = {
        "name": "Acceleration",
        "score": a_score,
        "coverage": f"{cov}/{req}",
        "details": f"Рост выручки: {_fmt(growth)}",
    }

    # R: resilience
    vol = normalize(data.get("volatility_1y"), **sector_config.get_norm_params(sector, "volatility_1y"))
    d2e = normalize(data.get("debt_to_equity"), **sector_config.get_norm_params(sector, "debt_to_equity"))
    beta = normalize(data.get("beta"), **sector_config.get_norm_params(sector, "beta"))
    r_score, cov, req = _average([vol, d2e, beta])
    covered_total, requested_total = covered_total + cov, requested_total + req
    components["R"] = {
        "name": "Resilience",
        "score": r_score,
        "coverage": f"{cov}/{req}",
        "details": f"Волатильность: {_fmt(vol)}, D/E: {_fmt(d2e)}, бета: {_fmt(beta)}",
    }

    # K and S come from the LLM already on a 0-10 scale, so they skip
    # sector_config normalisation.
    ai = data.get("ai_analysis") or {}
    governance = float(ai.get("governance_score", 5.0))
    innovation = float(ai.get("innovation_score", 5.0))
    esg = float(ai.get("esg_news_score", 5.0))
    controversy = float(ai.get("controversy_risk_score", 3.0))
    llm_available = bool(ai.get("llm_available", False))

    components["K"] = {
        "name": "Knowledge",
        "score": float(np.mean([governance, innovation])),
        "coverage": "LLM" if llm_available else "n/a",
        "details": f"Governance: {governance:.1f}, инновации: {innovation:.1f}",
        "reasoning": ai.get("governance_reasoning", ""),
    }

    s_block = _score_sustainability(esg, controversy)
    components["S"] = {
        "name": "Sustainability",
        "score": s_block["score"],
        "coverage": "LLM" if llm_available else "n/a",
        "details": s_block["details"],
        "reasoning": ai.get("esg_reasoning", ""),
    }

    total = float(np.mean([components[k]["score"] for k in ("P", "A", "R", "K", "S")]))

    # Share of quantitative metrics actually filled. A score built on 2 of 6 is a
    # guess, and whoever reads it should be able to tell.
    coverage_ratio = covered_total / requested_total if requested_total else 0.0

    return {
        "ticker": ticker,
        "name": data.get("name", ticker),
        "sector": sector,
        "asset_type": data.get("asset_type", "unknown"),
        "components": components,
        "total_score": total,
        "bucket": assign_bucket(total),
        "data_coverage": round(coverage_ratio, 2),
        "llm_available": llm_available,
        "risk_analysis": {
            "controversy_risk_score": controversy,
            "reasoning": ai.get("risk_reasoning", ""),
        },
    }


def _fmt(value: Optional[float]) -> str:
    """Show a missing metric as such instead of a silent zero."""
    return "н/д" if value is None else f"{value:.1f}"
