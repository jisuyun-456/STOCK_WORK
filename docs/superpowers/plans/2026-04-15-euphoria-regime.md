# Euphoria 5번째 레짐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 과매수 시장(RSI ≥ 75, VIX < 15, SPY > SMA50 > SMA200)을 감지하는 EUPHORIA 레짐을 추가하고 리스크를 자동 축소한다.

**Architecture:** 기존 4-레짐(BULL/NEUTRAL/BEAR/CRISIS) 체계에 EUPHORIA를 5번째 레짐으로 추가. rule-based(`detect_regime`)와 composite scoring(`detect_regime_enhanced`)에 VIX < 15 + RSI ≥ 75 조건을 삽입하고, allocator에 BULL 대비 리스크 축소 배분을 등록한다. HMM 레짐 스코어 매핑에도 EUPHORIA 폴백을 추가한다.

**Tech Stack:** Python 3.14, yfinance, pytest, strategies/regime_allocator.py, research/consensus.py, research/regime_hmm.py

---

## File Structure

| 파일 | 변경 내용 |
|------|----------|
| `strategies/regime_allocator.py` | REGIME_ALLOCATIONS + _REGIME_DESCRIPTIONS + severity dict에 EUPHORIA 추가 |
| `research/consensus.py` | detect_regime() + detect_regime_enhanced()에 RSI 계산 + EUPHORIA 분기 추가, REGIME_MULTIPLIERS에 EUPHORIA 추가 |
| `research/regime_hmm.py` | _REGIME_SCORES에 EUPHORIA 추가 (폴백 score=1.0) |
| `tests/test_regime_euphoria.py` | **신규** — 3개 파일 통합 EUPHORIA 테스트 |

---

### Task 1: EUPHORIA 레짐 할당 테스트 작성 및 구현

**Files:**
- Create: `tests/test_regime_euphoria.py`
- Modify: `strategies/regime_allocator.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_regime_euphoria.py
"""EUPHORIA (5th regime) tests — allocator, consensus detection, HMM score."""
import pytest
from strategies.regime_allocator import (
    REGIME_ALLOCATIONS,
    allocate,
    get_regime_description,
    generate_regime_exit_signals,
)


class TestEuphoriaAllocator:
    def test_euphoria_in_regime_allocations(self):
        assert "EUPHORIA" in REGIME_ALLOCATIONS

    def test_euphoria_weights_sum_to_one(self):
        weights = REGIME_ALLOCATIONS["EUPHORIA"]
        assert abs(sum(weights.values()) - 1.0) < 1e-6

    def test_euphoria_has_required_strategies(self):
        weights = REGIME_ALLOCATIONS["EUPHORIA"]
        for key in ("MOM", "VAL", "QNT", "LEV", "LEV_ST", "CASH"):
            assert key in weights

    def test_euphoria_lev_fixed(self):
        """LEV + LEV_ST는 모든 레짐에서 0.50 고정."""
        weights = REGIME_ALLOCATIONS["EUPHORIA"]
        assert abs(weights["LEV"] + weights["LEV_ST"] - 0.50) < 1e-6

    def test_euphoria_cash_greater_than_bull(self):
        """과매수 리스크 축소 — BULL(0%)보다 CASH 비율이 높아야 한다."""
        assert REGIME_ALLOCATIONS["EUPHORIA"]["CASH"] > REGIME_ALLOCATIONS["BULL"]["CASH"]

    def test_euphoria_mom_less_than_bull(self):
        """과매수 시장에서 모멘텀 추격 억제."""
        assert REGIME_ALLOCATIONS["EUPHORIA"]["MOM"] < REGIME_ALLOCATIONS["BULL"]["MOM"]

    def test_allocate_euphoria_returns_amounts(self):
        result = allocate("EUPHORIA", 100_000)
        total = sum(result.values())
        assert abs(total - 100_000) < 1.0  # rounding tolerance

    def test_euphoria_description_exists(self):
        desc = get_regime_description("EUPHORIA")
        assert "EUPHORIA" in desc or "과열" in desc or "과매수" in desc

    def test_euphoria_severity_equals_bull(self):
        """EUPHORIA → BEAR 전환 시 exit signal 발생해야 한다 (severity 0)."""
        signals = generate_regime_exit_signals("BEAR", "EUPHORIA", {})
        assert len(signals) > 0

    def test_euphoria_to_bull_no_exit_signal(self):
        """EUPHORIA → BULL 전환은 리스크 감소이므로 exit signal 없음."""
        signals = generate_regime_exit_signals("BULL", "EUPHORIA", {})
        assert signals == []
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
cd /c/Users/yjisu/Desktop/STOCK_WORK
python -m pytest tests/test_regime_euphoria.py::TestEuphoriaAllocator -v 2>&1 | head -40
```
예상: FAILED (REGIME_ALLOCATIONS에 EUPHORIA 없음)

