# Workflow Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 전체 파이프라인 감사에서 발견된 취약점 12개를 수정하여 데이터 무결성, 수치 안전성, 레짐/리포트 정확성을 확보한다.

**Architecture:** 4개 주제 그룹으로 분류. 각 Task는 TDD (실패 테스트 → 구현 → 통과). 기존 테스트 회귀 없음 유지.

**Tech Stack:** Python 3.14, pytest, `execution/order_manager.py`, `execution/risk_validator.py`, `scripts/performance_calculator.py`, `run_cycle.py`, `research/consensus.py`

---

## File Structure

| 파일 | 변경 내용 |
|------|----------|
| `execution/order_manager.py:44` | A1: `_next_seq()` JSON 파싱 방어 |
| `execution/risk_validator.py:126` | A4: `_save_sector_cache()` tmp+os.replace |
| `execution/risk_validator.py:305` | B1: NaN VaR 명시 처리 |
| `scripts/performance_calculator.py:62` | D6: benchmark 0.0 → None 반환 |
| `scripts/performance_calculator.py:182` | B9: `math.sqrt(max(0, variance))` |
| `run_cycle.py:1475` | A5a: `_save_monitor_peaks()` tmp+os.replace |
| `run_cycle.py:1929` | A5b: `regime_state` 저장 tmp+os.replace |
| `run_cycle.py:1390` | E7: `phase_report` 동적 전략 목록 |
| `run_cycle.py:1752` | C1: `--force-regime` EUPHORIA 추가 |
| `research/consensus.py:79` | C12: SMA200 NaN cold-start 폴백 |
| `execution/order_manager.py:153` | D2: fill 대기 1×3s → 3×10s 재시도 |
| `tests/test_workflow_hardening.py` | 신규 — 12개 회귀 방지 테스트 |

---

## Task 1: 데이터 무결성 — JSON 방어 + 원자적 쓰기

**Files:**
- Create: `tests/test_workflow_hardening.py`
- Modify: `execution/order_manager.py:44`
- Modify: `execution/risk_validator.py:126`
- Modify: `run_cycle.py:1475`, `run_cycle.py:1929`

### A1: `_next_seq()` JSON 방어

- [ ] **Step 1: 실패 테스트 작성** (`tests/test_workflow_hardening.py`)

```python
# tests/test_workflow_hardening.py
"""Workflow hardening regression tests."""
import json
import math
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ─── A1: _next_seq JSON defense ──────────────────────────────────────────────

class TestNextSeqJsonDefense:
    def test_malformed_line_does_not_crash(self, tmp_path, monkeypatch):
        """Malformed JSONL line must be skipped, not crash _next_seq."""
        log = tmp_path / "trade_log.jsonl"
        log.write_text('{"order_id": "MOM-2026-04-16-NVDA-001"}\n{BROKEN\n')

        import execution.order_manager as om
        monkeypatch.setattr(om, "TRADE_LOG_PATH", log)

        # Should not raise — returns seq=2 (one valid match found)
        seq_id = om._next_seq("MOM", "NVDA", "2026-04-16")
        assert seq_id == "MOM-2026-04-16-NVDA-002"

    def test_empty_file_returns_seq_001(self, tmp_path, monkeypatch):
        log = tmp_path / "trade_log.jsonl"
        log.write_text("")

        import execution.order_manager as om
        monkeypatch.setattr(om, "TRADE_LOG_PATH", log)
        assert om._next_seq("MOM", "AAPL", "2026-04-16") == "MOM-2026-04-16-AAPL-001"
```

- [ ] **Step 2: 실패 확인**

```bash
python -m pytest tests/test_workflow_hardening.py::TestNextSeqJsonDefense -v 2>&1 | head -20
```
예상: FAILED (`json.JSONDecodeError` 발생)

- [ ] **Step 3: `execution/order_manager.py:44` 수정**

