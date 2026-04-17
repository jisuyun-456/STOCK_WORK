"""Tests for kr_research.agent_runner — 4 tests (HIGH #1 fix verification)."""
import json
from unittest.mock import MagicMock, patch


def _make_regime(regime_type: str = "NEUTRAL"):
    from kr_research.models import KRRegime
    return KRRegime(
        regime=regime_type,
        confidence=0.7,
        factors={"vkospi": 20.0, "kospi_trend": 1.02},
    )


def test_claude_mode_actually_invokes_anthropic_client():
    """HIGH #1: run_claude must actually call client.messages.create (not a dead stub)."""
    from kr_research import agent_runner

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"verdict": "BUY", "confidence": 0.8, "rationale": "test"}')]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch.object(agent_runner, "_get_client", return_value=mock_client):
        regime = _make_regime("BULL")
        verdicts = agent_runner.run_claude(
            tickers=["005930"],
            regime=regime,
            market_snapshot={"date": "20260417"},
        )

    # CRITICAL: verify client.messages.create was actually called
    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args

    # Must use claude-sonnet-4-6 model
    assert call_kwargs[1].get("model") == "claude-sonnet-4-6" or \
           (call_kwargs[0] and call_kwargs[0][0] == "claude-sonnet-4-6"), \
        f"Expected model=claude-sonnet-4-6, got {call_kwargs}"

    # Must return verdicts list
    assert len(verdicts) == 1
    assert verdicts[0].ticker == "005930"
    assert verdicts[0].verdict == "BUY"
    assert verdicts[0].agent == "claude"


def test_run_rules_crisis_returns_sell_all():
    """run_rules with CRISIS regime must return SELL for all tickers."""
    from kr_research.agent_runner import run_rules

    regime = _make_regime("CRISIS")
    verdicts = run_rules(tickers=["005930", "000660", "035420"], regime=regime)

    assert len(verdicts) == 3
    for v in verdicts:
        assert v.verdict == "SELL", f"Expected SELL in CRISIS, got {v.verdict} for {v.ticker}"


def test_parse_verdict_valid_json():
    """_parse_verdict must correctly parse valid JSON response into KRVerdict."""
    from kr_research.agent_runner import _parse_verdict

    json_text = '{"verdict": "SELL", "confidence": 0.9, "rationale": "high risk"}'
    verdict = _parse_verdict("000660", json_text)

    assert verdict.ticker == "000660"
    assert verdict.verdict == "SELL"
    assert verdict.confidence == 0.9
    assert verdict.rationale == "high risk"
    assert verdict.agent == "claude"


def test_run_claude_handles_parse_error_gracefully():
    """run_claude must return HOLD verdict when Claude response is unparseable."""
    from kr_research import agent_runner

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="I cannot provide a JSON response at this time.")]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch.object(agent_runner, "_get_client", return_value=mock_client):
        regime = _make_regime("NEUTRAL")
        verdicts = agent_runner.run_claude(
            tickers=["035720"],
            regime=regime,
            market_snapshot={},
        )

    assert len(verdicts) == 1
    assert verdicts[0].verdict == "HOLD", f"Expected HOLD on parse error, got {verdicts[0].verdict}"
    assert verdicts[0].confidence == 0.3
    assert verdicts[0].ticker == "035720"