- [ ] **Step 3: regime_allocator.py에 EUPHORIA 구현**

`strategies/regime_allocator.py` 수정:

**REGIME_ALLOCATIONS에 추가** (CRISIS 항목 뒤):
```python
    # EUPHORIA: 과매수 신호 (RSI≥75, VIX<15, SPY>SMA50>SMA200) → 리스크 축소
    # LEV+LEV_ST 50% 고정, 나머지 MOM 감소+CASH 증가로 잠재 반락 대비
    "EUPHORIA": {"MOM": 0.10, "VAL": 0.125, "QNT": 0.15, "LEV": 0.25, "LEV_ST": 0.25, "CASH": 0.125},
```

**_REGIME_DESCRIPTIONS에 추가**:
```python
    "EUPHORIA": (
        "과열장(EUPHORIA): LEV 25%(SPY+TQQQ) + LEV_ST 25%(VIX/SPY 모멘텀) + QNT 15% + VAL 12.5% + "
        "현금 12.5% + MOM 10%. RSI≥75·VIX<15·SPY>SMA50>SMA200 과매수 신호 → 모멘텀 감소·현금 확보. "
        "잠재 반락 대비 BULL 대비 MOM 50% 감소."
    ),
```

**severity dict 수정** (`generate_regime_exit_signals` 함수 내 line 117):
```python
    severity = {"EUPHORIA": 0, "BULL": 0, "NEUTRAL": 1, "BEAR": 2, "CRISIS": 3}
```

- [ ] **Step 4: 테스트 재실행 — 통과 확인**

```bash
python -m pytest tests/test_regime_euphoria.py::TestEuphoriaAllocator -v
```
예상: PASSED 9/9

- [ ] **Step 5: 커밋**

```bash
git add strategies/regime_allocator.py tests/test_regime_euphoria.py
git commit -m "feat(regime): add EUPHORIA 5th regime to allocator (MOM↓ CASH↑)"
```

---

### Task 2: EUPHORIA 탐지 테스트 작성 및 consensus.py 구현

**Files:**
- Modify: `tests/test_regime_euphoria.py` (TestEuphoriaConsensus 클래스 추가)
- Modify: `research/consensus.py`

- [ ] **Step 1: consensus 실패 테스트 추가**

`tests/test_regime_euphoria.py`에 아래 클래스 추가:
```python
class TestEuphoriaConsensus:
    """detect_regime, detect_regime_enhanced EUPHORIA 분기 단위 테스트."""

    def _make_hist(self, n=252, trend="euphoria"):
        """yfinance hist DataFrame 모의 생성."""
        import pandas as pd
        import numpy as np

        dates = pd.date_range("2024-01-01", periods=n, freq="B")
        if trend == "euphoria":
            # 강한 상승 추세: SMA200 < SMA50 < current
            prices = np.linspace(400, 560, n)  # SPY 40% 상승
        elif trend == "bear":
            prices = np.linspace(500, 380, n)
        else:
            prices = np.full(n, 480.0)
        return pd.DataFrame({"Close": prices}, index=dates)

    def test_detect_regime_euphoria_conditions(self):
        """EUPHORIA: VIX<15 + RSI≥75 + SPY>SMA50>SMA200 시 EUPHORIA 반환."""
        from research.consensus import _classify_regime_from_data

        hist = self._make_hist(trend="euphoria")
        result = _classify_regime_from_data(hist, vix_level=12.0)
        assert result == "EUPHORIA"

    def test_detect_regime_no_euphoria_high_vix(self):
        """VIX ≥ 15이면 EUPHORIA 아님 → BULL 또는 NEUTRAL."""
        from research.consensus import _classify_regime_from_data

        hist = self._make_hist(trend="euphoria")
        result = _classify_regime_from_data(hist, vix_level=18.0)
        assert result != "EUPHORIA"

    def test_detect_regime_no_euphoria_low_rsi(self):
        """RSI < 75이면 EUPHORIA 아님 (횡보 추세)."""
        from research.consensus import _classify_regime_from_data

        # 횡보 데이터는 RSI < 75
        hist = self._make_hist(trend="neutral")
        result = _classify_regime_from_data(hist, vix_level=12.0)
        assert result != "EUPHORIA"

    def test_regime_multipliers_has_euphoria(self):
        from research.consensus import REGIME_MULTIPLIERS
        assert "EUPHORIA" in REGIME_MULTIPLIERS

    def test_get_regime_weights_euphoria(self):
        from research.consensus import get_regime_weights
        weights = get_regime_weights("EUPHORIA")
        assert abs(sum(weights.values()) - 1.0) < 1e-6
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_regime_euphoria.py::TestEuphoriaConsensus -v 2>&1 | head -30
```
예상: FAILED (`_classify_regime_from_data` 없음)