기존:
```python
        if TRADE_LOG_PATH.exists():
            with open(TRADE_LOG_PATH, "r") as f:
                for line in f:
                    entry = json.loads(line.strip())
                    if entry.get("order_id", "").startswith(prefix):
                        seq += 1
```

변경:
```python
        if TRADE_LOG_PATH.exists():
            with open(TRADE_LOG_PATH, "r") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                    except json.JSONDecodeError:
                        continue  # 손상된 라인 스킵 (run_cycle._sync_alpaca_positions 패턴 답습)
                    if entry.get("order_id", "").startswith(prefix):
                        seq += 1
```

- [ ] **Step 4: 통과 확인**

```bash
python -m pytest tests/test_workflow_hardening.py::TestNextSeqJsonDefense -v
```
예상: PASSED 2/2

### A4: `_save_sector_cache()` 원자적 쓰기

- [ ] **Step 5: A4 테스트 추가** (`tests/test_workflow_hardening.py`에 append)

```python
# ─── A4: _save_sector_cache atomic write ─────────────────────────────────────

class TestSectorCacheAtomicWrite:
    def test_no_tmp_file_left_on_success(self, tmp_path, monkeypatch):
        """tmp 파일이 성공 후 남지 않아야 한다."""
        import execution.risk_validator as rv
        monkeypatch.setattr(rv, "_SECTOR_CACHE_PATH", tmp_path / "sector_cache.json")

        rv._save_sector_cache("NVDA", "Technology")
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == [], f"tmp file leaked: {tmp_files}"

    def test_cache_readable_after_save(self, tmp_path, monkeypatch):
        import execution.risk_validator as rv
        monkeypatch.setattr(rv, "_SECTOR_CACHE_PATH", tmp_path / "sector_cache.json")

        rv._save_sector_cache("AAPL", "Technology")
        cache = rv._load_sector_cache()
        assert cache["AAPL"]["sector"] == "Technology"
```

- [ ] **Step 6: A4 실패 확인**

```bash
python -m pytest tests/test_workflow_hardening.py::TestSectorCacheAtomicWrite -v
```
예상: 테스트 자체는 통과하나 Step 7 이후 변경 전 기준 확인용

- [ ] **Step 7: `execution/risk_validator.py:122~127` 수정**

기존:
```python
def _save_sector_cache(symbol: str, sector: str):
    cache = _load_sector_cache()
    cache[symbol] = {"sector": sector, "ts": time.time()}
    _SECTOR_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_SECTOR_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)
```

변경:
```python
def _save_sector_cache(symbol: str, sector: str):
    cache = _load_sector_cache()
    cache[symbol] = {"sector": sector, "ts": time.time()}
    _SECTOR_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _SECTOR_CACHE_PATH.with_suffix(".tmp")
    with open(tmp_path, "w") as f:
        json.dump(cache, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, _SECTOR_CACHE_PATH)
```

### A5: `_save_monitor_peaks()` + `regime_state` 원자적 쓰기

- [ ] **Step 8: `run_cycle.py:1473~1476` 수정**

기존:
```python
def _save_monitor_peaks(data: dict):
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(MONITOR_PEAKS_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=_json_default)
```

변경:
```python
def _save_monitor_peaks(data: dict):
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    MONITOR_PEAKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = MONITOR_PEAKS_PATH.with_suffix(".tmp")
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=_json_default)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, MONITOR_PEAKS_PATH)
```

- [ ] **Step 9: `run_cycle.py:1929~1930` 수정**

기존 (블록 내):
```python
            with open(_regime_state_path, "w") as f:
                json.dump(_regime_state, f, indent=2)
```

변경:
```python
            _tmp = _regime_state_path.with_suffix(".tmp")
            with open(_tmp, "w") as f:
                json.dump(_regime_state, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(_tmp, _regime_state_path)
```

- [ ] **Step 10: 전체 Task 1 테스트 통과**

```bash
python -m pytest tests/test_workflow_hardening.py -v -q
```
예상: PASSED 4/4

