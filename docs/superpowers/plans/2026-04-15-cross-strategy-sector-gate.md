# Cross-Strategy Sector Concentration Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 단일 섹터가 전체 포트폴리오의 30%를 초과하지 못하도록 전략 간 교차 집중도 게이트를 추가하고, 전략별 섹터 한도도 강화한다.

**Architecture:** `risk_validator.py`에 `check_cross_strategy_concentration()` 함수를 추가하고, `run_cycle.py`의 `phase_risk_gate()`에서 기존 `validate_signal()` 통과 후 추가 게이트로 호출한다. `phase_risk_gate()`는 이미 `portfolios` 전체 객체에 접근하므로 최소한의 변경으로 전략 간 포지션을 집계할 수 있다.

**Tech Stack:** Python 3.14, pytest, `execution/risk_validator.py`, `run_cycle.py`

---

## File Structure

| 파일 | 변경 내용 |
|------|----------|
| `execution/risk_validator.py` | `check_cross_strategy_concentration()` 추가 + `STRATEGY_SECTOR_LIMITS` MOM/VAL/QNT 40%→30% |
| `run_cycle.py` | `phase_risk_gate()` 내 cross-strategy 게이트 호출 추가 (line ~853 이후) |
| `tests/test_cross_strategy_concentration.py` | **신규** — 새 함수 + 통합 게이트 테스트 |

---

### Task 1: 실패 테스트 작성

**Files:**
- Create: `tests/test_cross_strategy_concentration.py`

- [ ] **Step 1: 테스트 파일 작성**

```python
# tests/test_cross_strategy_concentration.py
"""Cross-strategy sector concentration gate tests."""
import pytest
from unittest.mock import patch
from execution.risk_validator import (
    check_cross_strategy_concentration,
    STRATEGY_SECTOR_LIMITS,
)


# ── 섹터 mock (yfinance 호출 없이) ──────────────────────────────────────────
SECTOR_MAP_MOCK = {
    "NVDA": "Technology",
    "AMD":  "Technology",
    "AMAT": "Technology",
    "LRCX": "Technology",
    "AAPL": "Technology",
    "MSFT": "Technology",
    "JPM":  "Financials",
    "BAC":  "Financials",
    "SPY":  "ETF-Broad",
}


def _mock_get_sector(symbol: str) -> str:
    return SECTOR_MAP_MOCK.get(symbol, "Unknown")


class TestCheckCrossStrategyConcentration:
    """check_cross_strategy_concentration() 단위 테스트."""

    def _build_strat(self, positions: dict) -> dict:
        """portfolios['strategies'] 한 항목 형식 생성."""
        return {
            "positions": {
                sym: {"market_value": val, "qty": 1, "current": val}
                for sym, val in positions.items()
            }
        }

    @patch("execution.risk_validator.get_sector", side_effect=_mock_get_sector)
    def test_blocks_when_cross_strategy_exceeds_threshold(self, _):
        """MOM 25%+QNT 20% Technology → 총 45% > 30% → BLOCK."""
        all_positions = {
            "MOM": self._build_strat({"NVDA": 25_000, "AMD": 0}),
            "QNT": self._build_strat({"AMAT": 20_000}),
        }
        passed, result = check_cross_strategy_concentration(
            symbol="LRCX",          # Technology
            trade_value=5_000,
            all_strategy_positions=all_positions,
            total_portfolio=100_000,
            max_pct=0.30,
        )
        assert not passed
        assert result.check_name == "cross_strategy_concentration"
        assert "Technology" in result.reason

    @patch("execution.risk_validator.get_sector", side_effect=_mock_get_sector)
    def test_passes_when_below_threshold(self, _):
        """MOM 10%+QNT 10% Technology → 총 20% < 30% → PASS."""
        all_positions = {
            "MOM": self._build_strat({"NVDA": 10_000}),
            "QNT": self._build_strat({"AMD": 10_000}),
        }
        passed, result = check_cross_strategy_concentration(
            symbol="JPM",           # Financials — different sector
            trade_value=5_000,
            all_strategy_positions=all_positions,
            total_portfolio=100_000,
            max_pct=0.30,
        )
        assert passed

    @patch("execution.risk_validator.get_sector", side_effect=_mock_get_sector)
    def test_unknown_sector_passes(self, _):
        """Unknown 섹터는 per-strategy 게이트에서 처리 → cross-strategy PASS."""
        all_positions = {"MOM": self._build_strat({})}
        passed, result = check_cross_strategy_concentration(
            symbol="UNKNOWN_TICKER",
            trade_value=5_000,
            all_strategy_positions=all_positions,
            total_portfolio=100_000,
            max_pct=0.30,
        )
        assert passed
        assert result.check_name == "cross_strategy_concentration"

    @patch("execution.risk_validator.get_sector", side_effect=_mock_get_sector)
    def test_trade_value_included_in_calculation(self, _):
        """새로 매수할 금액도 계산에 포함된다."""
        # 기존 보유 없음, trade_value만으로 50% → BLOCK
        all_positions = {"MOM": self._build_strat({})}
        passed, result = check_cross_strategy_concentration(
            symbol="NVDA",
            trade_value=50_000,     # 50% of 100K
            all_strategy_positions=all_positions,
            total_portfolio=100_000,
            max_pct=0.30,
        )
        assert not passed

    @patch("execution.risk_validator.get_sector", side_effect=_mock_get_sector)
    def test_empty_positions_passes(self, _):
        """포지션 없고 소액 매수 → PASS."""
        all_positions = {"MOM": self._build_strat({}), "QNT": self._build_strat({})}
        passed, result = check_cross_strategy_concentration(
            symbol="NVDA",
            trade_value=5_000,      # 5% → below 30%
            all_strategy_positions=all_positions,
            total_portfolio=100_000,
            max_pct=0.30,
        )
        assert passed

    def test_strategy_sector_limits_tightened(self):
        """MOM/VAL/QNT 전략별 sector limit이 30% 이하인지 확인."""
        for strat in ("MOM", "VAL", "QNT"):
            assert STRATEGY_SECTOR_LIMITS[strat] <= 0.30, (
                f"{strat} sector limit {STRATEGY_SECTOR_LIMITS[strat]:.0%} > 30%"
            )
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_cross_strategy_concentration.py -v 2>&1 | tail -20
```
예상: FAILED (`check_cross_strategy_concentration` 없음 + `STRATEGY_SECTOR_LIMITS` 값 불일치)

