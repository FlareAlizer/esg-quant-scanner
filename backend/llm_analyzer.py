"""LLM agent: web search plus structured metric extraction.

Turns search snippets into validated JSON. Nothing that can be computed exactly
belongs here.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Any, Dict, List, Optional

from config import settings

logger = logging.getLogger(__name__)

# Built on first use rather than at import, so tests and linters don't need a key.
_client = None


def _get_client():
    global _client
    if _client is None:
        if not settings.llm_enabled:
            return None
        from openai import OpenAI  # local import: the package is optional

        _client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_s,
        )
    return _client


def _load_ddgs():
    """Return the DDGS class, or None if no search package is installed.

    duckduckgo_search was renamed to ddgs. The shim left behind under the old
    name doesn't raise, it just returns an empty result set, so callers read
    "search is broken" as "nothing found". Prefer the current package.
    """
    try:
        from ddgs import DDGS

        return DDGS
    except ImportError:
        pass

    try:
        from duckduckgo_search import DDGS

        logger.warning(
            "Установлен устаревший duckduckgo_search: он возвращает пустую выдачу. "
            "Выполните `pip install ddgs`."
        )
        return DDGS
    except ImportError:
        logger.warning("Пакет ddgs не установлен — поиск отключён")
        return None


def search_web(query: str, max_results: int = 5, attempts: int = 3) -> str:
    """Search and flatten the snippets into one string.

    DDG throttles hard, so the backoff is jittered rather than fixed. Parallel
    runs then don't sync up and hit the rate limit together.
    """
    ddgs_cls = _load_ddgs()
    if ddgs_cls is None:
        return ""

    logger.debug("Поиск: %s", query)

    for attempt in range(attempts):
        try:
            with ddgs_cls() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))

            if results:
                return "\n".join(
                    f"TITLE: {r.get('title', '')}\n"
                    f"SNIPPET: {r.get('body', '')}\n"
                    f"SOURCE: {r.get('href', '')}\n{'-' * 30}"
                    for r in results
                )
        except Exception as exc:
            logger.warning("Сбой поиска (попытка %d/%d): %s", attempt + 1, attempts, exc)

        # No point sleeping after the final attempt.
        if attempt < attempts - 1:
            time.sleep((2**attempt) + random.uniform(0.5, 1.5))

    return ""


def _call_llm(messages: List[Dict[str, str]], temperature: float = 0.2) -> Optional[str]:
    """Chat completion with retries. Returns the raw text or None."""
    client = _get_client()
    if client is None:
        logger.warning("LLM_API_KEY не задан — пропускаем вызов модели")
        return None

    for attempt in range(settings.llm_max_retries):
        try:
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
                max_tokens=2500,
            )
            return response.choices[0].message.content
        except Exception as exc:
            logger.warning(
                "Ошибка LLM API (попытка %d/%d): %s", attempt + 1, settings.llm_max_retries, exc
            )
            if attempt < settings.llm_max_retries - 1:
                time.sleep(2**attempt)

    return None


def safe_json_parse(text: Optional[str]) -> Dict[str, Any]:
    """Pull JSON out of a model response.

    Reasoning models wrap their chain of thought in <think>, and most models like
    to add markdown fences. Strip both.
    """
    if not text:
        return {}

    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Take the contents of the first fenced block, if any.
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL)
    if fence:
        cleaned = fence.group(1)

    try:
        parsed = json.loads(cleaned.strip())
    except json.JSONDecodeError as exc:
        logger.warning("Не удалось разобрать JSON от LLM: %s | текст: %.200s", exc, cleaned)
        return {}

    return parsed if isinstance(parsed, dict) else {}


def _clamp_score(value: Any, default: float = 5.0) -> float:
    """Clamp an LLM score into 0..10."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    if num != num:  # NaN
        return default
    return max(0.0, min(10.0, num))


def _as_fraction(value: Any) -> Optional[float]:
    """Convert percentages to fractions.

    The model regularly returns 20 where 0.20 was asked for. For ROE and margin,
    anything above 1.5 in absolute value is almost certainly a percentage.
    """
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num != num:
        return None
    return num / 100.0 if abs(num) > 1.5 else num


def detect_asset_type(ticker: str, context: str = "") -> str:
    """Classify as etf, bond, stock or unknown.

    Yahoo's quoteType first, because it is a fact rather than a guess. The text
    heuristic is a fallback and matches on word boundaries so that
    "fundamentals" doesn't register as "fund".
    """
    try:
        import yfinance as yf

        quote_type = (yf.Ticker(ticker).info or {}).get("quoteType", "")
        if quote_type:
            quote_type = quote_type.lower()
            if quote_type == "etf":
                return "etf"
            if quote_type in {"equity", "stock"}:
                return "stock"
            if quote_type == "bond":
                return "bond"
    except Exception as exc:
        logger.debug("quoteType недоступен для %s: %s", ticker, exc)

    lowered = context.lower()

    if re.search(r"\b(etf|exchange[- ]traded fund|index fund)\b", lowered):
        return "etf"
    if re.search(r"\b(treasury|bond fund|fixed income|yield to maturity)\b", lowered):
        return "bond"
    return "unknown"


