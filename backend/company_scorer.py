"""PARKS scoring: maps heterogeneous metrics onto a single 0-10 scale.

    P  Profitability   ROE, net margin
    A  Acceleration    revenue growth
    R  Resilience      volatility, D/E, beta
    K  Knowledge       governance and innovation (LLM)
    S  Sustainability  ESG profile less a controversy penalty (LLM)

A metric with no data is left out of its component, and a component with no
data is left out of the total. The total is the plain mean of the components
that could be scored.
"""

from __future__ import annotations

from typing import Any

import numpy as np

import sector_config

COMPONENTS = ("P", "A", "R", "K", "S")
NO_DATA_BUCKET = "⚪ Недостаточно данных"
# A total built on fewer components than this is shown but gets no bucket and
# is not used to rank assets: one component is not a profile.
MIN_COMPONENTS = 3


def normalize(
    value: float | None,
    min_val: float,
    max_val: float,
    invert: bool = False,
) -> float | None:
    """Map a metric onto a 0-10 scale, linearly between the band edges.

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


def _mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return float(np.mean(present)) if present else None


def assign_bucket(score: float | None) -> str:
    """Map a 0-10 score to a bucket."""
    if score is None:
        return NO_DATA_BUCKET
    if score >= 8.5:
        return "🔥 Core Investment (высочайшее качество)"
    if score >= 7.0:
        return "🟢 Strong Buy (высокое качество)"
    if score >= 5.5:
        return "🟡 Hold / Neutral (среднее качество)"
    if score >= 4.0:
        return "🟠 Underperform (низкое качество)"
    return "🔴 Avoid (критический риск)"


def sustainability_score(esg_score: float, controversy_risk: float) -> float:
    """Base ESG score less a controversy penalty.

    Risk comes in on a 0-10 scale where 0 is safe. Halving it caps the penalty at
    5 points: a scandal can halve the score but not erase an objectively decent
    ESG profile.
    """
    return float(np.clip(esg_score - controversy_risk / 2.0, 0.0, 10.0))


def score_company(ticker: str, data: dict[str, Any]) -> dict[str, Any]:
    """Score an asset. Takes the dict produced by data_fetcher.fetch_company_data."""
    # A sector without its own bands ("Consumer Defensive", say) is still
    # reported under its name and scored on the Default ones.
    band = sector_config.resolve_sector(data.get("sector"), data.get("industry"))

    def scored(metric: str) -> float | None:
        return normalize(data.get(metric), **sector_config.get_norm_params(band, metric))

    components: dict[str, dict[str, Any]] = {}
    covered = requested = 0

    def quantitative(code: str, name: str, metrics: dict[str, str]) -> None:
        nonlocal covered, requested
        values = {label: scored(metric) for label, metric in metrics.items()}
        present = sum(v is not None for v in values.values())
        covered, requested = covered + present, requested + len(values)
        components[code] = {
            "name": name,
            "score": _mean(list(values.values())),
            "coverage": f"{present}/{len(values)}",
            "details": ", ".join(f"{label}: {_fmt(v)}" for label, v in values.items()),
        }

    quantitative("P", "Profitability", {"ROE": "return_on_equity", "маржа": "profit_margins"})
    quantitative("A", "Acceleration", {"Рост выручки": "revenue_growth"})
    quantitative(
        "R", "Resilience",
        {"Волатильность": "volatility_1y", "D/E": "debt_to_equity", "бета": "beta"},
    )

    # K and S come from the LLM already on a 0-10 scale, so they skip
    # sector_config normalisation. Without the model they are not scored at all:
    # a neutral placeholder would drag every total towards the middle.
    ai = data.get("ai_analysis") or {}
    llm_available = bool(ai.get("llm_available", False))
    controversy = float(ai.get("controversy_risk_score", 0.0)) if llm_available else None

    if llm_available:
        governance = float(ai.get("governance_score", 5.0))
        innovation = float(ai.get("innovation_score", 5.0))
        esg = float(ai.get("esg_news_score", 5.0))
        k_score: float | None = (governance + innovation) / 2.0
        s_score: float | None = sustainability_score(esg, controversy)
        k_details = f"Governance: {governance:.1f}, инновации: {innovation:.1f}"
        s_details = (
            f"База ESG: {esg:.1f} − штраф за риск: {controversy / 2.0:.1f} (риск {controversy:.1f}/10)"
        )
    else:
        k_score = s_score = None
        k_details = s_details = "LLM недоступен, компонент не оценивался"

    components["K"] = {
        "name": "Knowledge",
        "score": k_score,
        "coverage": "LLM" if llm_available else "n/a",
        "details": k_details,
        "reasoning": ai.get("governance_reasoning", "") if llm_available else "",
    }
    components["S"] = {
        "name": "Sustainability",
        "score": s_score,
        "coverage": "LLM" if llm_available else "n/a",
        "details": s_details,
        "reasoning": ai.get("esg_reasoning", "") if llm_available else "",
    }

    total = _mean([components[code]["score"] for code in COMPONENTS])
    reliable = sum(components[code]["score"] is not None for code in COMPONENTS) >= MIN_COMPONENTS

    return {
        "ticker": ticker,
        "name": data.get("name", ticker),
        "sector": data.get("sector") or None,
        "sector_band": band,
        "asset_type": data.get("asset_type", "unknown"),
        "components": components,
        # None when not a single component could be scored.
        "total_score": total,
        "reliable": reliable,
        "bucket": assign_bucket(total if reliable else None),
        # Share of the six quantitative metrics actually filled. A score built
        # on 2 of 6 is a guess, and whoever reads it should be able to tell.
        "data_coverage": round(covered / requested, 2) if requested else 0.0,
        "llm_available": llm_available,
        "risk_analysis": {
            "controversy_risk_score": controversy,
            "reasoning": ai.get("risk_reasoning", "") if llm_available else "",
        },
    }


def _fmt(value: float | None) -> str:
    """Show a missing metric as such instead of a silent zero."""
    return "н/д" if value is None else f"{value:.1f}"