---

### Task 2: risk_validator.py 구현

**Files:**
- Modify: `execution/risk_validator.py`

- [ ] **Step 1: STRATEGY_SECTOR_LIMITS 30%로 강화**

`execution/risk_validator.py` line 331~338 수정:

기존:
```python
STRATEGY_SECTOR_LIMITS: dict[str, float] = {
    "MOM": 0.40,
    "VAL": 0.40,
    "QNT": 0.40,
    "LEV": 1.00,
    "LEV_ST": 1.00,
}
```

변경:
```python
STRATEGY_SECTOR_LIMITS: dict[str, float] = {
    "MOM": 0.30,    # 40% → 30% (10종목 기준 최대 3종목 동일 섹터)
    "VAL": 0.30,    # 40% → 30%
    "QNT": 0.25,    # 40% → 25% (20종목 기준 최대 5종목 동일 섹터)
    "LEV": 1.00,    # All ETF-Leveraged sector by design
    "LEV_ST": 1.00, # Single ETF by design
}
```

- [ ] **Step 2: check_cross_strategy_concentration() 함수 추가**

`execution/risk_validator.py`에서 `check_sector_concentration()` 함수 끝 (line ~212) 바로 다음에 추가:

```python
def check_cross_strategy_concentration(
    symbol: str,
    trade_value: float,
    all_strategy_positions: dict,
    total_portfolio: float,
    max_pct: float = 0.30,
) -> tuple[bool, "RiskCheckResult"]:
    """전략 간 교차 섹터 집중도 체크.

    단일 섹터가 전체 포트폴리오(total_portfolio)의 max_pct를 초과하면 BLOCK.
    Unknown 섹터는 per-strategy 게이트에서 이미 처리하므로 여기선 PASS.

    Args:
        symbol: 신규 매수 심볼
        trade_value: 매수 금액 ($)
        all_strategy_positions: portfolios["strategies"] 전체 dict
        total_portfolio: 전체 포트폴리오 가치 ($)
        max_pct: 섹터 최대 비중 (기본 30%)
    """
    target_sector = get_sector(symbol)
    if target_sector == "Unknown":
        return True, RiskCheckResult(
            passed=True,
            check_name="cross_strategy_concentration",
            reason=f"Unknown sector for {symbol} — deferred to per-strategy gate",
            value=0.0,
            threshold=max_pct,
        )

    # 전체 전략의 해당 섹터 보유액 합산
    sector_value = trade_value
    for strat_data in all_strategy_positions.values():
        positions = strat_data.get("positions") or {}
        for sym, pos in positions.items():
            val = pos.get("market_value") or (
                (pos.get("qty") or 0) * (pos.get("current") or 0)
            )
            if val and get_sector(sym) == target_sector:
                sector_value += float(val)

    weight = sector_value / total_portfolio if total_portfolio > 0 else 1.0
    passed = weight <= max_pct

    return passed, RiskCheckResult(
        passed=passed,
        check_name="cross_strategy_concentration",
        reason=(
            f"Portfolio-wide '{target_sector}' exposure {weight:.1%} "
            f"{'<=' if passed else '>'} {max_pct:.0%} limit"
        ),
        value=weight,
        threshold=max_pct,
    )
```

- [ ] **Step 3: 테스트 통과 확인**

```bash
python -m pytest tests/test_cross_strategy_concentration.py -v 2>&1 | tail -15
```
예상: PASSED 6/6

- [ ] **Step 4: 기존 테스트 회귀 확인**

```bash
python -m pytest tests/ -q 2>&1 | tail -5
```
예상: 70 passed, 1 skipped

- [ ] **Step 5: 커밋**

```bash
git add execution/risk_validator.py tests/test_cross_strategy_concentration.py
git commit -m "feat(risk): cross-strategy sector gate (30% portfolio limit) + tighten per-strategy limits"
```

