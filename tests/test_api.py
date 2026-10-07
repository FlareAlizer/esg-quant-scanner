"""HTTP layer with scoring and the model stubbed."""

import pytest
from fastapi.testclient import TestClient

import api
import company_scorer

PROFILE = {
    "ticker": "ACME", "name": "Acme Corp", "sector": None, "asset_type": "stock",
    "return_on_equity": 0.15, "profit_margins": 0.30, "revenue_growth": 0.125,
    "volatility_1y": 0.15, "debt_to_equity": 110.0, "beta": 1.5,
    "ai_analysis": {"llm_available": False},
}


@pytest.fixture
def client(monkeypatch):
    calls = []

    def fetch(ticker):
        calls.append(ticker)
        if ticker == "NOPE":
            return {"ticker": ticker, "name": ticker, "volatility_1y": None, "ai_analysis": {}}
        return dict(PROFILE, ticker=ticker)

    monkeypatch.setattr(api.data_fetcher, "fetch_company_data", fetch)
    monkeypatch.setattr(api, "_scores", {})
    test_client = TestClient(api.app)
    test_client.fetch_calls = calls
    return test_client


def test_health_reports_llm_state(client):
    assert client.get("/api/v1/health").json() == {"status": "ok", "llm_enabled": False}


def test_score_is_json_serialisable_and_cached(client):
    first = client.get("/api/v1/score/acme")
    second = client.get("/api/v1/score/ACME")

    assert first.status_code == 200
    body = first.json()
    assert body["ticker"] == "ACME"
    assert body["total_score"] == pytest.approx((7.5 + 5.0 + 5.0) / 3)
    assert body["components"]["K"]["score"] is None
    assert second.json() == body
    assert client.fetch_calls == ["ACME"]


def test_unknown_ticker_is_404(client):
    response = client.get("/api/v1/score/NOPE")

    assert response.status_code == 404
    assert "NOPE" in response.json()["detail"]


@pytest.mark.parametrize("ticker", ["A B", "DROP;TABLE", "X" * 16, "%3Cscript%3E"])
def test_malformed_ticker_is_rejected_before_any_lookup(client, ticker):
    assert client.get(f"/api/v1/score/{ticker}").status_code == 422
    assert client.fetch_calls == []


def test_assistant_without_a_key_is_503(client):
    response = client.post("/api/v1/assistant", json={"ticker": "ACME", "question": "Why?"})

    assert response.status_code == 503
    assert "LLM_API_KEY" in response.json()["detail"]


def test_assistant_builds_the_profile_on_the_server(client, monkeypatch):
    seen = {}

    def answer(profile, question):
        seen.update(profile=profile, question=question)
        return "ответ"

    monkeypatch.setattr(api.llm_analyzer, "is_enabled", lambda: True)
    monkeypatch.setattr(api.llm_analyzer, "answer_question", answer)

    response = client.post("/api/v1/assistant", json={"ticker": "acme", "question": "  Why?  "})

    assert response.json() == {"answer": "ответ"}
    assert seen["question"] == "Why?"
    assert '"ticker": "ACME"' in seen["profile"]
    assert company_scorer.NO_DATA_BUCKET not in seen["profile"]


def test_assistant_validates_its_input(client, monkeypatch):
    monkeypatch.setattr(api.llm_analyzer, "is_enabled", lambda: True)

    assert client.post("/api/v1/assistant", json={"ticker": "ACME", "question": ""}).status_code == 422
    assert client.post("/api/v1/assistant", json={"ticker": "ACME", "question": "x" * 501}).status_code == 422
    assert client.post("/api/v1/assistant", json={"question": "Why?"}).status_code == 422


def test_silent_model_is_502(client, monkeypatch):
    monkeypatch.setattr(api.llm_analyzer, "is_enabled", lambda: True)
    monkeypatch.setattr(api.llm_analyzer, "answer_question", lambda profile, question: None)

    assert client.post("/api/v1/assistant", json={"ticker": "ACME", "question": "Why?"}).status_code == 502