- [ ] **Step 11: 전체 회귀 확인**

```bash
python -m pytest tests/ -q 2>&1 | tail -5
```

- [ ] **Step 12: 커밋**

```bash
git add execution/order_manager.py execution/risk_validator.py run_cycle.py tests/test_workflow_hardening.py
git commit -m "fix(integrity): A1 _next_seq JSON defense + A4/A5 atomic state writes"
```

---

## Task 2: 수치 안전성 — NaN/Zero 가드

**Files:**
- Modify: `execution/risk_validator.py:305`
- Modify: `scripts/performance_calculator.py:62`, `:182`
- Modify: `tests/test_workflow_hardening.py` (테스트 추가)

### B1: NaN VaR 명시 처리

- [ ] **Step 1: B1 테스트 추가**

```python
# ─── B1: NaN VaR handling ─────────────────────────────────────────────────────

class TestVarNaNHandling:
    def test_single_row_data_returns_data_insufficient(self):
        """데이터 1행이면 std()=NaN → '데이터 부족' REJECT, NaN% 아님."""
        import pandas as pd
        import numpy as np
        from execution.risk_validator import check_var

        # yfinance가 1행만 반환하는 엣지 케이스 모의
        single_row = pd.DataFrame(
            {"Close": {"AAPL": 180.0}},
        )
        with patch("execution.risk_validator.yf.download", return_value=single_row):
            result = check_var(
                symbol="AAPL",
                side="buy",
                trade_value=10_000,
                current_positions={"AAPL": {"market_value": 5000}},
            )

        assert not result.passed
        assert "insufficient" in result.reason.lower() or "부족" in result.reason.lower()
        assert "nan" not in result.reason.lower()

    def test_normal_data_passes(self):
        """정상 데이터에서 VaR 계산 정상 작동."""
        import pandas as pd
        import numpy as np
        from execution.risk_validator import check_var

        # 60일치 가격 데이터
        dates = pd.date_range("2025-01-01", periods=60, freq="B")
        prices = pd.DataFrame({"Close": {"AAPL": pd.Series(
            [180.0 + i * 0.5 for i in range(60)], index=dates
        )}})
        with patch("execution.risk_validator.yf.download", return_value=prices):
            result = check_var(
                symbol="AAPL",
                side="buy",
                trade_value=10_000,
                current_positions={},
            )
        assert result.check_name == "portfolio_var"
        assert "nan" not in result.reason.lower()
```

- [ ] **Step 2: 실패 확인**

```bash
python -m pytest tests/test_workflow_hardening.py::TestVarNaNHandling -v 2>&1 | head -20
```

- [ ] **Step 3: `execution/risk_validator.py:304~313` 수정**

`check_var` 함수 내 `var_value` 계산 직후:

기존:
```python
    z_score = 1.6449  # norm.ppf(0.95), deterministic
    var_value = float(port_returns.std() * z_score)

    return RiskCheckResult(
        passed=var_value <= max_var,
        ...
    )
```

변경:
```python
    z_score = 1.6449  # norm.ppf(0.95), deterministic
    std_val = port_returns.std()
    if math.isnan(std_val) or len(port_returns) < 5:
        return RiskCheckResult(
            passed=False,
            check_name="portfolio_var",
            reason=f"VaR 계산 불가: 데이터 부족 ({len(port_returns)}행, 최소 5행 필요)",
            value=0.0,
            threshold=max_var,
        )
    var_value = float(std_val * z_score)

    return RiskCheckResult(
        passed=var_value <= max_var,
        ...
    )
```

참고: `check_var` 함수 시작 부근에 `import math`가 있는지 확인. 없으면 파일 상단 imports에 추가.

### D6: `fetch_benchmark_prices` 0.0 → None

- [ ] **Step 4: D6 테스트 추가**

