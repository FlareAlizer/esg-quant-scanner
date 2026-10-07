"""Per-sector normalisation ranges.

15% ROE is strong for retail and mediocre for software, so metrics are scored
against sector bands rather than one absolute scale.

    "metric": {"min_val": X, "max_val": Y, "invert": bool}

invert=True means lower is better (debt, volatility, beta). Ratios are fractions
(0.15 = 15%), except debt_to_equity, which is in percent as Yahoo reports it
(45.0 = debt is 0.45 of equity).
"""

from __future__ import annotations

from typing import Any

SECTOR_NORMS: dict[str, dict[str, dict[str, Any]]] = {
    # Fallback when the sector is unknown or lacks a given metric.
    "Default": {
        "return_on_equity": {"min_val": 0.05, "max_val": 0.25, "invert": False},
        "profit_margins": {"min_val": 0.05, "max_val": 0.30, "invert": False},
        "revenue_growth": {"min_val": 0.05, "max_val": 0.20, "invert": False},
        "volatility_1y": {"min_val": 0.15, "max_val": 0.60, "invert": True},
        "debt_to_equity": {"min_val": 20.0, "max_val": 200.0, "invert": True},
        "beta": {"min_val": 0.8, "max_val": 1.5, "invert": True},
    },

    # Higher bar on ROE and growth, more tolerant of volatility, historically
    # less leverage.
    "Technology": {
        "return_on_equity": {"min_val": 0.10, "max_val": 0.40, "invert": False},
        "profit_margins": {"min_val": 0.10, "max_val": 0.40, "invert": False},
        "revenue_growth": {"min_val": 0.10, "max_val": 0.35, "invert": False},
        "volatility_1y": {"min_val": 0.20, "max_val": 0.70, "invert": True},
        "debt_to_equity": {"min_val": 10.0, "max_val": 150.0, "invert": True},
        "beta": {"min_val": 0.9, "max_val": 1.8, "invert": True},
    },

    # Same shape as Technology, but cyclicality widens the volatility band.
    "Semiconductors": {
        "return_on_equity": {"min_val": 0.10, "max_val": 0.40, "invert": False},
        "profit_margins": {"min_val": 0.10, "max_val": 0.45, "invert": False},
        "revenue_growth": {"min_val": 0.08, "max_val": 0.40, "invert": False},
        "volatility_1y": {"min_val": 0.25, "max_val": 0.80, "invert": True},
        "beta": {"min_val": 1.0, "max_val": 2.0, "invert": True},
    },

    # Thinner margins, more debt tolerated.
    "Consumer Cyclical": {
        "return_on_equity": {"min_val": 0.05, "max_val": 0.22, "invert": False},
        "profit_margins": {"min_val": 0.03, "max_val": 0.20, "invert": False},
        "revenue_growth": {"min_val": 0.03, "max_val": 0.18, "invert": False},
        "volatility_1y": {"min_val": 0.15, "max_val": 0.50, "invert": True},
        "debt_to_equity": {"min_val": 30.0, "max_val": 250.0, "invert": True},
        "beta": {"min_val": 0.7, "max_val": 1.4, "invert": True},
    },

    # Defensive sector, so we expect a low beta.
    "Healthcare": {
        "return_on_equity": {"min_val": 0.08, "max_val": 0.22, "invert": False},
        "profit_margins": {"min_val": 0.05, "max_val": 0.25, "invert": False},
        "revenue_growth": {"min_val": 0.05, "max_val": 0.20, "invert": False},
        "volatility_1y": {"min_val": 0.10, "max_val": 0.45, "invert": True},
        "debt_to_equity": {"min_val": 20.0, "max_val": 180.0, "invert": True},
        "beta": {"min_val": 0.6, "max_val": 1.2, "invert": True},
    },

    # Debt is part of the business model here, so the D/E band sits an order of
    # magnitude higher than for industrials.
    "Financial Services": {
        "return_on_equity": {"min_val": 0.08, "max_val": 0.20, "invert": False},
        "profit_margins": {"min_val": 0.10, "max_val": 0.35, "invert": False},
        "revenue_growth": {"min_val": 0.04, "max_val": 0.15, "invert": False},
        "debt_to_equity": {"min_val": 100.0, "max_val": 1000.0, "invert": True},
    },

    # Low growth and high debt are normal here, not a warning sign.
    "Utilities": {
        "return_on_equity": {"min_val": 0.04, "max_val": 0.15, "invert": False},
        "profit_margins": {"min_val": 0.05, "max_val": 0.25, "invert": False},
        "revenue_growth": {"min_val": 0.00, "max_val": 0.10, "invert": False},
        "volatility_1y": {"min_val": 0.10, "max_val": 0.40, "invert": True},
        "debt_to_equity": {"min_val": 80.0, "max_val": 300.0, "invert": True},
        "beta": {"min_val": 0.3, "max_val": 1.0, "invert": True},
    },
}


KNOWN_SECTORS = [name for name in SECTOR_NORMS if name != "Default"]


def resolve_sector(sector: str | None, industry: str | None = None) -> str:
    """Map a sector or industry label onto a key of SECTOR_NORMS.

    The names follow Yahoo's sector taxonomy, plus "Semiconductors", which Yahoo
    reports as an industry, so the industry is tried first. Anything else gets
    the Default band.
    """
    by_lower = {name.lower(): name for name in KNOWN_SECTORS}
    for label in (industry, sector):
        if isinstance(label, str) and label.strip().lower() in by_lower:
            return by_lower[label.strip().lower()]
    return "Default"


def get_norm_params(sector: str, metric: str) -> dict[str, Any]:
    """Normalisation params for a (sector, metric) pair.

    Falls back sector -> Default -> a neutral band. Hitting the last one means
    the metric isn't described anywhere and the config needs fixing.
    """
    sector_norms = SECTOR_NORMS.get(sector, SECTOR_NORMS["Default"])
    params = sector_norms.get(metric) or SECTOR_NORMS["Default"].get(metric)

    if params is None:
        return {"min_val": 0.0, "max_val": 1.0, "invert": False}

    # Copy: otherwise a caller can mutate the shared config through the reference.
    return dict(params)
