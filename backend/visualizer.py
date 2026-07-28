"""Console bars and PNG charts for portfolio weights."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

import matplotlib

matplotlib.use("Agg")  # headless: no display on servers

import matplotlib.pyplot as plt  # noqa: E402  must come after use()
import numpy as np  # noqa: E402

logger = logging.getLogger(__name__)

_BACKGROUND = "#1e1e1e"


def draw_text_pie_chart(weights: Dict[str, float], title: str = "Allocation") -> None:
    """Horizontal bars in the console, for CI and SSH runs where nobody opens a PNG."""
    if not weights:
        print("⚠️  Нет весов для отображения.")
        return

    print(f"\n📊 {title}")
    print("=" * 62)

    bar_width = 40
    shades = ["█", "▓", "▒", "░"]

    for i, (ticker, pct) in enumerate(sorted(weights.items(), key=lambda kv: kv[1], reverse=True)):
        if pct < 0.1:
            continue
        # keep a 0.3% position visible
        length = max(1, int(pct / 100 * bar_width))
        bar = shades[i % len(shades)] * length
        print(f" {ticker:<9} |{bar:<{bar_width}}| {pct:5.1f}%")

    print("=" * 62)


def save_portfolio_chart(
    weights: Dict[str, float],
    filename: str | Path = "portfolio.png",
    title: str = "Portfolio Allocation",
    dpi: int = 200,
) -> Path | None:
    """Save a dark-theme pie chart. Returns the path, or None if there was nothing to draw."""
    items = [(k, v) for k, v in sorted(weights.items(), key=lambda kv: kv[1], reverse=True) if v > 0]
    if not items:
        logger.warning("Нет данных для графика")
        return None

    labels = [k for k, _ in items]
    sizes = [v for _, v in items]

    output = Path(filename)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Context manager rather than plt.style.use, which would leak the style into
    # every later figure in the process.
    with plt.style.context("dark_background"):
        fig, ax = plt.subplots(figsize=(11, 8))
        try:
            fig.patch.set_facecolor(_BACKGROUND)
            ax.set_facecolor(_BACKGROUND)

            colors = plt.get_cmap("tab20")(np.linspace(0, 1, len(sizes)))

            wedges, texts, autotexts = ax.pie(
                sizes,
                labels=labels,
                autopct="%1.1f%%",
                startangle=140,
                colors=colors,
                pctdistance=0.78,
                labeldistance=1.08,
                textprops={"color": "white"},
            )
            plt.setp(texts, size=10, weight="bold")
            plt.setp(autotexts, size=9, weight="bold")

            ax.set_title(title, fontsize=15, fontweight="bold", color="white", pad=18)
            ax.axis("equal")

            fig.savefig(output, dpi=dpi, facecolor=_BACKGROUND, bbox_inches="tight")
            logger.info("График сохранён: %s", output)
            return output
        except Exception as exc:
            logger.error("Ошибка при сохранении графика: %s", exc)
            return None
        finally:
            # Always close, otherwise figures pile up across batch runs.
            plt.close(fig)