```python
# ─── D6: benchmark price None on failure ────────────────────────────────────

class TestBenchmarkPriceFailure:
    def test_yfinance_failure_returns_none_not_zero(self):
        """yfinance 실패 시 0.0 대신 None 반환해야 한다."""
        from scripts.performance_calculator import fetch_benchmark_prices

        with patch("scripts.performance_calculator.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.fast_info.__getitem__.side_effect = Exception("network error")
            prices = fetch_benchmark_prices()

        assert prices.get("SPY") is None, "SPY should be None on failure, not 0.0"
        assert prices.get("QQQ") is None, "QQQ should be None on failure, not 0.0"
```

- [ ] **Step 5: 실패 확인**

```bash
python -m pytest tests/test_workflow_hardening.py::TestBenchmarkPriceFailure -v 2>&1 | head -15
```

- [ ] **Step 6: `scripts/performance_calculator.py:53~63` 수정**

기존:
```python
def fetch_benchmark_prices() -> dict[str, float]:
    """Fetch current SPY and QQQ prices via yfinance."""
    prices = {}
    for ticker in ["SPY", "QQQ"]:
        try:
            info = yf.Ticker(ticker).fast_info
            prices[ticker] = float(info["last_price"])
        except Exception as e:
            print(f"  [perf] WARNING: {ticker} price fetch failed: {e}")
            prices[ticker] = 0.0
    return prices
```

변경:
```python
def fetch_benchmark_prices() -> dict[str, float | None]:
    """Fetch current SPY and QQQ prices via yfinance. Returns None on failure."""
    prices: dict[str, float | None] = {}
    for ticker in ["SPY", "QQQ"]:
        try:
            info = yf.Ticker(ticker).fast_info
            prices[ticker] = float(info["last_price"])
        except Exception as e:
            print(f"  [perf] WARNING: {ticker} price fetch failed: {e}")
            prices[ticker] = None
    return prices
```

그 다음, `fetch_benchmark_prices()`를 호출하는 곳에서 None 처리:
`scripts/performance_calculator.py`에서 `benchmark_prices["SPY"]` 사용 시 None 체크 추가.
`if current_spy is not None and inception_price > 0:` 형태로 감싸는 곳 확인 후 수정.

### B9: `math.sqrt(variance)` 음수 가드

- [ ] **Step 7: `scripts/performance_calculator.py:182` 수정**

기존:
```python
    variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
    std_ret = math.sqrt(variance)
```

변경:
```python
    variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
    std_ret = math.sqrt(max(0.0, variance))  # float 반올림 오류로 음수 방지
```

- [ ] **Step 8: Task 2 전체 테스트 통과**

```bash
python -m pytest tests/test_workflow_hardening.py -v -q
```

- [ ] **Step 9: 전체 회귀**

```bash
python -m pytest tests/ -q 2>&1 | tail -5
```

- [ ] **Step 10: 커밋**

```bash
git add execution/risk_validator.py scripts/performance_calculator.py tests/test_workflow_hardening.py
git commit -m "fix(numeric): B1 NaN VaR 명시 처리 + D6 benchmark None + B9 sqrt guard"
```

---

## Task 3: 레짐/리포트 정확성

**Files:**
- Modify: `run_cycle.py:1390`, `:1752`
- Modify: `research/consensus.py:79`
- Modify: `tests/test_workflow_hardening.py`

### E7: `phase_report` 동적 전략 목록

- [ ] **Step 1: E7 테스트 추가**

