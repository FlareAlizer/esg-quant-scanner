"""HTTP API for the frontend.

    uvicorn api:app --app-dir backend --port 8000

The LLM key stays on this side: the browser sends a ticker and a question, the
profile the model sees is built here. There is no auth and no rate limit, so
keep it on localhost.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import company_scorer
import data_fetcher
import llm_analyzer

logger = logging.getLogger(__name__)

app = FastAPI(title="ESG Quant Scanner", version="1.0.0")

# Yahoo symbols: letters, digits, and . - = ^ (BRK-B, BHARTIARTL.NS, ^GSPC).
_TICKER_RE = re.compile(r"[A-Z0-9.\-=^]{1,15}")

# Scoring one asset costs several network calls; keep the result for the
# lifetime of the process.
_CACHE_SIZE = 256
_scores: dict[str, dict[str, Any]] = {}


class Question(BaseModel):
    ticker: str = Field(min_length=1, max_length=15)
    question: str = Field(min_length=1, max_length=500)


def _score(raw_ticker: str) -> dict[str, Any]:
    ticker = raw_ticker.strip().upper()
    if not _TICKER_RE.fullmatch(ticker):
        raise HTTPException(status_code=422, detail="Некорректный тикер.")

    if ticker in _scores:
        return _scores[ticker]

    data = data_fetcher.fetch_company_data(ticker)
    # No price history and no profile: Yahoo doesn't know the symbol.
    if data["volatility_1y"] is None and data["name"] == ticker:
        raise HTTPException(status_code=404, detail=f"Тикер {ticker} не найден.")

    if len(_scores) >= _CACHE_SIZE:
        _scores.pop(next(iter(_scores)))
    _scores[ticker] = company_scorer.score_company(ticker, data)
    return _scores[ticker]


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "llm_enabled": llm_analyzer.is_enabled()}


@app.get("/api/v1/score/{ticker}")
def score(ticker: str) -> dict[str, Any]:
    """PARKS score for one asset, as returned by company_scorer.score_company."""
    return _score(ticker)


@app.post("/api/v1/assistant")
def assistant(body: Question) -> dict[str, str]:
    """Answer a question about one scored asset from its profile."""
    if not llm_analyzer.is_enabled():
        raise HTTPException(status_code=503, detail="На сервере не задан LLM_API_KEY: ассистент отключён.")

    profile = json.dumps(_score(body.ticker), ensure_ascii=False, indent=1)
    answer = llm_analyzer.answer_question(profile, body.question.strip())
    if not answer:
        raise HTTPException(status_code=502, detail="Модель не ответила. Попробуйте ещё раз.")
    return {"answer": answer}
