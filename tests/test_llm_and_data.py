"""LLM paths with the model and the network mocked out."""

import dataclasses
import json
import logging
from types import SimpleNamespace

import pytest

import data_fetcher
import llm_analyzer

FAKE_KEY = "test-key-0000"


class FakeClient:
    """Stands in for openai.OpenAI: replays queued replies, records the calls."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **params):
        self.calls.append(params)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])


class ApiError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


@pytest.fixture
def llm(monkeypatch):
    """Enable the LLM with a fake key and a canned search result."""
    monkeypatch.setattr(llm_analyzer, "settings", dataclasses.replace(llm_analyzer.settings, llm_api_key=FAKE_KEY))
    monkeypatch.setattr(llm_analyzer, "_disabled", False)
    monkeypatch.setattr(llm_analyzer, "_json_mode", True)
    monkeypatch.setattr(llm_analyzer, "search_web", lambda *a, **k: "TITLE: t\nSNIPPET: s")

    def install(*replies):
        client = FakeClient(*replies)
        monkeypatch.setattr(llm_analyzer, "_client", client)
        return client

    return install


def test_without_a_key_nothing_is_searched_or_called(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("network must not be touched without a key")

    monkeypatch.setattr(llm_analyzer, "search_web", fail)

    assert llm_analyzer.is_enabled() is False
    assert llm_analyzer.fetch_fundamentals_from_web("MSFT") == {}
    assert llm_analyzer.analyze_governance_esg_risk("MSFT")["llm_available"] is False
    assert llm_analyzer.answer_question("profile", "question") is None


@pytest.mark.parametrize(
    "raw",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        '<think>the answer is {"a": 2}</think>\n{"a": 1}',
        'Here is the result: {"a": 1} Hope it helps.',
    ],
)
def test_json_is_extracted_from_noisy_answers(raw):
    assert llm_analyzer.safe_json_parse(raw) == {"a": 1}


@pytest.mark.parametrize("raw", [None, "", "no json here", "{broken", "[1, 2]"])
def test_unusable_answers_parse_to_empty(raw):
    assert llm_analyzer.safe_json_parse(raw) == {}


def test_fundamentals_units_are_converted_and_outliers_dropped(llm):
    llm(
        json.dumps(
            {
                "name": "Acme",
                "sector": "Technology",
                "beta": 1.2,
                "roe_pct": 160,              # 160% is a real ROE, not a typo
                "net_margin_pct": "25",
                "revenue_growth_pct": 99999,  # outside the plausible range
                "debt_to_equity_pct": 45,
            }
        )
    )
    result = llm_analyzer.fetch_fundamentals_from_web("ACME")

    assert result["return_on_equity"] == pytest.approx(1.6)
    assert result["profit_margins"] == pytest.approx(0.25)
    assert result["revenue_growth"] is None
    assert result["debt_to_equity"] == pytest.approx(45.0)
    assert result["beta"] == pytest.approx(1.2)


def test_risk_scores_are_clamped_and_text_is_bounded(llm):
    llm(
        json.dumps(
            {
                "governance_score": 12,
                "esg_news_score": -3,
                "innovation_score": "7.5",
                "controversy_risk_score": None,
                "risk_reasoning": "x" * 5000,
                "unexpected": "ignored",
            }
        )
    )
    result = llm_analyzer.analyze_governance_esg_risk("ACME")

    assert result["llm_available"] is True
    assert result["governance_score"] == 10.0
    assert result["esg_news_score"] == 0.0
    assert result["innovation_score"] == 7.5
    assert result["controversy_risk_score"] == 5.0
    assert len(result["risk_reasoning"]) == 600
    assert "unexpected" not in result


def test_answer_without_scores_counts_as_no_assessment(llm):
    llm('{"comment": "I cannot assess this"}')
    assert llm_analyzer.analyze_governance_esg_risk("ACME")["llm_available"] is False


def test_rejected_key_disables_the_model_and_is_not_logged(llm, caplog):
    client = llm(ApiError(401, f"Incorrect API key provided: {FAKE_KEY}"))

    with caplog.at_level(logging.DEBUG):
        assert llm_analyzer.analyze_governance_esg_risk("ACME")["llm_available"] is False
        assert llm_analyzer.fetch_fundamentals_from_web("ACME") == {}

    assert len(client.calls) == 1  # the second request was never sent
    assert llm_analyzer.is_enabled() is False
    assert FAKE_KEY not in caplog.text


def test_provider_error_text_is_redacted_in_the_log(llm, caplog):
    llm(ApiError(500, f"upstream failed for key {FAKE_KEY}"))

    with caplog.at_level(logging.DEBUG):
        assert llm_analyzer.fetch_fundamentals_from_web("ACME") == {}

    assert "upstream failed" in caplog.text
    assert FAKE_KEY not in caplog.text


def test_endpoint_without_json_mode_gets_a_plain_retry(llm):
    client = llm(ApiError(400, "response_format is not supported"), '{"governance_score": 6}')

    assert llm_analyzer.analyze_governance_esg_risk("ACME")["governance_score"] == 6.0
    assert "response_format" in client.calls[0]
    assert "response_format" not in client.calls[1]


def test_llm_only_fills_what_yahoo_left_empty(monkeypatch):
    yahoo = {
        "name": "Acme Corp", "sector": "Technology", "industry": "Software", "asset_type": "stock",
        "beta": 1.1, "return_on_equity": 0.30, "profit_margins": None,
        "revenue_growth": 0.10, "debt_to_equity": None,
    }
    web = {"return_on_equity": 0.99, "profit_margins": 0.20, "debt_to_equity": 50.0, "sector": "Utilities"}
    monkeypatch.setattr(data_fetcher, "fetch_yahoo_fundamentals", lambda t: dict(yahoo))
    monkeypatch.setattr(data_fetcher.llm_analyzer, "fetch_fundamentals_from_web", lambda t, kind: dict(web))
    monkeypatch.setattr(data_fetcher, "compute_annualized_volatility", lambda t: 0.25)

    data = data_fetcher.fetch_company_data(" acme ")

    assert data["ticker"] == "ACME"
    assert data["sector"] == "Technology"
    assert data["return_on_equity"] == 0.30      # Yahoo wins
    assert data["profit_margins"] == 0.20        # gap filled
    assert data["debt_to_equity"] == 50.0
    assert data["volatility_1y"] == 0.25
    assert data["ai_analysis"]["llm_available"] is False


def test_complete_yahoo_profile_skips_the_llm_lookup(monkeypatch):
    yahoo = dict.fromkeys(data_fetcher._YAHOO_FIELDS, 0.1) | {"name": "A", "sector": None, "asset_type": "stock"}

    def fail(*args):
        raise AssertionError("no gaps, the web lookup is not needed")

    monkeypatch.setattr(data_fetcher, "fetch_yahoo_fundamentals", lambda t: yahoo)
    monkeypatch.setattr(data_fetcher.llm_analyzer, "fetch_fundamentals_from_web", fail)
    monkeypatch.setattr(data_fetcher, "compute_annualized_volatility", lambda t: None)

    assert data_fetcher.fetch_company_data("A")["sector"] == "Default"