_FUNDAMENTALS_SYSTEM_PROMPT = """\
You are a financial research agent. Extract or carefully ESTIMATE metrics.

RULES BY ASSET TYPE:
1. ETFs — no meaningful corporate debt: set debt = 0.0. Look for weighted
   average portfolio ROE; if absent, estimate from the sector of top holdings.
2. Bonds / treasury funds — ROE and margin are meaningless: return null for
   both, set roe to the yield to maturity, debt = 0.0, beta is typically 0.0-0.2.
3. Companies — use trailing twelve months (TTM) figures.

FORMAT RULES:
- Percentages MUST be decimals: 20% -> 0.20.
- "sector" must be specific ("Semiconductors", not "Tech").
- Use null when a value cannot be established or estimated. Do NOT invent.
- Output valid JSON only, no prose.
"""

_RISK_SYSTEM_PROMPT = """\
You assess investment risk from the supplied search snippets.
For an ETF, analyse the risk of the UNDERLYING sector rather than a single issuer.

Scoring convention (IMPORTANT):
- governance_score, esg_news_score, innovation_score: 0-10, HIGHER IS BETTER.
- controversy_risk_score: 0-10, LOWER IS SAFER.

All *_reasoning fields must be written in Russian, one or two sentences each.
Output valid JSON only.
"""


def fetch_fundamentals_from_web(ticker: str) -> Dict[str, Any]:
    """Look up fundamentals and normalise them.

    Missing values come back as None rather than 0, which the scorer relies on.
    """
    context = search_web(
        f"{ticker} stock financial ratios TTM ROE profit margin debt to equity beta sector",
        max_results=5,
    )
    asset_type = detect_asset_type(ticker, context)

    # Funds warrant a second, targeted query about holdings.
    if asset_type == "etf":
        logger.info("%s распознан как ETF — ищем характеристики портфеля", ticker)
        context += "\n=== ETF SPECIFIC ===\n" + search_web(
            f"{ticker} ETF fact sheet portfolio characteristics weighted average ROE top holdings",
            max_results=4,
        )

    user_prompt = (
        f"Ticker: {ticker}\nDetected asset type: {asset_type}\n\n"
        f"Search results:\n---\n{context}\n---\n\n"
        "Return exactly this JSON shape:\n"
        '{"name": String, "sector": String, "beta": Float|null, "roe": Float|null, '
        '"margin": Float|null, "growth": Float|null, "debt": Float|null}'
    )

    raw = _call_llm(
        [
            {"role": "system", "content": _FUNDAMENTALS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    parsed = safe_json_parse(raw)

    return {
        "name": parsed.get("name") or ticker,
        "sector": parsed.get("sector") or "Default",
        "asset_type": asset_type,
        # Beta and D/E aren't percentages.
        "beta": parsed.get("beta"),
        "debt": parsed.get("debt"),
        # These three often come back as percentages.
        "roe": _as_fraction(parsed.get("roe")),
        "margin": _as_fraction(parsed.get("margin")),
        "growth": _as_fraction(parsed.get("growth")),
    }


def analyze_governance_esg_risk(ticker: str) -> Dict[str, Any]:
    """Qualitative G/E/S and reputational risk.

    Always returns the full set of keys, falling back to neutral values when the
    LLM is unavailable, so callers don't have to null-check every field.
    """
    defaults: Dict[str, Any] = {
        "governance_score": 5.0, "governance_reasoning": "Нет данных",
        "esg_news_score": 5.0, "esg_reasoning": "Нет данных",
        "innovation_score": 5.0, "innovation_reasoning": "Нет данных",
        "controversy_risk_score": 3.0, "risk_reasoning": "Анализ не проводился",
        "llm_available": False,
    }

    context = search_web(f"{ticker} investment risks controversy ESG lawsuits outlook", max_results=4)
    if not context:
        return defaults

    raw = _call_llm(
        [
            {"role": "system", "content": _RISK_SYSTEM_PROMPT},
            {"role": "user", "content": f"Snippets:\n{context}\n\nJSON:"},
        ],
        temperature=0.3,
    )
    parsed = safe_json_parse(raw)
    if not parsed:
        return defaults

    merged = {**defaults, **parsed, "llm_available": True}

    # The model still returns 12 or -3 now and then.
    for key in ("governance_score", "esg_news_score", "innovation_score", "controversy_risk_score"):
        merged[key] = _clamp_score(merged[key], defaults[key])

    return merged
