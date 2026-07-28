"""Entry point: score assets, build a portfolio, stress it with Monte Carlo."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List

import company_scorer
import config
import data_fetcher
import monte_carlo
import portfolio_optimizer
import visualizer

# Default universe. Override with --tickers or --tickers-file.
DEFAULT_TICKERS: List[str] = [
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


def load_tickers(args: argparse.Namespace) -> List[str]:
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


def score_universe(tickers: List[str]) -> List[str]:
    """Score everything and return what worked. One bad ticker shouldn't kill the run."""
    log = logging.getLogger("pipeline")
    valid: List[str] = []

    print(f"\n🧐 ШАГ 1: скоринг PARKS ({len(tickers)} активов)")
    print("=" * 62)

    for ticker in tickers:
        try:
            data = data_fetcher.fetch_company_data(ticker)
            if not data:
                log.warning("Нет данных для %s — пропуск", ticker)
                continue

            score = company_scorer.score_company(ticker, data)
            portfolio_optimizer.preload_score_cache(ticker, score)
            valid.append(ticker)

            coverage = score["data_coverage"]
            flag = "" if coverage >= 0.5 else "  ⚠️ мало данных"
            print(
                f"  {ticker:<14} {score['total_score']:5.2f}/10  "
                f"[покрытие {coverage:.0%}]  {score['bucket']}{flag}"
            )
        except Exception as exc:
            log.error("Ошибка обработки %s: %s", ticker, exc)

    return valid


def run_pipeline(args: argparse.Namespace) -> int:
    """The pipeline. Returns a process exit code."""
    tickers = load_tickers(args)
    print(f"\n🚀 ЗАПУСК СТРАТЕГИИ — активов в пуле: {len(tickers)}")

    valid_tickers = score_universe(tickers)
    if len(valid_tickers) < 2:
        print("\n❌ Оценить удалось менее двух активов — оптимизация невозможна.")
        return 1

    print(f"\n🧠 ШАГ 2: оптимизация (цель {args.target_return:.0%})")
    print("=" * 62)

    portfolio = None
    # Step the target down if it's unreachable, rather than retrying it verbatim.
    for target in (args.target_return, args.target_return * 0.85, args.target_return * 0.7):
        result = portfolio_optimizer.optimize_mean_variance(
            valid_tickers,
            target_return=target,
            max_weight=args.max_weight,
            min_weight=args.min_weight,
        )
        if "error" not in result:
            portfolio = result
            break
        print(f"  ⚠️ {result['error']} (цель {target:.1%}) — понижаем планку")

    if portfolio is None:
        print("\n❌ Не удалось построить портфель даже при пониженных требованиях.")
        return 1

    weights = portfolio["optimized_weights_pct"]
    ret = portfolio["achieved_portfolio_return"]
    vol = portfolio["expected_portfolio_volatility"]

    print(f"\n💼 ИТОГОВЫЙ ПОРТФЕЛЬ: доходность {ret:.2%} | волатильность {vol:.2%}")

    # If the solver had to relax the bounds, say so. Asking for 25% max per asset
    # and silently getting 77% is worse than no answer.
    requested = portfolio.get("requested_bounds")
    applied = portfolio.get("applied_bounds")
    if requested and applied and requested != applied:
        print(
            f"  ⚠️ Ограничения на веса ослаблены: запрошено "
            f"{requested[0]:.0%}-{requested[1]:.0%}, применено {applied[0]:.0%}-{applied[1]:.0%} "
            f"(на {len(valid_tickers)} активах исходные границы несовместимы с суммой 100%)."
        )
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
        mu_annual=ret,
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
    parser.add_argument("--target-return", type=float, default=0.14, help="Целевая доходность (0.14 = 14%%)")
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
