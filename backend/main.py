"""Entry point: score assets, build a portfolio, stress it with Monte Carlo."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

import company_scorer
import config
import data_fetcher
import monte_carlo
import portfolio_optimizer
import visualizer

# Default universe. Override with --tickers or --tickers-file.
DEFAULT_TICKERS: list[str] = [
    "SMH", "PAVE", "VHT",
    "SHY", "IEI",
    "BYDDY", "CAVA", "LULU", "AMZN",
    "SEIC", "V", "JPM", "KNSL",
    "DXCM", "ISRG", "VRTX", "AZN",
    "ORCL", "MSFT", "CRWD",
    "CAT", "HON",
    "WMT", "NSRGY", "KO",
    "TMUS", "BHARTIARTL.NS",
    "IBDRY", "SUZLON.NS", "CLPXY",
]


def force_utf8_output() -> None:
    """Force stdout and stderr to UTF-8.

    The report is full of emoji and Cyrillic. That works in an interactive
    Windows console, but the moment output goes to a pipe or a file Python falls
    back to the locale encoding (cp1251) and the first print kills the whole run
    with UnicodeEncodeError, after every network request has already been paid
    for. errors="replace" covers terminals missing the glyphs: a question mark
    beats an exception.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # stream closed or not text
                pass


def setup_logging(verbose: bool) -> None:
    """One log format across the project."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    # Noisy dependencies. primp is ddgs's HTTP engine and logs every single
    # request at INFO, which buries the scoring output.
    for noisy in ("yfinance", "urllib3", "peewee", "httpx", "primp", "ddgs", "openai", "matplotlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def load_tickers(args: argparse.Namespace) -> list[str]:
    """Tickers from argv, a file, or the default universe."""
    if args.tickers:
        return [t.strip().upper() for t in args.tickers if t.strip()]

    if args.tickers_file:
        path = Path(args.tickers_file)
        if not path.exists():
            raise SystemExit(f"Файл не найден: {path}")
        return [
            line.strip().upper()
            for line in path.read_text(encoding="utf-8").splitlines()
            # skip blanks and comments
            if line.strip() and not line.strip().startswith("#")
        ]

    return list(DEFAULT_TICKERS)


def score_universe(tickers: list[str]) -> list[str]:
    """Score everything and return what worked. One bad ticker shouldn't kill the run."""
    log = logging.getLogger("pipeline")
    valid: list[str] = []

    print(f"\n🧐 ШАГ 1: скоринг PARKS ({len(tickers)} активов)")
    print("=" * 62)

    for ticker in tickers:
        try:
            score = company_scorer.score_company(ticker, data_fetcher.fetch_company_data(ticker))
        except Exception as exc:  # noqa: BLE001  whatever a data source throws, move on
            log.error("Ошибка обработки %s: %s", ticker, exc)
            continue

        portfolio_optimizer.preload_score_cache(ticker, score)
        valid.append(ticker)

        total, coverage = score["total_score"], score["data_coverage"]
        shown = f"{total:5.2f}/10" if total is not None else "  н/д   "
        flag = "" if coverage >= 0.5 else "  ⚠️ мало данных"
        print(f"  {ticker:<14} {shown}  [покрытие {coverage:.0%}]  {score['bucket']}{flag}")

    return valid


def build_portfolio(tickers: list[str], args: argparse.Namespace) -> dict[str, Any]:
    """Run the optimiser picked by --objective. Weight bounds are never relaxed."""
    bounds = {"max_weight": args.max_weight, "min_weight": args.min_weight}

    if args.objective == "max-score":
        return portfolio_optimizer.optimize_by_score(
            tickers, volatility_threshold=args.max_volatility, **bounds
        )

    result = portfolio_optimizer.optimize_mean_variance(tickers, target_return=args.target_return, **bounds)

    # The target is out of reach for this pool under these caps. Fall back to the
    # best reachable return and say so, rather than loosening the caps.
    best = result.get("max_feasible_return")
    if best is not None:
        print(f"  ⚠️ {result['error']} Строим портфель под {best:.1%}.")
        result = portfolio_optimizer.optimize_mean_variance(tickers, target_return=best, **bounds)
    return result