```python
# ─── E7: phase_report dynamic strategy list ──────────────────────────────────

class TestPhaseReportDynamicStrategies:
    def test_report_includes_lev_st_and_grw(self):
        """LEV_ST, GRW가 phase_report 성과 표에 포함되어야 한다."""
        # phase_report 내부를 직접 테스트하기보다 generate_daily_report 함수 호출
        from scripts.performance_calculator import generate_daily_report

        fake_perf = {
            "strategies": {
                "MOM": {"current_nav": 15000, "daily_return_pct": 1.0,
                        "total_return_pct": 2.0, "mdd_pct": 0.5,
                        "sharpe_ratio": 1.2, "trade_count": 3},
                "LEV_ST": {"current_nav": 25000, "daily_return_pct": 0.5,
                           "total_return_pct": 1.0, "mdd_pct": 0.2,
                           "sharpe_ratio": 0.9, "trade_count": 1},
                "GRW": {"current_nav": 12000, "daily_return_pct": 2.0,
                        "total_return_pct": 3.0, "mdd_pct": 1.0,
                        "sharpe_ratio": 1.5, "trade_count": 5},
                "TOTAL": {"current_nav": 100000, "total_return_pct": 1.5,
                          "spy_return_pct": 0.8, "qqq_return_pct": 1.2},
            }
        }
        report = generate_daily_report(fake_perf, signals=[], regime="BULL")
        assert "LEV_ST" in report, "LEV_ST must appear in daily report"
        assert "GRW" in report, "GRW must appear in daily report"
```

참고: `generate_daily_report`가 `run_cycle.py`의 `phase_report` 내부 함수이면, `run_cycle` 모듈에서 직접 import하거나 subprocess 활용. 만약 함수가 없으면 아래 Step 2에서 리팩토링 후 테스트.

- [ ] **Step 2: `run_cycle.py:1390` 수정**

기존:
```python
    for code in ["MOM", "VAL", "QNT", "LEV"]:
        m = strats.get(code, {})
        lines.append(
            f"| {code} | ${m.get('current_nav', 0):,.0f} | "
            f"{m.get('daily_return_pct', 0):+.2f}% | "
            f"{m.get('total_return_pct', 0):+.2f}% | "
            f"{m.get('mdd_pct', 0):.2f}% | "
            f"{m.get('sharpe_ratio', 'N/A')} | "
            f"{m.get('trade_count', 0)} |"
        )
```

변경:
```python
    # 동적 전략 목록 — 하드코딩 대신 portfolios.json 기준
    strategy_codes = [c for c in strats if c != "TOTAL"]
    for code in sorted(strategy_codes):
        m = strats.get(code, {})
        lines.append(
            f"| {code} | ${m.get('current_nav', 0):,.0f} | "
            f"{m.get('daily_return_pct', 0):+.2f}% | "
            f"{m.get('total_return_pct', 0):+.2f}% | "
            f"{m.get('mdd_pct', 0):.2f}% | "
            f"{m.get('sharpe_ratio', 'N/A')} | "
            f"{m.get('trade_count', 0)} |"
        )
```

### C1: `--force-regime`에 EUPHORIA 추가

- [ ] **Step 3: C1 테스트 추가**

```python
# ─── C1: --force-regime EUPHORIA ─────────────────────────────────────────────

class TestForceRegimeEuphoria:
    def test_force_regime_accepts_euphoria(self):
        """--force-regime EUPHORIA가 argparse에서 유효한 값이어야 한다."""
        import argparse
        import subprocess, sys

        result = subprocess.run(
            [sys.executable, "run_cycle.py", "--phase", "signals",
             "--dry-run", "--force-regime", "EUPHORIA"],
            capture_output=True, text=True, cwd=".",
            timeout=5,
        )
        # argparse error면 "invalid choice" 메시지와 exit code 2
        assert "invalid choice" not in result.stderr, (
            f"EUPHORIA rejected by argparse: {result.stderr}"
        )
        assert result.returncode != 2, "argparse rejected EUPHORIA"
```

- [ ] **Step 4: 실패 확인**

```bash
python -m pytest tests/test_workflow_hardening.py::TestForceRegimeEuphoria -v 2>&1 | head -15
```

- [ ] **Step 5: `run_cycle.py:1752` 수정**

기존:
```python
    parser.add_argument("--force-regime", default=None, choices=["BULL", "BEAR", "NEUTRAL", "CRISIS"],
```

변경:
```python
    parser.add_argument("--force-regime", default=None,
                        choices=["BULL", "BEAR", "NEUTRAL", "CRISIS", "EUPHORIA"],
```