- [ ] **Step 3: consensus.py에 _classify_regime_from_data 헬퍼 + EUPHORIA 구현**

`research/consensus.py`에서 다음을 수정:

**① `REGIME_MULTIPLIERS`에 EUPHORIA 추가** (line ~37 부근):
```python
REGIME_MULTIPLIERS: dict[str, dict[str, float]] = {
    "CRISIS": {"risk_controller": 2.0, "macro_economist": 1.5},
    "BEAR": {"risk_controller": 1.5, "macro_economist": 1.3},
    "BULL": {"equity_research": 1.3, "technical_strategist": 1.2},
    "EUPHORIA": {"equity_research": 1.1, "risk_controller": 1.4},  # 과열 — 리스크 관리 가중
    "NEUTRAL": {},
}
```

**② RSI 계산 + EUPHORIA 분류 헬퍼 함수 추가** (모듈 상단 함수, `detect_regime` 위에):
```python
def _calc_rsi(close_series, period: int = 14) -> float:
    """Wilder RSI (pandas Series). 데이터 부족 시 50.0 반환."""
    if len(close_series) < period + 1:
        return 50.0
    delta = close_series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    last_loss = loss.iloc[-1]
    if last_loss == 0:
        return 100.0
    rs = gain.iloc[-1] / last_loss
    return round(float(100.0 - 100.0 / (1 + rs)), 2)


def _classify_regime_from_data(hist, vix_level: float) -> str:
    """hist(Close 포함 DataFrame)와 VIX 레벨로 레짐 분류.

    우선순위:
      1. CRISIS  — SPY < SMA200 and VIX > 30
      2. BEAR    — SPY < SMA200
      3. EUPHORIA — SPY > SMA50 > SMA200 and VIX < 15 and RSI ≥ 75
      4. BULL    — SPY ≥ SMA200 and VIX < 20
      5. NEUTRAL — 나머지
    """
    close = hist["Close"]
    current_price = close.iloc[-1]
    sma200 = close.rolling(200).mean().iloc[-1]
    sma50 = close.rolling(50).mean().iloc[-1]
    ratio = current_price / sma200 if sma200 > 0 else 1.0

    if ratio < 1.0 and vix_level > 30:
        return "CRISIS"
    if ratio < 1.0:
        return "BEAR"

    # 과매수 조건 — EUPHORIA
    if (
        vix_level < 15
        and current_price > sma50 > sma200
    ):
        rsi = _calc_rsi(close)
        if rsi >= 75:
            return "EUPHORIA"

    if ratio >= 1.0 and vix_level < 20:
        return "BULL"
    return "NEUTRAL"
```

**③ `detect_regime()`에서 내부 분류 로직을 헬퍼로 교체** (기존 if/elif 체인 → 헬퍼 호출):

기존 코드 (line ~66~79):
```python
    if ratio < 1.0 and vix_level > 30:
        regime = "CRISIS"
        reasoning = f"SPY ({current_price:.2f}) below SMA200 ({sma200:.2f}), VIX={vix_level:.1f} > 30"
    elif ratio < 1.0 and vix_level <= 30:
        regime = "BEAR"
        reasoning = f"SPY ({current_price:.2f}) below SMA200 ({sma200:.2f}), VIX={vix_level:.1f}"
    elif ratio >= 1.0 and vix_level < 20:
        regime = "BULL"
        reasoning = f"SPY ({current_price:.2f}) above SMA200 ({sma200:.2f}), VIX={vix_level:.1f} < 20"
    else:
        regime = "NEUTRAL"
        reasoning = f"SPY ({current_price:.2f}) vs SMA200 ({sma200:.2f}), VIX={vix_level:.1f}"
```