---

### Task 3: phase_risk_gate()에 cross-strategy 게이트 연결

**Files:**
- Modify: `run_cycle.py:853~870`

- [ ] **Step 1: phase_risk_gate()에 import 및 게이트 추가**

`run_cycle.py` line 788 근처의 import 블록에 추가:
```python
from execution.risk_validator import validate_signal, check_cross_strategy_concentration
```

`run_cycle.py` line 853~861 (validate_signal 호출 블록) 이후 바로 다음에 삽입:

현재 코드 (line ~853~870):
```python
        passed, results = validate_signal(
            symbol=signal.symbol,
            side=signal.direction.value,
            trade_value=trade_value,
            strategy_capital=capital,
            strategy_cash=cash,
            current_positions=current_positions,
            strategy_code=signal.strategy,
        )

        status = "PASS" if passed else "FAIL"
```

변경 후:
```python
        passed, results = validate_signal(
            symbol=signal.symbol,
            side=signal.direction.value,
            trade_value=trade_value,
            strategy_capital=capital,
            strategy_cash=cash,
            current_positions=current_positions,
            strategy_code=signal.strategy,
        )

        # Cross-strategy sector concentration gate (BUY 전용)
        if passed and signal.direction == Direction.BUY:
            cross_passed, cross_result = check_cross_strategy_concentration(
                symbol=signal.symbol,
                trade_value=trade_value,
                all_strategy_positions=portfolios["strategies"],
                total_portfolio=portfolios.get("account_total", 0),
                max_pct=0.30,
            )
            if not cross_passed:
                passed = False
                results.append(cross_result)

        status = "PASS" if passed else "FAIL"
```

- [ ] **Step 2: import 수정**

`run_cycle.py` line 788:
```python
    from execution.risk_validator import validate_signal
```
↓ 변경:
```python
    from execution.risk_validator import validate_signal, check_cross_strategy_concentration
```

- [ ] **Step 3: 전체 테스트 실행**

```bash
python -m pytest tests/ -q 2>&1 | tail -5
```
예상: 70+ passed, 1 skipped

- [ ] **Step 4: 수동 smoke test — 현재 포트폴리오로 cross-strategy 게이트 동작 확인**

```bash
python -c "
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path('.env'))
import json
from execution.risk_validator import check_cross_strategy_concentration

portfolios = json.loads(Path('state/portfolios.json').read_text())
strategies = portfolios['strategies']
total = portfolios.get('account_total', 100000)

# Technology 30% 한도 테스트 — NVDA \$35K 매수 시도
passed, result = check_cross_strategy_concentration(
    symbol='NVDA',
    trade_value=35_000,
    all_strategy_positions=strategies,
    total_portfolio=total,
    max_pct=0.30,
)
print(f'NVDA \$35K 매수 시도: {\"PASS\" if passed else \"BLOCK\"}')
print(f'  {result.reason}')

# \$5K 매수 시도 (정상 범위)
passed2, result2 = check_cross_strategy_concentration(
    symbol='NVDA',
    trade_value=5_000,
    all_strategy_positions=strategies,
    total_portfolio=total,
    max_pct=0.30,
)
print(f'NVDA \$5K 매수 시도: {\"PASS\" if passed2 else \"BLOCK\"}')
print(f'  {result2.reason}')
"
```
예상:
```
NVDA $35K 매수 시도: BLOCK
  Portfolio-wide 'Technology' exposure 34.8% > 30% limit
NVDA $5K 매수 시도: PASS
  Portfolio-wide 'Technology' exposure 4.9% <= 30% limit
```

- [ ] **Step 5: 최종 커밋**

```bash
git add run_cycle.py
git commit -m "feat(risk): wire cross-strategy sector gate into phase_risk_gate"
```

---

## 검증 체크포인트

```bash
# 1. 전체 테스트
python -m pytest tests/ -q

# 2. 현재 STRATEGY_SECTOR_LIMITS 확인
python -c "
from execution.risk_validator import STRATEGY_SECTOR_LIMITS
for k, v in STRATEGY_SECTOR_LIMITS.items():
    print(f'{k}: {v:.0%}')
"

# 3. smoke test (Task 3 Step 4와 동일)
```

---

## 설계 결정 요약

| 항목 | 결정 | 근거 |
|------|------|------|
| 전략별 섹터 한도 | MOM/VAL 40%→30%, QNT 40%→25% | MOM 10종목×30%=3종목/섹터, QNT 20종목×25%=5종목/섹터 |
| 포트폴리오 전체 한도 | 30% | 단일 섹터가 포트폴리오 1/3 초과 시 과집중으로 판단 |
| Unknown 섹터 처리 | cross-strategy에서 PASS (per-strategy에서 이미 BLOCK) | 중복 차단 방지 |
| BUY 전용 게이트 | SELL은 건너뜀 | 청산은 집중도 해소 방향이므로 게이트 불필요 |
| 삽입 위치 | validate_signal() 통과 후 별도 체크 | validate_signal() 시그니처 변경 없이 최소 변경 |