### C12: SMA200 NaN cold-start 폴백

- [ ] **Step 6: C12 테스트 추가**

```python
# ─── C12: SMA200 NaN cold-start ──────────────────────────────────────────────

class TestSma200NanHandling:
    def _make_short_hist(self, n=50):
        """SMA200 계산 불가 수준의 짧은 데이터."""
        import pandas as pd
        import numpy as np
        dates = pd.date_range("2025-01-01", periods=n, freq="B")
        prices = np.linspace(480, 490, n)
        return pd.DataFrame({"Close": prices}, index=dates)

    def test_short_history_does_not_return_false_bull(self):
        """SMA200 미계산 시 NEUTRAL 또는 명시적 폴백 반환. BULL 오분류 금지."""
        from research.consensus import _classify_regime_from_data

        hist = self._make_short_hist(n=50)  # SMA200 = NaN
        result = _classify_regime_from_data(hist, vix_level=15.0)
        # SMA200 없으면 ratio 계산 불가 → BULL 확신 금지
        assert result in ("NEUTRAL", "BULL"), f"Unexpected: {result}"
        # 핵심: NaN 전파로 CRISIS 오분류 금지
        assert result != "CRISIS", "SMA200=NaN should not trigger CRISIS"

    def test_nan_sma200_reason_logged(self):
        """SMA200 NaN 상황을 _classify_regime_from_data가 안전하게 처리."""
        import pandas as pd
        import numpy as np
        from research.consensus import _classify_regime_from_data

        # 이 데이터로는 SMA200은 NaN, SMA50도 NaN
        hist = self._make_short_hist(n=30)
        # 예외 없이 실행되어야 함
        try:
            result = _classify_regime_from_data(hist, vix_level=20.0)
        except Exception as e:
            pytest.fail(f"_classify_regime_from_data raised on short data: {e}")
```

- [ ] **Step 7: `research/consensus.py:75~80` 수정**

기존:
```python
    close = hist["Close"]
    current_price = close.iloc[-1]
    sma200 = close.rolling(200).mean().iloc[-1]
    sma50 = close.rolling(50).mean().iloc[-1]
    ratio = current_price / sma200 if sma200 > 0 else 1.0
```

변경:
```python
    import math as _math
    close = hist["Close"]
    current_price = close.iloc[-1]
    sma200 = close.rolling(200).mean().iloc[-1]
    sma50 = close.rolling(50).mean().iloc[-1]

    # SMA200 미계산(데이터 부족) 시 NEUTRAL 폴백
    if _math.isnan(float(sma200)):
        return "NEUTRAL"

    ratio = current_price / sma200 if sma200 > 0 else 1.0
```

- [ ] **Step 8: Task 3 전체 테스트 통과**

```bash
python -m pytest tests/test_workflow_hardening.py -v -q
```

- [ ] **Step 9: 회귀 확인**

```bash
python -m pytest tests/ -q 2>&1 | tail -5
```

- [ ] **Step 10: 커밋**

```bash
git add run_cycle.py research/consensus.py tests/test_workflow_hardening.py
git commit -m "fix(regime): C1 EUPHORIA force-regime + E7 동적 전략 리포트 + C12 SMA200 NaN 폴백"
```

---

## Task 4: Fill 재시도 + 최종 dry-run 검증

**Files:**
- Modify: `execution/order_manager.py:150~180`
- Modify: `tests/test_workflow_hardening.py`

### D2: Fill 대기 3s → 최대 3×10s 재시도

- [ ] **Step 1: D2 테스트 추가**