대체 코드:
```python
    regime = _classify_regime_from_data(hist, vix_level)
    reasoning = (
        f"SPY={current_price:.2f}, SMA200={sma200:.2f}(ratio={ratio:.4f}), "
        f"VIX={vix_level:.1f} → {regime}"
    )
```

(주의: `sma200` 변수는 `detect_regime()` 함수 내에서 이미 계산되어 있음. `_classify_regime_from_data`가 hist를 받으므로 내부에서 재계산.)

**④ `detect_regime_enhanced()`에 EUPHORIA 분기 추가** (기존 composite 임계값 블록 교체):

기존 코드 (line ~222~228):
```python
    if composite > 0.7:
        regime = "BULL"
    elif composite > 0.4:
        regime = "NEUTRAL"
    elif composite > 0.2:
        regime = "BEAR"
    else:
        regime = "CRISIS"
```

대체 코드:
```python
    # EUPHORIA 오버라이드: composite 상위 + VIX < 15 + RSI ≥ 75
    _rsi = _calc_rsi(hist["Close"]) if not hist.empty else 50.0
    if composite > 0.85 and vix_level < 15 and _rsi >= 75:
        regime = "EUPHORIA"
    elif composite > 0.7:
        regime = "BULL"
    elif composite > 0.4:
        regime = "NEUTRAL"
    elif composite > 0.2:
        regime = "BEAR"
    else:
        regime = "CRISIS"
```

- [ ] **Step 4: 테스트 재실행 — 통과 확인**

```bash
python -m pytest tests/test_regime_euphoria.py::TestEuphoriaConsensus -v
```
예상: PASSED 5/5

- [ ] **Step 5: 기존 consensus 테스트 회귀 확인**

```bash
python -m pytest tests/ -v --ignore=tests/test_regime_hmm.py -q 2>&1 | tail -20
```
예상: 기존 테스트 모두 PASS (detect_regime 로직 변경에 따른 회귀 없음)

- [ ] **Step 6: 커밋**

```bash
git add research/consensus.py tests/test_regime_euphoria.py
git commit -m "feat(regime): add EUPHORIA detection to detect_regime + detect_regime_enhanced"
```

---

### Task 3: HMM _REGIME_SCORES에 EUPHORIA 추가

**Files:**
- Modify: `tests/test_regime_euphoria.py` (TestEuphoriaHMM 클래스 추가)
- Modify: `research/regime_hmm.py`

- [ ] **Step 1: HMM 실패 테스트 추가**

`tests/test_regime_euphoria.py`에 아래 클래스 추가:
```python
class TestEuphoriaHMM:
    def test_regime_scores_has_euphoria(self):
        from research.regime_hmm import _REGIME_SCORES
        assert "EUPHORIA" in _REGIME_SCORES

    def test_euphoria_score_equals_bull(self):
        """EUPHORIA는 BULL과 같은 점수(1.0) — HMM 연속 스코어링 일관성."""
        from research.regime_hmm import _REGIME_SCORES
        assert _REGIME_SCORES["EUPHORIA"] == _REGIME_SCORES["BULL"]

    def test_score_from_regime_prob_includes_euphoria(self):
        """score_from_regime_prob이 EUPHORIA 확률을 올바르게 반영한다."""
        from research.regime_hmm import score_from_regime_prob
        # EUPHORIA 100% → score = 1.0
        state_probs = {"EUPHORIA": 1.0, "BULL": 0.0, "NEUTRAL": 0.0, "BEAR": 0.0, "CRISIS": 0.0}
        score = score_from_regime_prob(state_probs, state_to_regime={})
        assert abs(score - 1.0) < 1e-6

    def test_score_mixed_euphoria_bull(self):
        """EUPHORIA 50% + BULL 50% → score ≈ 1.0 (둘 다 최고점)."""
        from research.regime_hmm import score_from_regime_prob
        state_probs = {"EUPHORIA": 0.5, "BULL": 0.5}
        score = score_from_regime_prob(state_probs, state_to_regime={})
        assert abs(score - 1.0) < 1e-6
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
python -m pytest tests/test_regime_euphoria.py::TestEuphoriaHMM -v 2>&1 | head -25
```
예상: FAILED (`_REGIME_SCORES`에 EUPHORIA 없음)

