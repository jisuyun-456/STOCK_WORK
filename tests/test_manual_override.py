"""tests/test_manual_override.py — research.manual_override 단위/통합 테스트.

모든 파일 I/O는 tmp_path로 격리. 외부 에이전트/캐시 호출은 MagicMock으로 차단.
pytest tests/test_manual_override.py -v
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from research.manual_override import (
    OVERRIDE_PATH,
    clear_expired,
    invalidate,
    list_active,
    load_manual_verdicts,
    save_manual_verdicts,
)
from research.models import ResearchVerdict
from strategies.base_strategy import Direction, Signal


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_verdict(agent: str = "equity_research", symbol: str = "AAPL") -> ResearchVerdict:
    return ResearchVerdict(
        agent=agent,
        symbol=symbol,
        direction="AGREE",
        confidence_delta=0.05,
        conviction="MODERATE",
        reasoning="Test reasoning",
        key_metrics={"test": True},
        override_vote=None,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def _make_signal(
    symbol: str = "AAPL",
    strategy: str = "MOM",
    direction: Direction = Direction.BUY,
    confidence: float = 0.6,
) -> Signal:
    return Signal(
        strategy=strategy,
        symbol=symbol,
        direction=direction,
        weight_pct=0.1,
        confidence=confidence,
        reason="Test signal",
    )


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolate_override_path(tmp_path, monkeypatch):
    """각 테스트마다 OVERRIDE_PATH를 tmp_path의 임시 파일로 교체."""
    fake_path = tmp_path / "manual_verdicts.json"
    monkeypatch.setattr("research.manual_override.OVERRIDE_PATH", fake_path)
    return fake_path


# ─── 기본 저장/로드 ─────────────────────────────────────────────────────────


def test_save_and_load_roundtrip():
    """save 후 load → 동일한 verdicts 리스트 반환."""
    verdicts = [_make_verdict("equity_research"), _make_verdict("technical_strategist")]
    save_manual_verdicts("AAPL", "MOM", "buy", verdicts)

    loaded = load_manual_verdicts("AAPL", "MOM", "buy")
    assert loaded is not None
    assert len(loaded) == 2
    assert loaded[0].agent == "equity_research"
    assert loaded[1].agent == "technical_strategist"
    assert loaded[0].symbol == "AAPL"
    assert loaded[0].confidence_delta == pytest.approx(0.05)


def test_key_uppercase_normalization():
    """save('nvda', 'mom', 'buy') 후 load('NVDA', 'MOM', 'buy') 성공."""
    verdicts = [_make_verdict(symbol="NVDA")]
    save_manual_verdicts("nvda", "mom", "buy", verdicts)

    loaded = load_manual_verdicts("NVDA", "MOM", "buy")
    assert loaded is not None
    assert len(loaded) == 1


def test_direction_case_normalization():
    """save(..., 'BUY') 후 load(..., 'buy') 성공 (키 정규화)."""
    verdicts = [_make_verdict()]
    save_manual_verdicts("AAPL", "MOM", "BUY", verdicts)

    loaded = load_manual_verdicts("AAPL", "MOM", "buy")
    assert loaded is not None
    assert len(loaded) == 1


def test_load_missing_returns_none():
    """존재하지 않는 키 → None."""
    result = load_manual_verdicts("TSLA", "VAL", "sell")
    assert result is None


def test_overwrite_same_key():
    """동일 키로 두 번 save → 두 번째 값으로 덮어쓰기."""
    first = [_make_verdict("equity_research")]
    second = [_make_verdict("macro_economist"), _make_verdict("risk_controller")]

    save_manual_verdicts("MSFT", "QNT", "buy", first)
    save_manual_verdicts("MSFT", "QNT", "buy", second)

    loaded = load_manual_verdicts("MSFT", "QNT", "buy")
    assert loaded is not None
    assert len(loaded) == 2
    assert loaded[0].agent == "macro_economist"


# ─── TTL / 만료 ─────────────────────────────────────────────────────────────


def test_ttl_expiration(tmp_path, monkeypatch):
    """expires_at을 과거로 조작 → load returns None."""
    fake_path = tmp_path / "manual_verdicts.json"
    monkeypatch.setattr("research.manual_override.OVERRIDE_PATH", fake_path)

    verdicts = [_make_verdict()]
    save_manual_verdicts("AAPL", "MOM", "buy", verdicts)

    # expires_at을 과거로 직접 조작
    data = json.loads(fake_path.read_text(encoding="utf-8"))
    past = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    data["AAPL:MOM:buy"]["expires_at"] = past
    fake_path.write_text(json.dumps(data), encoding="utf-8")

    result = load_manual_verdicts("AAPL", "MOM", "buy")
    assert result is None


def test_list_active_excludes_expired(tmp_path, monkeypatch):
    """list_active()는 만료된 항목을 제외한다."""
    fake_path = tmp_path / "manual_verdicts.json"
    monkeypatch.setattr("research.manual_override.OVERRIDE_PATH", fake_path)

    # 유효한 항목
    save_manual_verdicts("AAPL", "MOM", "buy", [_make_verdict()])
    # 만료 항목 직접 삽입
    data = json.loads(fake_path.read_text(encoding="utf-8"))
    past = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    data["TSLA:LEV:sell"] = {
        "saved_at": past,
        "expires_at": past,
        "symbol": "TSLA",
        "strategy": "LEV",
        "direction": "sell",
        "verdicts": [],
        "source": "manual_claude_code_agents",
    }
    fake_path.write_text(json.dumps(data), encoding="utf-8")

    active = list_active()
    keys = [item["key"] for item in active]
    assert "AAPL:MOM:buy" in keys
    assert "TSLA:LEV:sell" not in keys


def test_clear_expired_returns_count(tmp_path, monkeypatch):
    """만료 2개 있으면 clear_expired() → 2 반환."""
    fake_path = tmp_path / "manual_verdicts.json"
    monkeypatch.setattr("research.manual_override.OVERRIDE_PATH", fake_path)

    # 유효 1개
    save_manual_verdicts("AAPL", "MOM", "buy", [_make_verdict()])

    # 만료 2개 직접 삽입
    data = json.loads(fake_path.read_text(encoding="utf-8"))
    past = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    for key, sym, strat, dirn in [
        ("TSLA:LEV:sell", "TSLA", "LEV", "sell"),
        ("NVDA:QNT:buy", "NVDA", "QNT", "buy"),
    ]:
        data[key] = {
            "saved_at": past,
            "expires_at": past,
            "symbol": sym,
            "strategy": strat,
            "direction": dirn,
            "verdicts": [],
            "source": "manual_claude_code_agents",
        }
    fake_path.write_text(json.dumps(data), encoding="utf-8")

    removed = clear_expired()
    assert removed == 2

    # 유효 항목은 여전히 남아있어야 함
    remaining = load_manual_verdicts("AAPL", "MOM", "buy")
    assert remaining is not None


# ─── 에러 처리 ────────────────────────────────────────────────────────────────


def test_corrupted_json_graceful(tmp_path, monkeypatch):
    """OVERRIDE_PATH에 깨진 JSON 쓰고 load_manual_verdicts 호출 → None (에러 없이)."""
    fake_path = tmp_path / "manual_verdicts.json"
    monkeypatch.setattr("research.manual_override.OVERRIDE_PATH", fake_path)

    fake_path.write_text("{broken json<<<", encoding="utf-8")

    result = load_manual_verdicts("AAPL", "MOM", "buy")
    assert result is None


# ─── invalidate ──────────────────────────────────────────────────────────────


def test_invalidate():
    """invalidate 후 load → None. 없는 키 invalidate → False."""
    verdicts = [_make_verdict()]
    save_manual_verdicts("GOOG", "VAL", "buy", verdicts)

    # 있는 키 → True, 로드 안됨
    result = invalidate("GOOG", "VAL", "buy")
    assert result is True
    assert load_manual_verdicts("GOOG", "VAL", "buy") is None

    # 없는 키 → False
    result2 = invalidate("GOOG", "VAL", "buy")
    assert result2 is False


# ─── 통합 테스트 (overlay) ───────────────────────────────────────────────────


def test_overlay_manual_beats_cache(tmp_path, monkeypatch):
    """manual_verdicts에 항목 저장 후 run_research_overlay 호출 →
    _generate_verdicts가 호출되지 않았음을 확인 (MagicMock).
    """
    fake_path = tmp_path / "manual_verdicts.json"
    monkeypatch.setattr("research.manual_override.OVERRIDE_PATH", fake_path)

    # manual verdicts 저장 (AAPL / MOM / buy)
    manual_verdicts = [
        ResearchVerdict(
            agent="equity_research",
            symbol="AAPL",
            direction="AGREE",
            confidence_delta=0.1,
            conviction="STRONG",
            reasoning="Manual override — strong buy",
            key_metrics={},
            override_vote=None,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    ]
    save_manual_verdicts("AAPL", "MOM", "buy", manual_verdicts)

    signal = _make_signal("AAPL", "MOM", Direction.BUY, confidence=0.65)

    mock_generate = MagicMock(return_value=manual_verdicts)

    with patch("research.overlay._generate_verdicts", mock_generate), \
         patch("research.overlay.detect_regime") as mock_regime, \
         patch("research.overlay.get_cached", return_value=None), \
         patch("research.overlay.set_cache"), \
         patch("research.overlay.calculate_consensus", return_value=(0.7, {"regime": "BULL"})), \
         patch("research.overlay._log_dissent"):

        from research.models import RegimeDetection
        mock_regime.return_value = RegimeDetection(
            regime="BULL",
            sp500_vs_sma200=1.05,
            vix_level=15.0,
            reasoning="Test regime",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        from research.overlay import run_research_overlay
        adjusted, regime, verdicts_by_symbol = run_research_overlay(
            signals=[signal],
            market_data={"prices": {}},
            portfolio_state={},
            research_mode="full",
            no_cache=False,
        )

    # _generate_verdicts는 manual override가 있으므로 호출되지 않아야 함
    mock_generate.assert_not_called()
    # 시그널은 통과해야 함
    assert len(adjusted) == 1


def test_overlay_fallback_to_cache(tmp_path, monkeypatch):
    """manual_verdicts 없을 때 cache 경로 유지됨 확인.
    _generate_verdicts 미호출, get_cached 결과 사용.
    """
    fake_path = tmp_path / "manual_verdicts.json"
    monkeypatch.setattr("research.manual_override.OVERRIDE_PATH", fake_path)
    # manual verdicts 없음 (파일 비어있음)

    signal = _make_signal("NVDA", "MOM", Direction.BUY, confidence=0.6)

    cached_verdicts = [
        ResearchVerdict(
            agent="technical_strategist",
            symbol="NVDA",
            direction="AGREE",
            confidence_delta=0.08,
            conviction="MODERATE",
            reasoning="Cache hit",
            key_metrics={},
            override_vote=None,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    ]

    mock_generate = MagicMock(return_value=[])

    with patch("research.overlay._generate_verdicts", mock_generate), \
         patch("research.overlay.detect_regime") as mock_regime, \
         patch("research.overlay.get_cached", return_value=cached_verdicts), \
         patch("research.overlay.set_cache"), \
         patch("research.overlay.calculate_consensus", return_value=(0.68, {"regime": "NEUTRAL"})), \
         patch("research.overlay._log_dissent"):

        from research.models import RegimeDetection
        mock_regime.return_value = RegimeDetection(
            regime="NEUTRAL",
            sp500_vs_sma200=1.0,
            vix_level=20.0,
            reasoning="Test neutral",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        from research.overlay import run_research_overlay
        adjusted, regime, verdicts_by_symbol = run_research_overlay(
            signals=[signal],
            market_data={"prices": {}},
            portfolio_state={},
            research_mode="full",
            no_cache=False,
        )

    # manual이 없으므로 cache를 사용해야 함 → _generate_verdicts 미호출
    mock_generate.assert_not_called()
    # cache hit 이후 시그널 통과
    assert len(adjusted) == 1
    assert verdicts_by_symbol["NVDA"][0].agent == "technical_strategist"