def run_pipeline(args: argparse.Namespace) -> int:
    """The pipeline. Returns a process exit code."""
    tickers = load_tickers(args)
    print(f"\n🚀 ЗАПУСК СТРАТЕГИИ — активов в пуле: {len(tickers)}")
    if not config.settings.llm_enabled:
        print("ℹ️  LLM_API_KEY не задан: компоненты K и S не оцениваются, фундаментал берётся только из Yahoo.")

    valid_tickers = score_universe(tickers)
    if len(valid_tickers) < 2:
        print("\n❌ Оценить удалось менее двух активов — оптимизация невозможна.")
        return 1

    print("\n🧠 ШАГ 2: оптимизация")
    print("=" * 62)

    portfolio = build_portfolio(valid_tickers, args)
    if "error" in portfolio:
        print(f"\n❌ {portfolio['error']}")
        return 1

    weights = portfolio["optimized_weights_pct"]
    ret = portfolio["achieved_portfolio_return"]
    vol = portfolio["expected_portfolio_volatility"]

    print(f"\n💼 ИТОГОВЫЙ ПОРТФЕЛЬ: ожидаемая доходность {ret:.2%} | волатильность {vol:.2%}")
    if "expected_portfolio_score" in portfolio:
        print(f"   средневзвешенный PARKS: {portfolio['expected_portfolio_score']:.2f}/10")
    visualizer.draw_text_pie_chart(weights, "Распределение весов")

    chart_path = visualizer.save_portfolio_chart(
        weights,
        filename=args.output,
        title=f"Strategy: Return {ret:.1%} | Volatility {vol:.1%}",
    )
    if chart_path:
        print(f"🎨 График: {chart_path}")

    # GBM degenerates at zero volatility, which here means a degenerate
    # covariance (identical price histories, say). Worth saying out loud instead
    # of throwing a traceback on the very last step.
    if vol <= 0:
        print("\n❌ Волатильность портфеля равна нулю — данные вырождены, симуляция невозможна.")
        return 1

    print(f"\n🎲 ШАГ 3: Монте-Карло ({args.simulations:,} путей, {args.years} лет)")
    print("=" * 62)

    mc = monte_carlo.run_simulation(
        mu_annual=portfolio["expected_portfolio_drift"],
        vol_annual=vol,
        years=args.years,
        n_simulations=args.simulations,
        target_cagr=args.target_return,
    )
    monte_carlo.print_report(mc)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ESG Quant Scanner — скоринг активов и построение портфеля",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--tickers", nargs="+", help="Список тикеров через пробел")
    parser.add_argument("--tickers-file", help="Файл со списком тикеров (по одному в строке)")
    parser.add_argument(
        "--objective", choices=("min-risk", "max-score"), default="min-risk",
        help="min-risk: минимум риска при целевой доходности; max-score: максимум PARKS при лимите риска",
    )
    parser.add_argument("--target-return", type=float, default=0.14, help="Целевая доходность (0.14 = 14%%)")
    parser.add_argument("--max-volatility", type=float, default=0.20, help="Лимит риска для max-score")
    parser.add_argument("--max-weight", type=float, default=0.25, help="Максимальная доля одного актива")
    parser.add_argument("--min-weight", type=float, default=0.0, help="Минимальная доля актива")
    parser.add_argument("--years", type=int, default=5, help="Горизонт Монте-Карло, лет")
    parser.add_argument("--simulations", type=int, default=10_000, help="Число симуляций")
    parser.add_argument("--output", default="strategy_portfolio.png", help="Файл для графика")
    parser.add_argument("-v", "--verbose", action="store_true", help="Подробные логи")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    # Before setup_logging: the logger writes to stdout too.
    force_utf8_output()
    setup_logging(args.verbose)

    # Idempotent. config already ran this at import; calling it again just gets
    # the certificate path into the log now that logging is configured.
    ca_bundle = config.ensure_ca_bundle()
    if ca_bundle:
        logging.getLogger("pipeline").debug("Хранилище сертификатов: %s", ca_bundle)

    try:
        return run_pipeline(args)
    except KeyboardInterrupt:
        print("\n⏹️  Прервано пользователем.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
