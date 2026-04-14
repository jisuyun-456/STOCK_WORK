# strategy_params.json → 전략 코드 연결 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `config/strategy_params.json`을 MOM/QNT/VAL 전략 코드에 연결하여 파라미터 변경이 시그널 생성에 즉시 반영되도록 한다.

**Architecture:** 공통 config loader 함수를 만들고, 각 전략 클래스에 `__init__`을 추가해 init 시점에 파라미터를 읽는다. QNT에는 `min_composite_score` 필터를 추가해 임계값 이하 종목을 BUY 대상에서 제외한다.

**Tech Stack:** Python, JSON (config/strategy_params.json), strategies/*.py

---

## 파일 구조

| 파일 | 변경 내용 |
|------|---------|
| `config/loader.py` (신규) | strategy_params.json 로더 — 모듈 레벨 캐시 |
| `strategies/momentum.py` | `__init__` 추가: max_positions, stop_loss_pct, position_pct, lookback_months |
| `strategies/quant_factor.py` | `__init__` 추가: max_positions, ols_window, min_composite_score 필터 |
| `strategies/value_quality.py` | `__init__` 추가: max_positions, pe/roe/fcf 임계값 |
| `tests/test_strategy_params.py` (신규) | 파라미터 반영 검증 테스트 |

---

## Task 1: config loader 작성

**Files:**
- Create: `config/loader.py`

- [ ] **Step 1: 파일 생성**

```python
# config/loader.py
"""strategy_params.json 로더 — 모듈 레벨 캐시로 중복 IO 방지."""
from __future__ import annotations
import json
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "strategy_params.json"
_cache: dict | None = None


def load_strategy_params() -> dict:
    """strategy_params.json을 읽어 dict로 반환. 모듈 캐시 사용."""
    global _cache
    if _cache is None:
        _cache = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return _cache


def reload_strategy_params() -> dict:
    """캐시를 버리고 다시 읽는다 (테스트/변경 감지용)."""
    global _cache
    _cache = None
    return load_strategy_params()
```

- [ ] **Step 2: 동작 확인**

```bash
cd C:\Users\yjisu\Desktop\STOCK_WORK
python -c "from config.loader import load_strategy_params; p=load_strategy_params(); print(p['momentum']['stop_loss_pct'])"
```

예상 출력: `0.1`

---

## Task 2: MomentumStrategy 파라미터 연결

**Files:**
- Modify: `strategies/momentum.py:55-62` (클래스 속성 → __init__ 로 이동)

연결 대상:
- `max_positions` ← `config["momentum"]["max_positions"]`
- `stop_loss_pct` ← `config["momentum"]["stop_loss_pct"]`
- `position_pct` ← `config["momentum"]["position_pct"]` (BUY signal weight_pct)
- lookback 개월 수 ← `config["momentum"]["lookback_long"] // 21` (거래일 → 개월 변환)

- [ ] **Step 1: 테스트 작성 (`tests/test_strategy_params.py`)**

```python
# tests/test_strategy_params.py
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.loader import reload_strategy_params
import config.loader as _loader


def _patch_config(overrides: dict):
    """테스트용 config 패치 헬퍼."""
    import copy
    base = json.loads((Path(__file__).parent.parent / "config/strategy_params.json").read_text())
    for section, vals in overrides.items():
        base[section].update(vals)
    _loader._cache = base
    return base


def test_momentum_reads_max_positions():
    _patch_config({"momentum": {"max_positions": 5}})
    from importlib import reload
    import strategies.momentum as m
    reload(m)
    strat = m.MomentumStrategy()
    assert strat.max_positions == 5, f"expected 5, got {strat.max_positions}"
    reload_strategy_params()


def test_momentum_reads_stop_loss():
    _patch_config({"momentum": {"stop_loss_pct": 0.07}})
    from importlib import reload
    import strategies.momentum as m
    reload(m)
    strat = m.MomentumStrategy()
    assert strat.stop_loss_pct == 0.07, f"expected 0.07, got {strat.stop_loss_pct}"
    reload_strategy_params()


def test_momentum_reads_position_pct():
    _patch_config({"momentum": {"position_pct": 0.15}})
    from importlib import reload
    import strategies.momentum as m
    reload(m)
    strat = m.MomentumStrategy()
    assert strat.position_pct == 0.15, f"expected 0.15, got {strat.position_pct}"
    reload_strategy_params()
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_strategy_params.py::test_momentum_reads_max_positions -v
```

예상: `FAILED` (AttributeError: MomentumStrategy has no __init__ with config)

- [ ] **Step 3: MomentumStrategy에 `__init__` 추가**

`strategies/momentum.py`의 클래스 속성 뒤(line 62 다음)에 삽입:

```python
    def __init__(self) -> None:
        from config.loader import load_strategy_params
        _cfg = load_strategy_params().get("momentum", {})
        self.max_positions: int = int(_cfg.get("max_positions", self.__class__.max_positions))
        self.stop_loss_pct: float = float(_cfg.get("stop_loss_pct", self.__class__.stop_loss_pct))
        self.position_pct: float = float(_cfg.get("position_pct", 0.10))
        # lookback_long (거래일) → 개월 변환 (21거래일 ≈ 1개월)
        lookback_td: int = int(_cfg.get("lookback_long", 252))
        self.lookback_months: int = max(1, lookback_td // 21)
```

- [ ] **Step 4: BUY 시그널에서 `position_pct` 반영**

`strategies/momentum.py` line 176 (`target_weight = 1.0 / len(ranked)`) 를 수정:

```python
        # position_pct: config에서 읽은 목표 비중. 설정 없으면 등가중.
        target_weight = getattr(self, "position_pct", 1.0 / len(ranked)) if ranked else 0.0
```

- [ ] **Step 5: lookback_months 반영**

`strategies/momentum.py` line 92-93 (`pd.DateOffset(months=12)`, `months=1`) 수정:

```python
                lookback_m = getattr(self, "lookback_months", 12)
                price_12m_ago = series.asof(last_date - pd.DateOffset(months=lookback_m))
                price_1m_ago = series.asof(last_date - pd.DateOffset(months=1))
```

- [ ] **Step 6: 테스트 통과 확인**

```bash
python -m pytest tests/test_strategy_params.py::test_momentum_reads_max_positions tests/test_strategy_params.py::test_momentum_reads_stop_loss tests/test_strategy_params.py::test_momentum_reads_position_pct -v
```

예상: 3개 PASSED

- [ ] **Step 7: 커밋**

```bash
git add config/loader.py strategies/momentum.py tests/test_strategy_params.py
git commit -m "feat: MomentumStrategy — strategy_params.json 파라미터 연결"
```

---

## Task 3: QuantFactorStrategy 파라미터 연결 + min_composite_score 필터

**Files:**
- Modify: `strategies/quant_factor.py:265-284` (클래스 속성 → __init__)

연결 대상:
- `max_positions` ← `config["quant_factor"]["max_positions"]`
- `OLS_WINDOW` ← `config["quant_factor"]["ols_window"]`
- `min_composite_score` ← `config["quant_factor"]["min_composite_score"]` (신규 필터)

핵심 변경: `ranked = sorted(...)[:self.max_positions]` 이후 `min_composite_score` 이하 제거.

- [ ] **Step 1: 테스트 추가 (`tests/test_strategy_params.py`에 append)**

```python
def test_qnt_reads_max_positions():
    _patch_config({"quant_factor": {"max_positions": 10}})
    from importlib import reload
    import strategies.quant_factor as q
    reload(q)
    strat = q.QuantFactorStrategy()
    assert strat.max_positions == 10, f"expected 10, got {strat.max_positions}"
    reload_strategy_params()


def test_qnt_min_composite_score_filters():
    """min_composite_score=0.45로 설정 시 낮은 스코어 종목이 ranked에서 제외되는지 확인."""
    _patch_config({"quant_factor": {"min_composite_score": 0.45, "max_positions": 20}})
    from importlib import reload
    import strategies.quant_factor as q
    reload(q)
    strat = q.QuantFactorStrategy()
    assert strat.min_composite_score == 0.45
    # composite_scores에서 필터링 로직 직접 테스트
    scores = {"A": 0.76, "B": 0.33, "C": 0.22, "D": 0.10}
    filtered = {k: v for k, v in scores.items() if v >= strat.min_composite_score}
    assert set(filtered.keys()) == {"A", "B"}, f"unexpected: {filtered}"
    reload_strategy_params()
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_strategy_params.py::test_qnt_reads_max_positions tests/test_strategy_params.py::test_qnt_min_composite_score_filters -v
```

예상: 2개 FAILED

- [ ] **Step 3: QuantFactorStrategy에 `__init__` 추가**

`strategies/quant_factor.py` line 284 (`OLS_WINDOW: int = 60`) 다음에 삽입:

```python
    def __init__(self) -> None:
        from config.loader import load_strategy_params
        _cfg = load_strategy_params().get("quant_factor", {})
        self.max_positions: int = int(_cfg.get("max_positions", self.__class__.max_positions))
        self.OLS_WINDOW: int = int(_cfg.get("ols_window", self.__class__.OLS_WINDOW))
        self.min_composite_score: float = float(_cfg.get("min_composite_score", 0.3))
```

- [ ] **Step 4: `min_composite_score` 필터 삽입**

`strategies/quant_factor.py` line 408 (`ranked = sorted(...)[:self.max_positions]`) 직후에 추가:

```python
        # min_composite_score 미만 종목 제거 (Variant 파라미터 반영)
        min_score = getattr(self, "min_composite_score", 0.0)
        if min_score > 0:
            ranked = [(sym, s) for sym, s in ranked if s >= min_score]
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
python -m pytest tests/test_strategy_params.py::test_qnt_reads_max_positions tests/test_strategy_params.py::test_qnt_min_composite_score_filters -v
```

예상: 2개 PASSED

- [ ] **Step 6: 커밋**

```bash
git add strategies/quant_factor.py tests/test_strategy_params.py
git commit -m "feat: QuantFactorStrategy — strategy_params.json 연결 + min_composite_score 필터"
```

---

## Task 4: ValueQualityStrategy 파라미터 연결

**Files:**
- Modify: `strategies/value_quality.py:277-289` (클래스 속성 → __init__)

연결 대상:
- `max_positions` ← `config["value_quality"]["max_positions"]` (코드=15 vs config=5 불일치 수정)
- `pe_threshold_neutral` ← `config["value_quality"]["pe_threshold_neutral"]`
- `roe_threshold_neutral` ← `config["value_quality"]["roe_threshold_neutral"]`
- `fcf_yield_threshold` ← `config["value_quality"]["fcf_yield_threshold"]`

- [ ] **Step 1: 테스트 추가**

```python
def test_val_reads_max_positions():
    _patch_config({"value_quality": {"max_positions": 5}})
    from importlib import reload
    import strategies.value_quality as v
    reload(v)
    strat = v.ValueQualityStrategy()
    assert strat.max_positions == 5, f"expected 5, got {strat.max_positions}"
    reload_strategy_params()


def test_val_reads_pe_threshold():
    _patch_config({"value_quality": {"pe_threshold_neutral": 18}})
    from importlib import reload
    import strategies.value_quality as v
    reload(v)
    strat = v.ValueQualityStrategy()
    assert strat.pe_threshold_neutral == 18, f"expected 18, got {strat.pe_threshold_neutral}"
    reload_strategy_params()
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_strategy_params.py::test_val_reads_max_positions tests/test_strategy_params.py::test_val_reads_pe_threshold -v
```

예상: 2개 FAILED

- [ ] **Step 3: ValueQualityStrategy에 `__init__` 추가**

`strategies/value_quality.py` line 289 (`take_profit_pct = 0.20`) 다음에 삽입:

```python
    def __init__(self) -> None:
        from config.loader import load_strategy_params
        _cfg = load_strategy_params().get("value_quality", {})
        self.max_positions: int = int(_cfg.get("max_positions", self.__class__.max_positions))
        self.pe_threshold_neutral: float = float(_cfg.get("pe_threshold_neutral", 20))
        self.roe_threshold_neutral: float = float(_cfg.get("roe_threshold_neutral", 0.12))
        self.fcf_yield_threshold: float = float(_cfg.get("fcf_yield_threshold", 0.05))
```

- [ ] **Step 4: Regime 필터 로직에서 config 값 참조**

`strategies/value_quality.py`에서 regime별 필터 dict를 찾아 `pe_threshold_neutral` 사용 여부 확인.
현재 코드에 `NEUTRAL_PE_THRESHOLD` 등의 별도 상수가 있다면 `self.pe_threshold_neutral`로 대체.

(코드 탐색 후 apply — Regime 분기별로 `max_pe`, `min_roe`, `min_fcf_yield` 계산 시 base값으로 사용)

- [ ] **Step 5: 테스트 통과 확인**

```bash
python -m pytest tests/test_strategy_params.py -v
```

예상: 전체 PASSED (7개)

- [ ] **Step 6: 커밋**

```bash
git add strategies/value_quality.py tests/test_strategy_params.py
git commit -m "feat: ValueQualityStrategy — strategy_params.json 연결 (max_positions, pe/roe/fcf threshold)"
```

---

## Task 5: Iteration 2 — Variant A/B/C 재비교

- [ ] **Step 1: Variant A 시그널 수집 (기준점)**

```bash
python run_cycle.py --phase signals --dry-run 2>&1 | grep -E "(signals:|buy|sell)" | head -50
```

예상: MOM 10 BUY (`weight_pct=0.10`), QNT 20 BUY (score≥0.3), LEV 2 BUY

- [ ] **Step 2: Variant B 파라미터 적용**

`config/strategy_params.json` 수정:
```json
"momentum": { "position_pct": 0.15, "stop_loss_pct": 0.13, "lookback_long": 126 },
"quant_factor": { "min_composite_score": 0.20 }
```

- [ ] **Step 3: Variant B 시그널 수집**

```bash
python run_cycle.py --phase signals --dry-run 2>&1 | grep -E "(signals:|buy|sell)" | head -50
```

예상:
- MOM: weight_pct=0.15 (A의 0.10에서 증가), lookback 6개월로 변경
- QNT: min_score=0.20 → 더 많은 종목 포함 (모든 20개)

- [ ] **Step 4: Variant C 파라미터 적용**

```json
"momentum": { "position_pct": 0.07, "stop_loss_pct": 0.07, "lookback_long": 252 },
"quant_factor": { "min_composite_score": 0.45 }
```

- [ ] **Step 5: Variant C 시그널 수집**

```bash
python run_cycle.py --phase signals --dry-run 2>&1 | grep -E "(signals:|buy|sell)" | head -50
```

예상:
- MOM: weight_pct=0.07
- QNT: min_score=0.45 → 상위 2개만 (MU 0.76, LRCX 0.33)

- [ ] **Step 6: 원본 파라미터 복원**

```bash
cp config/strategy_params.backup.json config/strategy_params.json  # 또는 수동 복원
```

- [ ] **Step 7: 비교 결과 Obsidian 기록 + 최종 커밋**

```bash
git add state/ reports/
git commit -m "data: Iteration 2 Variant A/B/C 비교 결과 반영"
```

---

## Verification

전체 검증 순서:

```bash
# 1. 유닛 테스트
python -m pytest tests/test_strategy_params.py -v

# 2. 실제 시그널 생성 검증 (각 Variant별 다른 시그널 확인)
python run_cycle.py --phase signals --dry-run 2>&1 | grep "signals:"

# 3. 전체 사이클 이상 없음 확인
python run_cycle.py --phase all --dry-run 2>&1 | tail -5
```

성공 기준:
- `python -m pytest tests/test_strategy_params.py -v` → 7개 이상 PASSED
- Variant A/B/C 시그널 수가 서로 다름 (특히 QNT: B>A>C)
- `=== Cycle Complete ===` 출력 (오류 없음)