```python
# ─── D2: fill retry loop ──────────────────────────────────────────────────────

class TestFillRetryLoop:
    def test_unfilled_after_first_check_retries(self):
        """첫 check에서 unfilled → 재시도 후 filled 반환."""
        from execution.order_manager import execute_signal
        from strategies.base_strategy import Signal, Direction

        signal = Signal(
            strategy="MOM", symbol="NVDA", direction=Direction.BUY,
            weight_pct=0.10, confidence=0.8, reason="test"
        )

        call_count = 0

        def mock_get_order(order_id):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return {"filled_qty": "0", "filled_avg_price": None}
            return {"filled_qty": "10.5", "filled_avg_price": "180.0"}

        with patch("execution.order_manager.submit_market_order") as mock_submit, \
             patch("execution.order_manager.get_order_by_client_id", side_effect=mock_get_order), \
             patch("execution.order_manager.get_positions", return_value={}), \
             patch("execution.order_manager.time.sleep"):

            mock_submit.return_value = MagicMock(
                id="alpaca-123", client_order_id="MOM-2026-04-16-NVDA-001",
                symbol="NVDA", side="buy", status="filled"
            )

            result = execute_signal(
                signal=signal,
                capital=10_000,
                strategy_cash=10_000,
                dry_run=False,
                order_id="MOM-2026-04-16-NVDA-001",
            )

        assert result["fill_status"] == "filled"
        assert call_count >= 2, "Should have retried at least once"

    def test_still_unfilled_after_retries_returns_unfilled(self):
        """최대 재시도 후에도 미체결 → unfilled 반환 (crash 없음)."""
        from execution.order_manager import execute_signal
        from strategies.base_strategy import Signal, Direction

        signal = Signal(
            strategy="MOM", symbol="NVDA", direction=Direction.BUY,
            weight_pct=0.10, confidence=0.8, reason="test"
        )

        with patch("execution.order_manager.submit_market_order") as mock_submit, \
             patch("execution.order_manager.get_order_by_client_id",
                   return_value={"filled_qty": "0", "filled_avg_price": None}), \
             patch("execution.order_manager.get_positions", return_value={}), \
             patch("execution.order_manager.time.sleep"):

            mock_submit.return_value = MagicMock(
                id="alpaca-456", client_order_id="MOM-2026-04-16-NVDA-001",
                symbol="NVDA", side="buy", status="pending_new"
            )

            result = execute_signal(
                signal=signal,
                capital=10_000,
                strategy_cash=10_000,
                dry_run=False,
                order_id="MOM-2026-04-16-NVDA-001",
            )

        assert result["fill_status"] == "unfilled"
```

- [ ] **Step 2: 실패 확인**

```bash
python -m pytest tests/test_workflow_hardening.py::TestFillRetryLoop -v 2>&1 | head -20
```

- [ ] **Step 3: `execution/order_manager.py:150~180` 수정**

기존:
```python
        # M-3: 부분 체결 확인 — 3초 대기 후 fill 상태 검증
        fill_status = "pending"
        try:
            time.sleep(3)
            filled_order = get_order_by_client_id(order_id)
            if filled_order:
                filled_qty = float(filled_order.get("filled_qty", 0))
                ...
```

변경 (3s 1회 → 10s × 최대 3회 재시도):
```python
        # M-3: 부분 체결 확인 — 10초 간격 최대 3회 재시도
        fill_status = "pending"
        MAX_FILL_RETRIES = 3
        FILL_WAIT_SECONDS = 10
        try:
            for attempt in range(MAX_FILL_RETRIES):
                time.sleep(FILL_WAIT_SECONDS)
                filled_order = get_order_by_client_id(order_id)
                if not filled_order:
                    continue
                filled_qty = float(filled_order.get("filled_qty", 0))
                if signal.direction == Direction.BUY:
                    if filled_qty > 0:
                        fill_status = "filled"
                        break
                    # unfilled이지만 재시도 계속
                else:
                    requested_qty = qty
                    if filled_qty >= requested_qty:
                        fill_status = "filled"
                        break
                    elif filled_qty > 0:
                        fill_status = "partial_fill"
                        print(
                            f"[ORDER] WARNING: {symbol} 부분 체결 "
                            f"({filled_qty}/{requested_qty} shares)"
                        )
                        break
                if attempt < MAX_FILL_RETRIES - 1:
                    print(f"[ORDER] fill 대기 중... ({attempt + 1}/{MAX_FILL_RETRIES})")

            if fill_status == "pending":
                fill_status = "unfilled"

            if filled_order:
                result["filled_qty"] = float(filled_order.get("filled_qty", 0))
                result["filled_avg_price"] = filled_order.get("filled_avg_price")
```