- [ ] **Step 3: regime_hmm.py에 EUPHORIA 추가**

`research/regime_hmm.py` line 29~34 수정:

기존:
```python
_REGIME_SCORES: dict[str, float] = {
    "BULL": 1.0,
    "NEUTRAL": 0.6,
    "BEAR": 0.25,
    "CRISIS": 0.0,
}
```

변경:
```python
_REGIME_SCORES: dict[str, float] = {
    "EUPHORIA": 1.0,  # 과매수 — BULL과 동일 연속 점수 (HMM은 RSI 미포함)
    "BULL": 1.0,
    "NEUTRAL": 0.6,
    "BEAR": 0.25,
    "CRISIS": 0.0,
}
```

- [ ] **Step 4: 테스트 재실행 — 통과 확인**

```bash
python -m pytest tests/test_regime_euphoria.py::TestEuphoriaHMM -v
```
예상: PASSED 4/4

- [ ] **Step 5: 전체 테스트 실행**

```bash
python -m pytest tests/ -v -q 2>&1 | tail -20
```
예상: 모든 기존 테스트 PASS, EUPHORIA 신규 테스트 13개 PASS
(test_regime_hmm.py: hmmlearn 미설치 시 skip 유지)

- [ ] **Step 6: 최종 커밋**

```bash
git add research/regime_hmm.py tests/test_regime_euphoria.py
git commit -m "feat(regime): add EUPHORIA to HMM _REGIME_SCORES + full test suite (13 tests)"
```

---

## 검증 체크포인트

```bash
# 1. 전체 테스트
python -m pytest tests/ -v -q 2>&1 | tail -20

# 2. EUPHORIA 할당 수동 확인
python -c "
from strategies.regime_allocator import allocate, REGIME_ALLOCATIONS
print('=== EUPHORIA weights ===')
print(REGIME_ALLOCATIONS['EUPHORIA'])
print('Sum:', sum(REGIME_ALLOCATIONS['EUPHORIA'].values()))
allocate('EUPHORIA', 100_000)
"

# 3. 레짐 설명 확인
python -c "
from strategies.regime_allocator import get_regime_description
for r in ['BULL', 'EUPHORIA', 'NEUTRAL', 'BEAR', 'CRISIS']:
    print(r, ':', get_regime_description(r)[:60])
"

# 4. EUPHORIA 분류 수동 확인
python -c "
from research.consensus import _classify_regime_from_data, _calc_rsi
import pandas as pd, numpy as np
dates = pd.date_range('2024-01-01', periods=252, freq='B')
prices = np.linspace(400, 560, 252)  # 강한 상승
hist = pd.DataFrame({'Close': prices}, index=dates)
rsi = _calc_rsi(hist['Close'])
regime = _classify_regime_from_data(hist, vix_level=12.0)
print(f'RSI={rsi:.1f}, VIX=12.0 → regime={regime}')  # 예상: EUPHORIA
regime2 = _classify_regime_from_data(hist, vix_level=18.0)
print(f'RSI={rsi:.1f}, VIX=18.0 → regime={regime2}')  # 예상: BULL
"
```

---

## 설계 결정 요약

| 항목 | 결정 | 근거 |
|------|------|------|
| EUPHORIA 배분 | MOM 10%, VAL 12.5%, QNT 15%, LEV 25%, LEV_ST 25%, CASH 12.5% | BULL 대비 MOM 50% 감소, CASH 12.5% 확보 — 잠재 반락 대비 |
| Severity | 0 (BULL과 동일) | EUPHORIA→BEAR 전환 시 exit signal 발생, BULL→EUPHORIA는 발생 안 함 |
| RSI 임계값 | ≥ 75 | 기존 명세 그대로 (과매수 구간 표준) |
| VIX 임계값 | < 15 | 기존 명세 그대로 (저변동성 과열 구간) |
| composite 임계값 | > 0.85 (enhanced에서) | BULL(0.7) 위 별도 슬롯, 충분한 분리 마진 |
| HMM 스코어 | 1.0 (BULL과 동일) | HMM 피처에 RSI 없음 → EUPHORIA/BULL 구분 불가, 동일 점수 할당 |