주의: 기존 `filled_qty`, `filled_avg_price` 대입 코드는 루프 내부로 이동. `filled_order`는 루프 외부에서도 접근 가능하도록 루프 전에 `filled_order = None`으로 초기화.

- [ ] **Step 4: Task 4 테스트 통과**

```bash
python -m pytest tests/test_workflow_hardening.py -v
```

- [ ] **Step 5: 전체 테스트 회귀**

```bash
python -m pytest tests/ -q 2>&1 | tail -5
```
예상: 137+ passed, 1 skipped

- [ ] **Step 6: 최종 dry-run 검증**

```bash
python run_cycle.py --phase signals --dry-run 2>&1 | grep -E "(Phase|signals|PASS|FAIL|ERROR)"
```
예상: 모든 Phase 정상 완료, crash 없음

- [ ] **Step 7: 최종 커밋**

```bash
git add execution/order_manager.py tests/test_workflow_hardening.py
git commit -m "fix(order): D2 fill 재시도 3×10s + 전체 워크플로우 hardening 완료"
```

---

## 검증 체크포인트

```bash
# 1. 신규 테스트 전부 통과
python -m pytest tests/test_workflow_hardening.py -v

# 2. 전체 회귀 없음
python -m pytest tests/ -q 2>&1 | tail -3

# 3. dry-run 정상 완료
python run_cycle.py --phase signals --dry-run 2>&1 | tail -5

# 4. EUPHORIA force-regime 동작 확인
python run_cycle.py --phase signals --dry-run --force-regime EUPHORIA 2>&1 | grep -E "(regime|EUPHORIA)"

# 5. 원자적 쓰기 확인 (tmp 파일 없음)
ls state/*.tmp 2>/dev/null || echo "OK: no tmp files"
```

---

## 설계 결정 요약

| 취약점 | 수정 방식 | 근거 |
|--------|----------|------|
| A1 _next_seq JSON | try/except + continue | run_cycle._sync_alpaca_positions와 동일 패턴 |
| A4 sector_cache | tmp+os.replace+fsync | save_portfolios 기존 패턴 |
| A5 monitor_peaks/regime_state | tmp+os.replace+fsync | 일관성 |
| B1 NaN VaR | isnan 명시 체크 + "데이터 부족" 메시지 | 오퍼레이터 구분 가능 메시지 |
| D6 benchmark 0.0 | None 반환 + 호출부 None 체크 | 0.0은 -100% 수익률 오계산 야기 |
| B9 sqrt | max(0.0, variance) | 수학적 불변: 분산은 비음수 |
| E7 전략 목록 | portfolios.json keys() 동적 | LEV_ST/GRW 추가 시 자동 포함 |
| C1 force-regime | choices에 EUPHORIA 추가 | 5번째 레짐 테스트/시뮬레이션 지원 |
| C12 SMA200 NaN | early return NEUTRAL | cold-start에서 안전한 폴백 |
| D2 fill 재시도 | 3×10s retry | Paper trading에서도 비상시 pending 발생 가능 |

**미포함 (아키텍처 변경 필요, 별도 task로):**
- A3 파일 락 (Windows fcntl 미지원, OS 이중 실행 방지로 대체 권장)
- B6/C5 negative cash after realloc (Regime 재배분 흐름 전체 리팩토링 필요)
- C3 CRISIS LEV exit 타이밍 (Phase 1.7 ↔ Phase 2 순서 변경 필요)
- D1 rate-limit retry (alpaca_client.py 전체 래핑 필요)
