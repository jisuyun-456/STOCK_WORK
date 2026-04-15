#!/usr/bin/env python3
"""Paper Trading Cycle -9-phase automated pipeline (Phase 2.5 Research Overlay).

Usage:
    python run_cycle.py --phase all              # Run full cycle
    python run_cycle.py --phase all --dry-run    # Simulate without orders
    python run_cycle.py --phase data             # Data fetch only
    python run_cycle.py --phase signals          # Generate signals only
    python run_cycle.py --phase research         # Research overlay only
    python run_cycle.py --phase risk             # Risk validation only
    python run_cycle.py --phase execute          # Execute approved signals
    python run_cycle.py --phase report           # Generate report only

    --research-mode {full|selective|skip}         # Research depth (default: full)
    --no-cache                                    # Bypass research cache

Phases:
    1.   DATA      -fetch market data + Alpaca positions
    2.   SIGNALS   -run strategy modules, generate signals
    2.5  RESEARCH  -Research Division 5-agent parallel analysis (NEW)
    3.   RISK      -validate each signal through risk gates
    3.5  APPEAL    -Risk-FAIL signals → Research appeal (NEW)
    4.   RESOLVE   -resolve conflicting signals (rule-based)
    5.   EXECUTE   -submit orders to Alpaca Paper API
    6.   REPORT    -update performance.json + daily report
    7.   COMMIT    -(handled by GitHub Actions, not this script)
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import socket
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# Windows cp949/euc-kr 콘솔에서 한글·유니코드 print 시 UnicodeEncodeError 방지
# 모든 하위 모듈(strategies, news, fundamentals 등)에 전역 적용
def _fix_console_encoding() -> None:
    for _stream_name in ("stdout", "stderr"):
        _stream = getattr(sys, _stream_name)
        if hasattr(_stream, "buffer"):
            _enc = (getattr(_stream, "encoding", None) or "").lower().replace("-", "")
            if _enc in ("cp949", "euckr", "mskr"):
                setattr(sys, _stream_name,
                        io.TextIOWrapper(_stream.buffer, encoding="utf-8", errors="replace"))

_fix_console_encoding()

# ─── Paths ───────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
STATE_DIR = ROOT / "state"
PORTFOLIOS_PATH = STATE_DIR / "portfolios.json"
PERFORMANCE_PATH = STATE_DIR / "performance.json"
SNAPSHOT_PATH = STATE_DIR / "snapshot.json"
REPORTS_DIR = ROOT / "reports" / "daily"
# N-HIGH/MEDIUM Phase A: operational state files
AUDIT_LOG_PATH = STATE_DIR / "audit_log.jsonl"
DEGRADED_COUNT_PATH = STATE_DIR / "degraded_count.json"
NETWORK_DOWN_FLAG = STATE_DIR / "network_down.flag"
STATE_BACKUP_DIR = STATE_DIR / "backup"


def _json_default(obj):
    """numpy 스칼라 타입을 native Python으로 변환 (Python 3.14 호환)."""
    if hasattr(obj, "item") and callable(obj.item):
        try:
            return obj.item()
        except Exception:
            pass
    if isinstance(obj, bool):
        return bool(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _ensure_inception(data: dict) -> dict:
    """C5 fix: portfolios.json에 inception 필드가 없으면 현재 allocated로 초기화.

    inception.total / inception.strategies 는 initial NAV 기준으로 사용되며,
    이후 절대 수정되지 않는다 (immutable). performance_calculator가 이 값을
    total_return_pct 분모로 사용한다.
    """
    if "inception" not in data:
        strategies = data.get("strategies", {})
        inception_strategies = {
            code: float(strat.get("allocated", 0))
            for code, strat in strategies.items()
        }
        total = sum(inception_strategies.values())
        # sanity check: 초기 자본은 $50k 이상이어야 함 (트레이딩 회사 기준)
        if total < 50000:
            print(
                f"[inception] WARNING: 현재 allocated 합 ${total:.0f} < $50k. "
                f"기본 $100,000을 inception으로 사용."
            )
            total = 100000
        data["inception"] = {
            "total": round(total, 2),
            "strategies": inception_strategies,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }
    return data


def load_portfolios() -> dict:
    """Load portfolios.json with atomic-write backup fallback.

    If the main file is corrupted (e.g., crashed mid-write), restore from
    .backup.json automatically. Raises only if both files are unrecoverable.
    """
    backup_path = PORTFOLIOS_PATH.with_suffix(".backup.json")
    try:
        text = PORTFOLIOS_PATH.read_text(encoding="utf-8")
        return _ensure_inception(json.loads(text))
    except (json.JSONDecodeError, FileNotFoundError, OSError) as e:
        if backup_path.exists():
            print(f"[load_portfolios] WARNING: 메인 파일 손상 ({e}) → 백업 복구")
            try:
                return _ensure_inception(json.loads(backup_path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError) as be:
                raise RuntimeError(
                    f"portfolios.json and backup both unrecoverable: main={e}, backup={be}"
                )
        raise


def save_portfolios(data: dict):
    """Atomically write portfolios.json with rotating backup.

    Steps:
      1. Copy existing file to .backup.json (pre-write snapshot)
      2. Write new content to .tmp.json
      3. os.replace() — atomic on both POSIX and Windows (Python 3.3+)

    If the process crashes during write, the original file is untouched.
    Load will fall back to backup if main file is ever corrupted.
    """
    data["last_updated"] = datetime.now(timezone.utc).isoformat()

    PORTFOLIOS_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Pre-write backup
    if PORTFOLIOS_PATH.exists():
        backup_path = PORTFOLIOS_PATH.with_suffix(".backup.json")
        try:
            shutil.copy2(PORTFOLIOS_PATH, backup_path)
        except OSError as e:
            print(f"[save_portfolios] WARNING: backup copy failed: {e}")

    # Atomic write via temp file + os.replace
    tmp_path = PORTFOLIOS_PATH.with_suffix(".tmp.json")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=_json_default)
        f.flush()
        try:
            os.fsync(f.fileno())
        except (OSError, AttributeError):
            pass  # fsync unavailable on some platforms
    os.replace(tmp_path, PORTFOLIOS_PATH)


# ─── N-HIGH/MEDIUM Phase A helpers ──────────────────────────────────────

def _audit_log(phase: str, action: str, payload: dict | None = None) -> None:
    """Append-only immutable audit log.

    Records who/when/what/why/result for every phase entry and exit.
    File MUST be append-only — never truncate or delete (Immutable Ledger principle).
    """
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "who": "bot",
            "phase": phase,
            "action": action,  # "start" | "end" | "error"
            "payload": payload or {},
        }
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=_json_default) + "\n")
    except Exception as e:
        # audit log failure must never crash the cycle
        print(f"  [audit] write failed: {e}")


def _network_healthcheck() -> bool:
    """Verify DNS resolution for critical hosts before starting the cycle.

    Retries with exponential backoff (10s → 30s → 90s). On final failure,
    writes state/network_down.flag and returns False. Caller decides whether
    to exit(2).
    """
    hosts = [
        "query2.finance.yahoo.com",
        "paper-api.alpaca.markets",
        "8.8.8.8",  # sanity check (Google DNS)
    ]
    delays = [10, 30, 90]

    for attempt, delay in enumerate([0] + delays):
        if delay:
            print(f"  [NETWORK] retry {attempt}/3 in {delay}s...")
            time.sleep(delay)
        failed = []
        for h in hosts:
            try:
                socket.gethostbyname(h)
            except socket.gaierror as e:
                failed.append(f"{h} ({e})")
        if not failed:
            # clear stale down flag on recovery
            if NETWORK_DOWN_FLAG.exists():
                try:
                    NETWORK_DOWN_FLAG.unlink()
                except OSError:
                    pass
            print(f"  [NETWORK] healthcheck OK ({len(hosts)} hosts)")
            return True
        print(f"  [NETWORK] DNS 실패: {', '.join(failed)}")

    # final failure
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        NETWORK_DOWN_FLAG.write_text(
            json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "failed_hosts": failed,
            }),
            encoding="utf-8",
        )
    except OSError:
        pass
    print("  [NETWORK] CRITICAL: 3회 재시도 모두 실패 — 사이클 중단")
    return False


def _track_degraded(is_degraded: bool) -> int:
    """Increment or reset degraded_count.json. Returns current consecutive count.

    Consecutive count ≥ 2 indicates persistent data quality failure and should
    trigger a warning on the next cycle start.
    """
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        current = {"consecutive": 0, "last_ts": None}
        if DEGRADED_COUNT_PATH.exists():
            try:
                current = json.loads(DEGRADED_COUNT_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        if is_degraded:
            current["consecutive"] = int(current.get("consecutive", 0)) + 1
        else:
            current["consecutive"] = 0
        current["last_ts"] = datetime.now(timezone.utc).isoformat()
        DEGRADED_COUNT_PATH.write_text(
            json.dumps(current, ensure_ascii=False), encoding="utf-8"
        )
        return int(current["consecutive"])
    except Exception as e:
        print(f"  [degraded] tracker failed: {e}")
        return 0


def _backup_state_files() -> None:
    """Daily snapshot of state/*.json into state/backup/YYYY-MM-DD/.

    Called at the end of main() so disaster recovery can roll back a day.
    Non-fatal — backup failures log a warning but never crash the cycle.
    """
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dest = STATE_BACKUP_DIR / today
        dest.mkdir(parents=True, exist_ok=True)
        count = 0
        for src in STATE_DIR.glob("*.json"):
            try:
                shutil.copy2(src, dest / src.name)
                count += 1
            except OSError as e:
                print(f"  [backup] copy {src.name} failed: {e}")
        # also backup audit log (append-only safety copy)
        if AUDIT_LOG_PATH.exists():
            try:
                shutil.copy2(AUDIT_LOG_PATH, dest / AUDIT_LOG_PATH.name)
                count += 1
            except OSError:
                pass
        print(f"  [backup] {count} files → state/backup/{today}/")
    except Exception as e:
        print(f"  [backup] failed: {e}")


def _check_allocation_integrity(portfolios: dict) -> bool:
    """Verify allocations sum is within 1% of inception.total (drift detection).

    Why: portfolios.json 은 auto-sync 로 account_total 만 갱신되고 각 전략의
    allocated 값은 고정이어야 한다. 만약 누군가 allocated 를 직접 수정하거나
    sync 로직이 잘못되면 전체 배분이 원본에서 드리프트할 수 있다.
    이 체크는 Immutable Ledger 원칙의 마지막 방어선이다.

    Returns True if integrity OK, False if drift detected (log + alert written).
    """
    inception = portfolios.get("inception", {})
    inception_total = float(inception.get("total", 0) or 0)
    if inception_total <= 0:
        return True  # inception not initialised yet — skip check

    strategies = portfolios.get("strategies", {})
    alloc_sum = sum(float(s.get("allocated", 0) or 0) for s in strategies.values())
    drift = abs(alloc_sum - inception_total) / inception_total
    if drift > 0.01:
        msg = (
            f"allocation drift {drift:.2%} "
            f"(sum=${alloc_sum:,.2f} vs inception=${inception_total:,.2f})"
        )
        print(f"  [CRITICAL] {msg}")
        portfolios.setdefault("alerts", []).append({
            "type": "allocation_drift",
            "drift_pct": round(drift, 4),
            "alloc_sum": round(alloc_sum, 2),
            "inception_total": round(inception_total, 2),
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        _audit_log("integrity", "drift", {
            "drift_pct": drift,
            "alloc_sum": alloc_sum,
            "inception_total": inception_total,
        })
        return False
    return True


def _check_inception_drift(portfolios: dict) -> None:
    """각 전략 allocated가 inception.strategies와 ±10% 이상 괴리시 경고.

    자동 reset 금지 — intentional 재분배와 버그 drift 구분 불가.
    수정은 `python scripts/reset_initial_nav.py`로 수동 진행.
    """
    inception_strats = (portfolios.get("inception", {}) or {}).get("strategies", {}) or {}
    for code, strat in (portfolios.get("strategies", {}) or {}).items():
        allocated = float(strat.get("allocated", 0) or 0)
        anchor = float(inception_strats.get(code, 0) or 0)
        if anchor <= 0 or allocated <= 0:
            continue
        drift = abs(allocated - anchor) / anchor
        if drift > 0.10:
            print(
                f"  [inception-drift] {code}: allocated=${allocated:,.0f} vs "
                f"inception=${anchor:,.0f} ({drift:.1%}) → "
                f"재분배 의도면 `python scripts/reset_initial_nav.py` 실행"
            )


def _check_negative_cash(portfolios: dict) -> list[dict]:
    """Detect strategies with negative cash balance (margin call risk).

    Threshold: -$10 allows for minor rounding. Anything below triggers
    a CRITICAL log and appends an alert to portfolios["alerts"].
    Returns the list of new alerts (empty if all strategies are clean).
    """
    new_alerts: list[dict] = []
    strategies = portfolios.get("strategies", {})
    for code, strat in strategies.items():
        cash = float(strat.get("cash", 0) or 0)
        if cash < -10:
            print(
                f"  [CRITICAL] {code} 음수 cash: ${cash:.2f} — margin call 위험"
            )
            alert = {
                "type": "negative_cash",
                "strategy": code,
                "amount": round(cash, 2),
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            new_alerts.append(alert)
    if new_alerts:
        portfolios.setdefault("alerts", []).extend(new_alerts)
    return new_alerts


# ─── Phase 1: DATA ──────────────────────────────────────────────────────

def phase_data() -> dict:
    """Fetch all market data for 4 strategies + news."""
    print("[Phase 1: DATA] Fetching market data...")

    from strategies.momentum import fetch_momentum_data

    market_data = fetch_momentum_data(days=400)
    prices = market_data.get("prices")

    if prices is not None and not prices.empty:
        print(f"  Fetched {len(prices.columns)} symbols, {len(prices)} days")
    else:
        print("  WARNING: No price data fetched")

    alpaca_positions = []
    alpaca_live = False
    try:
        from execution.alpaca_client import get_positions, get_account_info
        alpaca_positions = get_positions()
        account = get_account_info()
        print(f"  Alpaca account: ${account['equity']:,.2f} equity, mode={account['mode']}")
        alpaca_live = True
    except Exception as e:
        # C3 fix: Alpaca 연결 실패 시 BUY 전면 차단 플래그 설정.
        # 기존 버그: get_positions() 실패 → 빈 포지션 리스트 → 리스크 게이트가
        # "포지션 없음"으로 판단해 중복 BUY 승인.
        print(f"  [CRITICAL] Alpaca 연결 실패 — BUY 시그널 전면 차단: {e}")

    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbols_count": len(prices.columns) if prices is not None else 0,
        "days_count": len(prices) if prices is not None else 0,
        "alpaca_positions": alpaca_positions,
        "alpaca_live": alpaca_live,
    }
    # C3: 하위 phase에서 사용하도록 market_data에 플래그 전파
    market_data["alpaca_live"] = alpaca_live
    market_data["alpaca_unavailable"] = not alpaca_live

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(SNAPSHOT_PATH, "w") as f:
        json.dump(snapshot, f, indent=2, default=_json_default)

    # VAL: FMP + yfinance 재무 데이터
    try:
        from strategies.value_quality import fetch_value_data
        val_data = fetch_value_data()
        market_data["fundamentals"] = val_data.get("fundamentals", {})
        print(f"  VAL data: {len(market_data['fundamentals'])} stocks")
    except Exception as e:
        print(f"  VAL data fetch failed: {e}")
        market_data["fundamentals"] = {}

    # QNT: Kenneth French 팩터 데이터
    try:
        from strategies.quant_factor import fetch_factor_data
        qnt_data = fetch_factor_data()
        market_data["factors"] = qnt_data.get("factors")
        market_data["qnt_prices"] = qnt_data.get("prices")  # QNT 전용 가격 추가
        # N-MEDIUM-2: FF5 staleness 메타데이터 전파 (QNT strategy 가 signal 50% 축소에 사용)
        market_data["ff5_stale"] = qnt_data.get("ff5_stale", False)
        market_data["ff5_days_lag"] = qnt_data.get("ff5_days_lag", 0)
        print(f"  QNT factor data: {'loaded' if market_data['factors'] is not None else 'failed'}")
    except Exception as e:
        print(f"  QNT factor fetch failed: {e}")
        market_data["factors"] = None
        market_data["ff5_stale"] = False
        market_data["ff5_days_lag"] = 0

    # LEV (Core-Satellite Barbell 재설계 2026-04-11):
    # 재설계된 LEV 전략은 regime 과 current_positions 만으로 동작하며
    # 외부 가격 데이터를 요구하지 않는다 (SMA 계산 제거).
    # 호환용 빈 dict 주입.
    market_data["leveraged"] = {"prices": None}

    # 뉴스 수집 (yfinance + 6개 RSS 소스 병합)
    try:
        from news.fetcher import fetch_macro_news_enhanced
        macro_articles = fetch_macro_news_enhanced()
        market_data["news"] = {"_MACRO": macro_articles}
        sources = set(a.get("source", "?") for a in macro_articles)
        print(f"  Macro news: {len(macro_articles)} articles from {sources}")
    except Exception as e:
        print(f"  News fetch failed: {e}")
        market_data["news"] = {}

    # 기술지표 계산 (Phase 8: RSI, MACD, Bollinger, Volume)
    try:
        from strategies.indicators import compute_indicators
        indicators = {}
        if prices is not None and not prices.empty:
            volumes = market_data.get("volumes")
            for symbol in prices.columns:
                try:
                    series = prices[symbol].dropna()
                    if len(series) >= 50:
                        vol_series = volumes[symbol] if volumes is not None and symbol in volumes.columns else None
                        indicators[symbol] = compute_indicators(series, vol_series)
                except Exception:
                    indicators[symbol] = {}
        market_data["indicators"] = indicators
        print(f"  Indicators: {len(indicators)} symbols computed")
    except Exception as e:
        print(f"  Indicators computation failed: {e}")
        market_data["indicators"] = {}

    # N-HIGH-1: data quality degraded flag
    # If fewer than 50% of expected symbols were fetched, mark as degraded.
    try:
        from strategies import momentum as _mom
        expected = len(_mom.NASDAQ_100_SUBSET)
    except Exception:
        expected = 0
    actual = len(prices.columns) if prices is not None else 0
    if expected > 0 and actual < expected * 0.5:
        market_data["data_quality"] = "degraded"
        print(
            f"  [CRITICAL] 데이터 품질 저하: {actual}/{expected} 종목만 수집 "
            f"(임계 {expected // 2}) — 사이클 중단 권장"
        )
        consec = _track_degraded(True)
        if consec >= 2:
            print(
                f"  [CRITICAL] degraded {consec}회 연속 발생 — 즉시 조사 필요"
            )
    else:
        market_data["data_quality"] = "ok"
        _track_degraded(False)

    return market_data


# ─── Phase 1.5: REGIME ──────────────────────────────────────────────────

def phase_regime(market_data: dict, force_regime: str | None = None) -> tuple:
    """Phase 1.5: Regime Detection + Dynamic Allocation.

    Args:
        force_regime: If set, override live detection for simulation/testing.
                      Choices: BULL, BEAR, NEUTRAL, CRISIS.
    """
    print("[Phase 1.5: REGIME] Detecting market regime...")

    # 뉴스 감성 분석
    news_sentiment_score = 0.0
    try:
        from news.sentiment import analyze_sentiment
        macro_news = market_data.get("news", {}).get("_MACRO", [])
        if macro_news:
            result = analyze_sentiment("_MACRO", macro_news)
            news_sentiment_score = result.score
            print(f"  News sentiment: {news_sentiment_score:+.2f} ({result.summary})")
        else:
            print("  News sentiment: 0.00 (no macro news)")
    except Exception as e:
        print(f"  News sentiment failed: {e} (using 0.0)")

    # Polymarket 예측시장 데이터 (Phase 9)
    polymarket_score = None  # None = no data, 0.0 = neutral
    try:
        from research.polymarket import fetch_macro_markets, compute_polymarket_score
        pm_signals = fetch_macro_markets(max_markets=20)
        polymarket_score = compute_polymarket_score(pm_signals)
        market_data["polymarket"] = [
            {"question": s.question, "probabilities": s.probabilities, "volume": s.volume_usd}
            for s in pm_signals
        ]
        print(f"  Polymarket: score={polymarket_score:+.2f} ({len(pm_signals)} markets)")
    except Exception as e:
        print(f"  Polymarket fetch failed: {e} (score=None, excluded from regime)")

    # 확장된 Regime Detection (뉴스 + Polymarket)
    try:
        from research.consensus import detect_regime_enhanced
        regime_info = detect_regime_enhanced(news_sentiment_score, polymarket_score)
    except Exception as e:
        print(f"  Regime detection failed: {e}")
        from research.models import RegimeDetection
        regime_info = RegimeDetection(
            regime="NEUTRAL", sp500_vs_sma200=1.0, vix_level=20.0,
            reasoning=f"Fallback: {e}", timestamp=datetime.now(timezone.utc).isoformat()
        )

    # --force-regime: override detection result before allocation
    if force_regime:
        print(f"  [force-regime] {regime_info.regime} → {force_regime} (allocator override)")
        regime_info.regime = force_regime

    # 동적 배분
    from strategies.regime_allocator import allocate

    portfolios = load_portfolios()
    total = portfolios.get("account_total", 100000)
    allocations = allocate(regime_info.regime, total)

    # Apply CASH allocation: reduce strategy allocations and update portfolios.json
    cash_amount = allocations.pop("CASH", 0)
    if cash_amount > 0:
        print(f"  CASH reserve: ${cash_amount:,.0f} (not deployed)")
        # Update each strategy's allocated amount in portfolios.json
        for code in ["MOM", "VAL", "QNT", "LEV", "LEV_ST"]:
            if code in allocations and code in portfolios["strategies"]:
                portfolios["strategies"][code]["allocated"] = allocations[code]
        save_portfolios(portfolios)

    print(f"  Regime: {regime_info.regime} | VIX: {regime_info.vix_level}")
    print(f"  Allocations: {', '.join(f'{k}=${v:,.0f}' for k, v in allocations.items())}")

    return regime_info, allocations


# ─── Phase 2: SIGNALS ───────────────────────────────────────────────────

# Strategy-specific stop-loss thresholds (C2 enforcement)
# LEV 는 Regime 에 따라 동적으로 결정되므로 여기서 제외하고 _get_strategy_stop_loss() 에서 분기.
STRATEGY_STOP_LOSS: dict[str, float] = {
    "MOM": -0.10,   # -10%
    "VAL": -0.12,   # -12% (slower rotation)
    "QNT": -0.10,   # -10%
    # "LEV" 는 strategies.leveraged_etf.LeveragedETFStrategy.get_stop_loss_for_regime() 로 동적 결정
}


def _get_strategy_stop_loss(code: str, regime: str) -> float:
    """전략별 stop-loss 임계값. LEV 는 regime 동적, 나머지는 STRATEGY_STOP_LOSS 고정.

    LEV 의 regime 별 stop-loss:
      BULL: -30%, NEUTRAL: -20%, BEAR/CRISIS: None (regime 전환으로 강제 청산)

    None 이면 사실상 손절 무효화 (-0.99 반환 → 포지션이 99% 손실 전엔 트리거 안 됨).
    BEAR/CRISIS 는 regime 전환 자체가 leveraged_etf.generate_signals() 에서
    target_mix 변화로 SELL 신호를 만들어 자연스럽게 청산하므로 별도 stop-loss 불필요.
    """
    if code == "LEV":
        from strategies.leveraged_etf import LeveragedETFStrategy
        threshold = LeveragedETFStrategy.get_stop_loss_for_regime(regime)
        return threshold if threshold is not None else -0.99
    if code == "LEV_ST":
        from strategies.lev_short_term import LevShortTermStrategy
        threshold = LevShortTermStrategy.get_stop_loss_for_regime(regime)
        return threshold if threshold is not None else -0.99
    return STRATEGY_STOP_LOSS.get(code, -0.10)


def phase_stop_loss_check(regime: str = "NEUTRAL") -> list:
    """C2 fix: 포지션별 stop-loss 강제 검사 → SELL 시그널 강제 생성.

    기존 버그: 전략 파일에 `stop_loss_pct = 0.10` 이 선언만 되어 있고
    어디서도 읽히지 않아 손절이 0% 상태였다. 이 phase는 Phase 2 직전에
    실행되며, portfolios.json의 각 포지션을 확인해 `unrealized_plpc` 가
    전략 임계값을 초과하면 강제 SELL 시그널을 생성한다.

    Returns:
        List of forced SELL signals (모두 weight_pct=1.0 = 전량 청산)
    """
    from strategies.base_strategy import Signal, Direction

    print(f"[Phase 1.8: STOP-LOSS CHECK] 포지션별 손절 기준 검사 중 (regime={regime})...")

    portfolios = load_portfolios()
    forced_sells: list = []

    for code, strat in portfolios.get("strategies", {}).items():
        threshold = _get_strategy_stop_loss(code, regime)
        positions = strat.get("positions", {}) or {}
        for sym, pos in positions.items():
            plpc = pos.get("unrealized_plpc")
            if plpc is None:
                continue
            if plpc <= threshold:
                forced_sells.append(Signal(
                    strategy=code,
                    symbol=sym,
                    direction=Direction.SELL,
                    weight_pct=1.0,  # 전량 청산
                    confidence=1.0,
                    reason=(
                        f"STOP-LOSS: {plpc:+.1%} <= {threshold:+.0%} "
                        f"(strategy={code})"
                    ),
                    order_type="market",
                ))
                print(
                    f"  [STOP-LOSS] {sym} ({code}): P&L {plpc:+.1%} "
                    f"<= {threshold:+.0%} → 전량 청산"
                )

    if not forced_sells:
        print("  손절 기준 초과 포지션 없음")
    else:
        print(f"  총 {len(forced_sells)}개 포지션 강제 청산 대상")

    return forced_sells


def phase_signals(market_data: dict, regime: str = "NEUTRAL", allocations: dict = None) -> list:
    """Run all strategy modules and collect signals."""
    print("[Phase 2: SIGNALS] Running strategy modules...")

    from strategies.momentum import MomentumStrategy
    from strategies.value_quality import ValueQualityStrategy
    from strategies.quant_factor import QuantFactorStrategy
    from strategies.leveraged_etf import LeveragedETFStrategy
    from strategies.lev_short_term import LevShortTermStrategy

    strategies = [
        MomentumStrategy(),
        ValueQualityStrategy(),
        QuantFactorStrategy(),
        LeveragedETFStrategy(),
        LevShortTermStrategy(),
    ]

    portfolios = load_portfolios()

    all_signals = []
    for strat in strategies:
        # 배분 $1 미만이면 사실상 0으로 스킵 (부동소수점 비교 회피)
        if allocations and allocations.get(strat.name, 0) < 1.0:
            print(f"  {strat.name}: SKIPPED (regime={regime}, allocation=$0)")
            continue

        # Regime 정보 주입
        strat.regime = regime

        # Current positions for SELL signal generation
        strat_data = portfolios["strategies"].get(strat.name, {})
        current_positions = strat_data.get("positions", {}) or None

        # LEV (Core-Satellite Barbell 재설계 2026-04-11): delta 기반 리밸런스를 위해
        # 전략에 실제 allocated capital 을 주입한다. allocator 가 계산한 target 금액을
        # 사용해 leveraged_etf.generate_signals() 가 SELL/BUY delta 를 정확히 산출.
        if hasattr(strat, "allocated_capital"):
            strat.allocated_capital = float(
                (allocations or {}).get(strat.name, 0)
                or strat_data.get("allocated", 0)
                or 0
            )

        # N-LOW-2: negative-cash guard — 전략이 현재 음수 현금 상태면 BUY 시그널을 드랍한다.
        # 기존 버그: 음수 cash 상태에서도 BUY 시그널 생성 → 리스크 게이트 cash_buffer 에서
        # 수십 건 FAIL → 로그 오염 + CPU 낭비. SELL 시그널은 정상 흐르게 유지해 점진적 회복 허용.
        # RL-1 (2026-04-11): 근본 원인 해결됨 — _sync_alpaca_positions 공식이 market_value
        # 대신 cost_basis 로 수정되어 평가익이 나와도 cash 가 더 이상 음수로 떨어지지 않음.
        # 이 블록은 defense-in-depth 용으로 잔존. 1주 안정 운영 관찰 후 제거 여부 재판단.
        strat_cash = float(strat_data.get("cash", 0) or 0)
        cash_guard = strat_cash < -10

        signals = strat.generate_signals(market_data, current_positions)
        if cash_guard and signals:
            from strategies.base_strategy import Direction as _Dir
            pre_count = len(signals)
            signals = [s for s in signals if s.direction != _Dir.BUY]
            dropped = pre_count - len(signals)
            if dropped:
                print(
                    f"  [{strat.name}] 음수 cash ${strat_cash:.2f} 감지 — "
                    f"BUY 시그널 {dropped}건 드롭 (SELL/EXIT 만 유지)"
                )
        print(f"  {strat.name}: {len(signals)} signals")
        for s in signals:
            print(f"    {s.symbol} {s.direction.value} {s.weight_pct:.0%} conf={s.confidence:.2f} -{s.reason}")
        all_signals.extend(signals)

    return all_signals


# ─── Phase 2.5: RESEARCH (NEW) ──────────────────────────────────────────

def _load_paperclip_results() -> dict | None:
    """Paperclip research_results.json 로드 (존재하고 24시간 이내면 사용)."""
    results_path = Path(__file__).parent / "state" / "research_results.json"
    if not results_path.exists():
        return None
    try:
        with open(results_path, "r") as f:
            data = json.loads(f.read())
        # 24시간 이내 결과만 사용
        from datetime import datetime, timezone
        generated = datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - generated).total_seconds() / 3600
        if age_hours > 24:
            print(f"[Research] Paperclip 결과 만료 ({age_hours:.1f}h) — LLM 폴백")
            return None
        return data
    except Exception as e:
        print(f"[Research] Paperclip 결과 로드 실패: {e}")
        return None


def _apply_paperclip_verdicts(signals: list, paperclip: dict) -> tuple[list, dict, dict]:
    """Paperclip research_results.json의 verdict를 시그널에 적용."""
    from research.models import ResearchVerdict
    from research.consensus import calculate_consensus

    verdicts_by_symbol = {}
    regime_data = paperclip.get("regime", {})
    regime_str = regime_data.get("regime", "NEUTRAL")

    print(f"[Research] Paperclip 결과 사용 (생성: {paperclip['generated_at']})")
    print(f"[Research] Paperclip 레짐: {regime_str}, 감성: {regime_data.get('macro_sentiment', 'N/A')}")

    adjusted = []
    for signal in signals:
        sym_verdicts_raw = paperclip.get("verdicts", {}).get(signal.symbol, [])
        if not sym_verdicts_raw:
            # Paperclip에 해당 종목 verdict 없으면 원본 유지
            adjusted.append(signal)
            continue

        sym_verdicts = [ResearchVerdict.from_dict(v) for v in sym_verdicts_raw]
        verdicts_by_symbol[signal.symbol] = sym_verdicts

        # VETO 체크
        veto = any(v.direction == "VETO" for v in sym_verdicts)
        if veto:
            print(f"  {signal.symbol}: VETO by Paperclip → DROPPED")
            continue

        # consensus 계산
        adjusted_conf, meta = calculate_consensus(sym_verdicts, regime_str, signal.confidence)

        if adjusted_conf < 0.4:
            delta = adjusted_conf - signal.confidence
            print(f"  {signal.symbol}: confidence {signal.confidence:.2f} → {adjusted_conf:.2f} < 0.4 → DROPPED")
            continue

        delta = adjusted_conf - signal.confidence
        signal.confidence = round(min(1.0, max(0.0, adjusted_conf)), 4)
        signal.reason += f" | Paperclip Δ={delta:+.2f}"
        adjusted.append(signal)

    print(f"[Research] Paperclip 적용: {len(signals)} → {len(adjusted)} signals")
    return adjusted, regime_data, verdicts_by_symbol


def phase_research(signals: list, market_data: dict, research_mode: str, no_cache: bool):
    """Run Research Overlay -5-agent parallel analysis + confidence adjustment.

    Paperclip research_results.json이 존재하고 유효하면 LLM 호출 없이 사용.
    """
    # Paperclip 결과 우선 확인
    paperclip = _load_paperclip_results()
    if paperclip and research_mode != "skip":
        return _apply_paperclip_verdicts(signals, paperclip)

    from research.overlay import run_research_overlay

    portfolios = load_portfolios()
    adjusted_signals, regime, verdicts = run_research_overlay(
        signals=signals,
        market_data=market_data,
        portfolio_state=portfolios,
        research_mode=research_mode,
        no_cache=no_cache,
    )
    return adjusted_signals, regime, verdicts


# ─── Phase 3: RISK ──────────────────────────────────────────────────────

def phase_risk(signals: list, market_data: dict | None = None) -> tuple[list, list, list]:
    """Validate each signal through risk gates.

    Args:
        signals: Generated trade signals from phase_signals
        market_data: Phase 1 data dict (used for C3: alpaca_unavailable BUY block)

    Returns:
        (approved, failed_signals, failed_details)
    """
    print("[Phase 3: RISK] Validating signals...")

    from execution.risk_validator import validate_signal
    from execution.circuit_breaker import check_circuit_breaker, filter_signals_by_stage, Stage as CBStage
    from strategies.base_strategy import Direction

    portfolios = load_portfolios()
    approved = []
    failed_signals = []
    failed_details = []

    # Circuit breaker gate (4-stage graduated protection)
    cb_state = check_circuit_breaker(portfolios)
    if cb_state.stage >= CBStage.WARNING:
        print(f"  [CIRCUIT BREAKER] Stage {cb_state.stage.name}: {cb_state.reason}")
    if cb_state.stage == CBStage.EMERGENCY:
        print("  [CIRCUIT BREAKER] EMERGENCY lock active — all signals blocked")
        return [], list(signals), [
            {"symbol": s.symbol, "strategy": s.strategy, "failed_checks": ["circuit_breaker_emergency"]}
            for s in signals
        ]
    if cb_state.stage > CBStage.NORMAL:
        signals, cb_filtered = filter_signals_by_stage(signals, cb_state.stage)
        if cb_filtered:
            print(f"  [CIRCUIT BREAKER] Filtered {len(cb_filtered)} signals (stage={cb_state.stage.name})")
            for s in cb_filtered:
                failed_signals.append(s)
                failed_details.append({
                    "symbol": s.symbol,
                    "strategy": s.strategy,
                    "failed_checks": [f"circuit_breaker_{cb_state.stage.name.lower()}"],
                })

    # C3: Alpaca 연결 불가 시 BUY 전면 차단. SELL(청산)은 여전히 허용.
    alpaca_unavailable = bool((market_data or {}).get("alpaca_unavailable", False))
    if alpaca_unavailable:
        print(
            "  [CRITICAL] Alpaca unavailable — BUY 전면 차단 모드. "
            "SELL(청산) 시그널만 처리."
        )

    for signal in signals:
        # C3: Alpaca 장애 시 BUY 즉시 거부 (리스크 게이트 이전)
        if alpaca_unavailable and signal.direction == Direction.BUY:
            failed_signals.append(signal)
            failed_details.append({
                "symbol": signal.symbol,
                "strategy": signal.strategy,
                "failed_checks": ["alpaca_unavailable_buy_block"],
            })
            print(f"  {signal.symbol} ({signal.strategy}): FAIL — alpaca_unavailable_buy_block")
            continue
        strat_data = portfolios["strategies"].get(signal.strategy, {})
        allocated = strat_data.get("allocated", 0)
        # SIM2 fix: 실제 NAV 기준으로 리스크 계산 (손실 후 과대 포지션 방지)
        current_nav = strat_data.get("cash", 0) + sum(
            p.get("market_value", 0) for p in strat_data.get("positions", {}).values()
        )
        capital = min(allocated, current_nav) if current_nav > 0 else allocated
        cash = strat_data.get("cash", 0)

        current_positions = {}
        for sym, pos in strat_data.get("positions", {}).items():
            current_positions[sym] = pos.get("qty", 0) * pos.get("current", 0)

        trade_value = capital * signal.weight_pct

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
        failed_checks = [r.check_name for r in results if not r.passed]
        print(f"  {signal.symbol} ({signal.strategy}): {status}", end="")
        if failed_checks:
            print(f" -failed: {', '.join(failed_checks)}")
        else:
            print()

        if passed:
            approved.append(signal)
        else:
            failed_signals.append(signal)
            failed_details.append({
                "symbol": signal.symbol,
                "strategy": signal.strategy,
                "failed_checks": failed_checks,
            })

    print(f"  Approved: {len(approved)} / {len(signals)}")
    return approved, failed_signals, failed_details


# ─── Phase 3.5: APPEAL (NEW) ────────────────────────────────────────────

def phase_appeal(failed_signals: list, failed_details: list,
                 research_verdicts: dict, market_data: dict, regime):
    """Appeal loop: Risk-FAIL signals get Research Division re-review."""
    from research.overlay import run_appeal

    portfolios = load_portfolios()
    appealed = run_appeal(
        failed_signals=failed_signals,
        risk_results=failed_details,
        research_verdicts=research_verdicts,
        market_data=market_data,
        portfolio_state=portfolios,
        regime=regime,
    )
    return appealed


# ─── Phase 4: RESOLVE ───────────────────────────────────────────────────

def phase_resolve(signals: list) -> list:
    """Resolve conflicting signals (same symbol, different strategies)."""
    print("[Phase 4: RESOLVE] Checking for conflicts...")

    from strategies.base_strategy import Direction

    by_symbol: dict[str, list] = {}
    for s in signals:
        by_symbol.setdefault(s.symbol, []).append(s)

    resolved = []
    for symbol, group in by_symbol.items():
        if len(group) == 1:
            resolved.append(group[0])
            continue

        buy_signals = [s for s in group if s.direction == Direction.BUY]
        sell_signals = [s for s in group if s.direction == Direction.SELL]

        if buy_signals and sell_signals:
            all_sorted = sorted(group, key=lambda s: s.confidence, reverse=True)
            winner = all_sorted[0]
            print(f"  CONFLICT {symbol}: {len(buy_signals)} BUY vs {len(sell_signals)} SELL → {winner.strategy} {winner.direction.value} (conf={winner.confidence:.2f})")
            resolved.append(winner)
        else:
            resolved.extend(group)

    print(f"  Resolved: {len(resolved)} signals")
    return resolved


# ─── Phase 4.5: CROSS-STRATEGY CHECK ──────────────────────────────────

def _phase_cross_strategy_check(signals: list, max_aggregate_pct: float = 0.25) -> list:
    """Check aggregate symbol exposure across all strategies.

    If the same symbol appears in multiple strategies, ensure combined
    allocation doesn't exceed max_aggregate_pct of total AUM.
    Drops the lowest-confidence duplicate if exceeded.
    """
    from strategies.base_strategy import Direction

    print("[Phase 4.5: CROSS-STRATEGY CHECK] Checking aggregate exposure...")

    portfolios = load_portfolios()
    total_aum = portfolios.get("account_total", 100000)

    # Group BUY signals by symbol
    by_symbol: dict[str, list] = {}
    for s in signals:
        if s.direction == Direction.BUY:
            by_symbol.setdefault(s.symbol, []).append(s)

    approved = []
    rejected_count = 0

    for s in signals:
        if s.direction != Direction.BUY:
            approved.append(s)
            continue

        group = by_symbol.get(s.symbol, [s])
        if len(group) <= 1:
            approved.append(s)
            continue

        # Calculate aggregate: sum of (strategy_capital * weight_pct) / total_aum
        total_exposure = 0.0
        for g in group:
            strat_capital = portfolios["strategies"].get(g.strategy, {}).get("allocated", 0)
            total_exposure += strat_capital * g.weight_pct

        aggregate_pct = total_exposure / total_aum if total_aum > 0 else 1.0

        if aggregate_pct > max_aggregate_pct:
            # Keep only the highest-confidence signal, reject others
            best = max(group, key=lambda x: x.confidence)
            if s is best:
                approved.append(s)
            else:
                rejected_count += 1
                print(f"  REJECT {s.symbol} ({s.strategy}): aggregate {aggregate_pct:.1%} > {max_aggregate_pct:.0%}")
        else:
            approved.append(s)

    if rejected_count:
        print(f"  Cross-strategy check: {rejected_count} signals rejected")
    else:
        print(f"  Cross-strategy check: all clear ({len(signals)} signals)")

    return approved


# ─── Phase 5: EXECUTE ───────────────────────────────────────────────────

def phase_execute(signals: list, dry_run: bool = False) -> list:
    """Submit orders to Alpaca with network-failure protection.

    C7 fix (20회 시뮬레이션 중 발견): SIM 3에서 Alpaca DNS 장애 시
    execute_signal() 내부의 get_positions() 호출이 예외로 전파되어
    전체 사이클이 exit=1로 중단, phase_report 미실행 → nav_history 유실.
    이제 execute_signals 전체를 try/except로 감싸서 실패 시 빈 결과를
    반환하고 사이클을 계속 진행한다 (report 단계에서 전일 NAV 유지).
    """
    mode = "DRY RUN" if dry_run else "LIVE"
    print(f"[Phase 5: EXECUTE] Submitting orders ({mode})...")

    from execution.order_manager import execute_signals

    portfolios = load_portfolios()
    allocations = {}
    for code, strat in portfolios["strategies"].items():
        allocations[code] = {
            "capital": strat["allocated"],
            "cash": strat["cash"],
        }

    try:
        results = execute_signals(signals, allocations, dry_run=dry_run)
    except Exception as e:
        # C7: 네트워크·API 장애 시 전체 사이클 중단 방지
        print(f"  [CRITICAL] phase_execute 예외 — 모든 주문 스킵: {e}")
        import traceback
        traceback.print_exc()
        results = [
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "strategy": s.strategy,
                "symbol": s.symbol,
                "side": s.direction.value,
                "status": "error",
                "error_reason": f"phase_execute_exception: {type(e).__name__}: {e}",
            }
            for s in signals
        ]

    for r in results:
        symbol = r.get("symbol", "?")
        status = r.get("status", "?")
        print(f"  {symbol}: {status}")

    return results


# ─── Phase 5.5: REBALANCE (NEW) ────────────────────────────────────────

def phase_rebalance(market_data: dict, dry_run: bool = False) -> tuple[list, list]:
    """Check rebalancing schedules, generate rebalance orders if triggered."""
    from scripts.rebalancer import run_rebalance_check

    portfolios = load_portfolios()
    result = run_rebalance_check(portfolios, market_data, dry_run=dry_run)

    if result["rebalanced"] and not dry_run:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for code in result["rebalanced"]:
            portfolios["strategies"][code]["last_rebalance"] = today
        save_portfolios(portfolios)

    return result.get("signals", []), result.get("rebalanced", [])


# ─── Phase 6: REPORT ────────────────────────────────────────────────────

def _sync_alpaca_positions(portfolios: dict) -> dict:
    """Sync Alpaca actual positions into portfolios.json.

    Builds symbol→strategy mapping from trade_log.jsonl, then updates
    each strategy's positions dict with live Alpaca data.
    """
    try:
        from execution.alpaca_client import get_positions, get_account_info

        alpaca_positions = get_positions()
        account = get_account_info()
    except Exception as e:
        print(f"  [sync] Alpaca sync skipped: {e}")
        return portfolios

    # Build symbol→strategy map from trade_log
    # TODO(RL-1 latent): last-write-wins here loses multi-strategy ownership when
    # the same symbol is bought by more than one strategy (e.g. LRCX/AMAT/AMD
    # in MOM+QNT). Not corrupting state as of 2026-04-11 because the overlapping
    # trade_log entries are mostly dry_run and current positions happen not to
    # overlap, but revisit if we see unmatched positions in the sync log.
    symbol_strategy_map = {}
    trade_log_path = STATE_DIR / "trade_log.jsonl"
    if trade_log_path.exists():
        with open(trade_log_path) as f:
            for line in f:
                entry = json.loads(line.strip())
                sym = entry.get("symbol")
                strat = entry.get("strategy")
                if sym and strat and entry.get("side") == "buy":
                    symbol_strategy_map[sym] = strat

    # Clear all existing positions
    for code, strat in portfolios["strategies"].items():
        strat["positions"] = {}

    # Place Alpaca positions into correct strategy
    unmatched = []
    for pos in alpaca_positions:
        sym = pos["symbol"]
        strategy_code = symbol_strategy_map.get(sym)
        if strategy_code and strategy_code in portfolios["strategies"]:
            portfolios["strategies"][strategy_code]["positions"][sym] = {
                "qty": pos["qty"],
                "avg_entry": pos["avg_entry_price"],
                "current": pos["current_price"],
                "market_value": pos["market_value"],
                "unrealized_pl": pos["unrealized_pl"],
                "unrealized_plpc": pos["unrealized_plpc"],
            }
        else:
            unmatched.append(sym)

    # Update strategy cash from account-level data
    total_position_value = sum(p["market_value"] for p in alpaca_positions)
    total_cash = account["cash"]
    new_equity = float(account["equity"])
    if new_equity >= 100:
        portfolios["account_total"] = new_equity
    else:
        print(f"  [sync] WARNING: Alpaca equity ${new_equity:,.2f} < $100 — skipping account_total update")

    # Recalculate per-strategy cash: allocated - sum(cost basis in strategy)
    # RL-1 fix (2026-04-11): previously used market_value, which made cash go
    # negative by exactly the unrealized P&L whenever positions appreciated.
    # cash is the uninvested budget, so it must be computed from cost basis
    # (avg_entry * qty). Unrealized P&L already flows into NAV downstream
    # via `nav += qty * current` (see phase_report NAV block).
    for code, strat in portfolios["strategies"].items():
        strat_cost_basis = sum(
            p.get("avg_entry", 0) * p.get("qty", 0)
            for p in strat["positions"].values()
        )
        strat["cash"] = round(strat["allocated"] - strat_cost_basis, 2)

    pos_count = sum(len(s["positions"]) for s in portfolios["strategies"].values())
    print(f"  [sync] Alpaca: {len(alpaca_positions)} positions synced ({pos_count} mapped, {len(unmatched)} unmatched)")
    if unmatched:
        print(f"  [sync] Unmatched symbols: {', '.join(unmatched)}")

    # N-MEDIUM-3: negative cash detection (margin call guard)
    _check_negative_cash(portfolios)

    # inception drift 감지: allocated vs inception.strategies 괴리 경고
    _check_inception_drift(portfolios)

    return portfolios


def phase_report(signals: list, execution_results: list, regime=None, rebalanced_strategies: list = None):
    """Update performance.json, generate daily report + dashboard."""
    print("[Phase 6: REPORT] Generating report...")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    portfolios = load_portfolios()

    # Sync Alpaca positions into portfolios.json (source of truth)
    portfolios = _sync_alpaca_positions(portfolios)

    # Update NAV history (deduplicate: keep only one entry per date)
    for code, strat in portfolios["strategies"].items():
        nav = strat["cash"]
        for sym, pos in strat.get("positions", {}).items():
            nav += pos.get("qty", 0) * pos.get("current", 0)

        nav_history = strat.setdefault("nav_history", [])
        # Full dedup: remove all entries with today's date, then append once
        nav_history[:] = [h for h in nav_history if h.get("date") != today]
        nav_history.append({"date": today, "nav": round(nav, 2)})

    save_portfolios(portfolios)

    # ─── Performance Calculator ───
    trade_log = []
    try:
        from scripts.performance_calculator import (
            load_existing_performance, load_trade_log,
            fetch_benchmark_prices, build_daily_snapshot, append_and_save,
            generate_strategy_monthly_report,
        )

        benchmark_prices = fetch_benchmark_prices()
        trade_log = load_trade_log()
        existing_perf = load_existing_performance()

        regime_str = _extract_regime_str(regime)
        snapshot = build_daily_snapshot(
            portfolios, regime_str, len(signals),
            benchmark_prices, rebalanced_strategies or [],
        )
        performance_data = append_and_save(existing_perf, snapshot, portfolios, trade_log)

        # Monthly strategy reports (all strategies)
        strategy_report_dir = ROOT / "reports" / "strategy"
        for code, strat in portfolios["strategies"].items():
            generate_strategy_monthly_report(
                code, strat["name"], performance_data, trade_log, strategy_report_dir,
            )
    except Exception as e:
        print(f"  [perf] Performance calculation failed: {e}")
        import traceback; traceback.print_exc()
        performance_data = {}
        benchmark_prices = {}

    # ─── Paper Dashboard ───
    try:
        from scripts.dashboard_generator import generate_paper_dashboard
        regime_str = _extract_regime_str(regime)
        if not trade_log:
            trade_log = load_trade_log()
        generate_paper_dashboard(
            performance_data, portfolios, trade_log, regime_str,
            output_path=str(ROOT / "docs" / "paper_dashboard.html"),
        )
    except Exception as e:
        print(f"  [dashboard] Paper dashboard failed: {e}")

    # ─── Daily Report Markdown ───
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{today}-daily.md"

    regime_str = _extract_regime_str(regime)
    regime_reasoning = _extract_regime_reasoning(regime)

    lines = [f"# Daily Trading Report -{today}", ""]

    if regime_str:
        lines.extend([f"## Market Regime: {regime_str}", f"{regime_reasoning}", ""])

    # Performance Summary Table
    strats = performance_data.get("strategies", {})
    total_info = strats.get("TOTAL", {})
    lines.extend([
        "## Performance Summary",
        "",
        "| Strategy | NAV | Today | Total | MDD | Sharpe | Trades |",
        "|----------|-----|-------|-------|-----|--------|--------|",
    ])
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
    lines.append(
        f"| **TOTAL** | **${total_info.get('current_nav', 0):,.0f}** | | "
        f"**{total_info.get('total_return_pct', 0):+.2f}%** | | | |"
    )
    spy_r = total_info.get("spy_return_pct", 0)
    qqq_r = total_info.get("qqq_return_pct", 0)
    lines.append(f"| SPY | | | {spy_r:+.2f}% | | | |")
    lines.append(f"| QQQ | | | {qqq_r:+.2f}% | | | |")
    lines.append("")

    # Signals
    lines.extend(["## Signals Generated", f"Total: {len(signals)}", ""])
    for s in signals:
        lines.append(f"- **{s.symbol}** ({s.strategy}) {s.direction.value} {s.weight_pct:.0%} conf={s.confidence:.2f}")
        lines.append(f"  {s.reason}")

    # Execution
    lines.extend(["", "## Execution Results", ""])
    for r in execution_results:
        lines.append(f"- {r.get('symbol', '?')}: {r.get('status', '?')}")
        if r.get("error_reason"):
            lines.append(f"  Reason: {r['error_reason']}")

    # Rebalances
    if rebalanced_strategies:
        lines.extend(["", "## Rebalances", ""])
        for code in rebalanced_strategies:
            lines.append(f"- **{code}** rebalanced")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Report saved: {report_path}")

    # Daily Analysis report (Obsidian-ready)
    try:
        from scripts.daily_analysis import generate_daily_analysis, copy_to_obsidian
        analysis_path = generate_daily_analysis(date_str=today)
        # Copy to Obsidian if running locally (vault exists)
        from pathlib import Path as _P
        if _P(r"C:\Users\yjisu\Documents\ClaudeVault").exists():
            copy_to_obsidian(analysis_path)
    except Exception as e:
        print(f"  [analysis] Daily analysis failed: {e}")


def _extract_regime_str(regime) -> str:
    if regime is None:
        return "UNKNOWN"
    if hasattr(regime, 'regime'):
        return regime.regime
    if isinstance(regime, str):
        return regime
    return "UNKNOWN"


def _extract_regime_reasoning(regime) -> str:
    if regime and hasattr(regime, 'reasoning'):
        return getattr(regime, 'reasoning', '')
    return ''


# ─── Phase 7: MONITOR (Intraday) ───────────────────────────────────────

MONITOR_PEAKS_PATH = STATE_DIR / "monitor_peaks.json"
MONITOR_LOG_PATH = STATE_DIR / "monitor_log.jsonl"


def _load_monitor_peaks() -> dict:
    if MONITOR_PEAKS_PATH.exists():
        with open(MONITOR_PEAKS_PATH) as f:
            return json.load(f)
    return {"last_updated": None, "peaks": {}}


def _save_monitor_peaks(data: dict):
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(MONITOR_PEAKS_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=_json_default)


def _append_monitor_log(entry: dict):
    MONITOR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MONITOR_LOG_PATH, "a") as f:
        f.write(json.dumps(entry, default=_json_default) + "\n")


def _build_symbol_strategy_map(portfolios: dict) -> dict[str, str]:
    """Build symbol→strategy mapping from portfolios.json positions."""
    mapping = {}
    for code, strat in portfolios["strategies"].items():
        for sym in strat.get("positions", {}):
            mapping[sym] = code

    # Fallback: check trade_log for unmapped symbols
    if not mapping:
        trade_log_path = STATE_DIR / "trade_log.jsonl"
        if trade_log_path.exists():
            with open(trade_log_path) as f:
                for line in f:
                    entry = json.loads(line.strip())
                    sym = entry.get("symbol")
                    strat = entry.get("strategy")
                    if sym and strat and entry.get("side") == "buy":
                        mapping[sym] = strat

    return mapping


def phase_monitor(dry_run: bool = False) -> list[dict]:
    """Intraday 30-min monitor -stop-loss, take-profit, trailing stop.

    Flow:
      1. Check market open
      2. Get open orders (skip symbols with pending sells)
      3. Get Alpaca positions (source of truth)
      4. Map symbol→strategy
      5. Load peak tracker
      6. Evaluate each position
      7. Execute SELL signals if triggered
      8. Update peaks + monitor log
    """
    from execution.alpaca_client import (
        is_market_open, get_open_orders, get_positions, get_account_info,
    )
    from execution.monitor_rules import evaluate_position, check_strategy_mdd
    from execution.circuit_breaker import check_circuit_breaker, Stage as CBStage
    from strategies.base_strategy import Signal, Direction

    print("[Phase 7: MONITOR] Intraday position monitoring...")

    # 1. Market open check
    try:
        market_open = is_market_open()
    except Exception as e:
        print(f"  Market check failed: {e} -treating as closed")
        market_open = False

    if not market_open:
        print("  Market is CLOSED -skipping monitor")
        _append_monitor_log({
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_type": "monitor",
            "market_open": False,
            "positions_checked": 0,
            "exits": [],
        })
        return []

    # 2. Open orders -skip symbols with pending SELL orders
    try:
        open_orders = get_open_orders()
        pending_sell_symbols = {
            o["symbol"] for o in open_orders
            if "sell" in o.get("side", "").lower()
        }
        if pending_sell_symbols:
            print(f"  Pending sell orders: {', '.join(pending_sell_symbols)} -will skip")
    except Exception as e:
        print(f"  Open orders check failed: {e}")
        pending_sell_symbols = set()

    # 3. Alpaca positions
    try:
        positions = get_positions()
        account = get_account_info()
        print(f"  Alpaca: {len(positions)} positions, equity=${account['equity']:,.2f}")
    except Exception as e:
        print(f"  Alpaca connection failed: {e}")
        return []

    if not positions:
        print("  No positions to monitor")
        _append_monitor_log({
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_type": "monitor",
            "market_open": True,
            "positions_checked": 0,
            "exits": [],
        })
        return []

    # 4. Symbol→Strategy mapping
    portfolios = load_portfolios()
    sym_map = _build_symbol_strategy_map(portfolios)

    # 5. Load peak tracker
    peaks_data = _load_monitor_peaks()
    peaks = peaks_data.get("peaks", {})

    # 6. Evaluate each position
    exits = []
    checked = 0

    for pos in positions:
        sym = pos["symbol"]
        if sym in pending_sell_symbols:
            continue

        checked += 1
        strategy = sym_map.get(sym, "UNKNOWN")
        plpc = pos["unrealized_plpc"]

        # Update peak tracking
        current_peak = peaks.get(sym, {}).get("peak_plpc", plpc)
        if plpc > current_peak:
            current_peak = plpc
        peaks[sym] = {
            "peak_plpc": current_peak,
            "strategy": strategy,
            "last_plpc": plpc,
        }

        # Evaluate
        should_exit, reason = evaluate_position(plpc, current_peak, strategy)

        if should_exit:
            print(f"  EXIT {sym} ({strategy}): {reason}")
            exits.append({
                "symbol": sym,
                "strategy": strategy,
                "reason": reason,
                "plpc": plpc,
                "qty": pos["qty"],
            })

    # 7. Strategy-level MDD check
    mdd_status = {}
    for code, strat in portfolios["strategies"].items():
        mdd_triggered, mdd_reason = check_strategy_mdd(strat.get("nav_history", []))
        mdd_status[code] = mdd_reason if mdd_triggered else "ok"
        if mdd_triggered:
            print(f"  MDD ALERT {code}: {mdd_reason}")
            # Add all positions of this strategy to exits
            for pos in positions:
                sym = pos["symbol"]
                if sym_map.get(sym) == code and sym not in [e["symbol"] for e in exits]:
                    exits.append({
                        "symbol": sym,
                        "strategy": code,
                        "reason": f"strategy_mdd: {mdd_reason}",
                        "plpc": pos["unrealized_plpc"],
                        "qty": pos["qty"],
                    })

    # Portfolio-level circuit breaker (replaces hardcoded MDD -15% check)
    cb_state = check_circuit_breaker(portfolios)
    port_mdd_reason = cb_state.reason
    if cb_state.stage == CBStage.EMERGENCY:
        print(f"  [CIRCUIT BREAKER] EMERGENCY: {cb_state.reason} — 전 포지션 청산 개시")
        for code, strat in portfolios["strategies"].items():
            for sym, pos in strat.get("positions", {}).items():
                if sym not in [e["symbol"] for e in exits]:
                    exits.append({
                        "symbol": sym,
                        "strategy": code,
                        "reason": f"circuit_breaker_emergency: {cb_state.reason}",
                        "plpc": pos.get("unrealized_plpc", 0),
                        "qty": pos.get("qty", 0),
                    })

    # 8. Execute exit orders
    execution_results = []
    if exits:
        from execution.order_manager import execute_signal as exec_sig

        for exit_info in exits:
            signal = Signal(
                strategy=exit_info["strategy"],
                symbol=exit_info["symbol"],
                direction=Direction.SELL,
                weight_pct=1.0,
                confidence=1.0,
                reason=f"[MONITOR] {exit_info['reason']}",
            )

            if dry_run:
                result = {
                    "symbol": exit_info["symbol"],
                    "status": "dry_run",
                    "reason": exit_info["reason"],
                }
                print(f"  DRY RUN: would sell {exit_info['symbol']} ({exit_info['reason']})")
            else:
                strat_data = portfolios["strategies"].get(exit_info["strategy"], {})
                result = exec_sig(
                    signal,
                    strategy_capital=strat_data.get("allocated", 0),
                    strategy_cash=strat_data.get("cash", 0),
                    dry_run=False,
                )
                print(f"  SOLD {exit_info['symbol']}: {result.get('status', '?')}")

            execution_results.append(result)

            # Remove from peaks if sold
            peaks.pop(exit_info["symbol"], None)

    # 9. Save state
    peaks_data["peaks"] = peaks
    _save_monitor_peaks(peaks_data)

    # Sync portfolios if any exits executed (not dry-run)
    if exits and not dry_run:
        portfolios = _sync_alpaca_positions(portfolios)

        # MDD peak reset: 전략 MDD 또는 포트폴리오 MDD로 전액 청산된 전략의
        # nav_history를 현재 allocated 기준으로 리셋한다.
        # 이렇게 하지 않으면 할당 자본이 축소된 후에도 과거 peak이 유지되어
        # 새로운 포지션을 매수할 때마다 즉시 MDD 기준에 걸려 청산되는 루프가 발생한다.
        mdd_exited = {e["strategy"] for e in exits if "strategy_mdd" in e.get("reason", "")}
        if cb_state.stage == CBStage.EMERGENCY:
            mdd_exited.update(portfolios["strategies"].keys())
        if mdd_exited:
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            for code in mdd_exited:
                strat = portfolios["strategies"].get(code, {})
                allocated = float(strat.get("allocated", 0))
                if allocated > 0:
                    strat["nav_history"] = [{"date": today_str, "nav": allocated}]
                    print(f"  [MDD reset] {code}: nav_history → [{today_str}: ${allocated:,.0f}]")

        save_portfolios(portfolios)

    # 10. Append monitor log
    _append_monitor_log({
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_type": "monitor",
        "market_open": True,
        "positions_checked": checked,
        "exits": [
            {"symbol": e["symbol"], "strategy": e["strategy"], "reason": e["reason"],
             "plpc": e["plpc"], "status": execution_results[i].get("status", "?") if i < len(execution_results) else "?"}
            for i, e in enumerate(exits)
        ],
        "mdd_status": mdd_status,
        "portfolio_mdd": port_mdd_reason if cb_state.stage == CBStage.EMERGENCY else "ok",
        "circuit_breaker_stage": cb_state.stage.name,
    })

    print(f"  Monitor complete: {checked} checked, {len(exits)} exits")
    return execution_results


# ─── Main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Paper Trading Cycle (Phase 2.5)")
    parser.add_argument("--phase", required=True,
                        choices=["all", "data", "signals", "research", "risk", "resolve", "rebalance", "execute", "report", "monitor"])
    parser.add_argument("--dry-run", action="store_true", help="Simulate without placing real orders")
    parser.add_argument("--research-mode", default=None, choices=["full", "selective", "skip"],
                        help="Research overlay depth (default: full, dry-run default: selective)")
    parser.add_argument("--no-cache", action="store_true", help="Bypass research cache")
    parser.add_argument("--force-regime", default=None, choices=["BULL", "BEAR", "NEUTRAL", "CRISIS"],
                        help="Override live regime detection (simulation/testing only)")
    args = parser.parse_args()

    # Default research mode: selective for dry-run, full otherwise
    research_mode = args.research_mode
    if research_mode is None:
        research_mode = "selective" if args.dry_run else "full"

    # N-HIGH-2: network healthcheck before any work
    if not _network_healthcheck():
        _audit_log("main", "error", {"reason": "network_down"})
        sys.exit(2)

    # Warn if previous cycles flagged degraded data quality
    try:
        if DEGRADED_COUNT_PATH.exists():
            _dc = json.loads(DEGRADED_COUNT_PATH.read_text(encoding="utf-8"))
            if int(_dc.get("consecutive", 0)) >= 2:
                print(
                    f"  [WARNING] 이전 사이클 degraded {_dc['consecutive']}회 연속 — "
                    f"데이터 소스 확인 권장"
                )
    except Exception:
        pass

    _audit_log("main", "start", {"phase": args.phase, "dry_run": args.dry_run})

    # N-LOW-4: allocation integrity check — Immutable Ledger last line of defense
    try:
        _pre_portfolios = load_portfolios()
        _check_allocation_integrity(_pre_portfolios)
    except Exception as e:
        print(f"  [integrity] pre-flight check skipped: {e}")

    # Phase Monitor -independent lightweight path
    if args.phase == "monitor":
        print(f"=== Intraday Monitor - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ===")
        print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
        print()
        _audit_log("monitor", "start", {"dry_run": args.dry_run})
        monitor_results = phase_monitor(dry_run=args.dry_run)
        _audit_log("monitor", "end", {"results_count": len(monitor_results) if monitor_results else 0})
        print()
        print("=== Monitor Cycle Complete ===")
        _backup_state_files()
        _audit_log("main", "end", {"phase": "monitor"})
        return

    print(f"=== Paper Trading Cycle -{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ===")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'} | Research: {research_mode}")
    print()

    from strategies.base_strategy import Direction

    # Phase 1: DATA
    if args.phase in ("all", "data"):
        market_data = phase_data()
        print()
    else:
        market_data = None

    # Phase 1.5: REGIME (NEW) + Hysteresis
    regime_info = None
    allocations = None
    if args.phase in ("all",):
        if market_data is None:
            from strategies.momentum import fetch_momentum_data
            market_data = fetch_momentum_data(days=400)
        regime_info, allocations = phase_regime(market_data, force_regime=args.force_regime)
        detected_regime = regime_info.regime if regime_info else "NEUTRAL"

        # Hysteresis: require 2 consecutive cycles in same regime before switching
        # (skipped when --force-regime is set — simulation mode)
        _regime_state_path = STATE_DIR / "regime_state.json"
        if args.force_regime:
            regime = args.force_regime
        else:
            try:
                if _regime_state_path.exists():
                    with open(_regime_state_path) as f:
                        _rs = json.load(f)
                    prev = _rs.get("regime", "NEUTRAL")
                    consec = _rs.get("consecutive_cycles", 0)
                    if detected_regime != prev and consec < 2:
                        print(f"  [Hysteresis] {prev}→{detected_regime} detected but only {consec} cycle(s). Holding {prev}.")
                        regime = prev
                    else:
                        regime = detected_regime
                else:
                    regime = detected_regime
            except Exception:
                regime = detected_regime

        print()
    else:
        regime = args.force_regime if args.force_regime else "NEUTRAL"

    # Phase 1.7: REGIME EXIT — emergency liquidation on regime downgrade
    if args.phase in ("all",) and regime_info:
        _regime_state_path = STATE_DIR / "regime_state.json"
        previous_regime = "NEUTRAL"
        try:
            if _regime_state_path.exists():
                with open(_regime_state_path) as f:
                    _rs = json.load(f)
                    previous_regime = _rs.get("regime", "NEUTRAL")
        except Exception:
            pass

        if previous_regime != regime:
            from strategies.regime_allocator import generate_regime_exit_signals
            exit_signals = generate_regime_exit_signals(regime, previous_regime, load_portfolios())
            if exit_signals:
                print(f"[Phase 1.7: REGIME EXIT] {previous_regime}→{regime}: {len(exit_signals)} emergency exits")
                phase_execute(exit_signals, dry_run=args.dry_run)
                print()

        # Save current regime state
        _regime_state = {
            "regime": regime,
            "since": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "consecutive_cycles": 1,
        }
        try:
            if _regime_state_path.exists():
                with open(_regime_state_path) as f:
                    _rs = json.load(f)
                if _rs.get("regime") == regime:
                    _regime_state["consecutive_cycles"] = _rs.get("consecutive_cycles", 0) + 1
                    _regime_state["since"] = _rs.get("since", _regime_state["since"])
            with open(_regime_state_path, "w") as f:
                json.dump(_regime_state, f, indent=2)
        except Exception as e:
            print(f"  [regime_state] Save failed: {e}")

    # Phase 1.6: FUNDAMENTALS — 실적캘린더/경제지표/애널리스트/내부자 거래
    fundamental_data: dict = {}
    if args.phase in ("all",):
        try:
            # 전략 유니버스 심볼 수집 (price 데이터 컬럼 기준)
            _prices = market_data.get("prices") if market_data else None
            _fund_symbols: list[str] = (
                [c for c in _prices.columns if not c.startswith("^")]
                if _prices is not None else []
            )
            if _fund_symbols:
                print(f"[Phase 1.6: FUNDAMENTALS] {len(_fund_symbols)} 종목 펀더멘털 수집...")
                from fundamentals import collect_all as _fund_collect_all
                fundamental_data = _fund_collect_all(_fund_symbols)
                if market_data is not None:
                    market_data["fundamental"] = fundamental_data
                print()
        except Exception as _fe:
            print(f"  [Phase 1.6] 수집 실패 (fallback 빈 데이터): {_fe}")
            print()

    # Phase 1.8: STOP-LOSS CHECK — 강제 청산 시그널 선행 생성 (C2)
    stop_loss_signals: list = []
    if args.phase in ("all", "signals"):
        stop_loss_signals = phase_stop_loss_check(regime=regime)
        print()

    # Phase 2: SIGNALS
    if args.phase in ("all", "signals"):
        if market_data is None:
            from strategies.momentum import fetch_momentum_data
            market_data = fetch_momentum_data(days=400)
            # signals-only 모드에서도 QNT FF5 팩터 보충 (phase_data 스킵 시 누락 방지)
            if market_data.get("factors") is None:
                try:
                    from strategies.quant_factor import fetch_factor_data
                    _qnt = fetch_factor_data()
                    market_data["factors"] = _qnt.get("factors")
                    market_data["qnt_prices"] = _qnt.get("prices")
                    market_data["ff5_stale"] = _qnt.get("ff5_stale", False)
                    market_data["ff5_days_lag"] = _qnt.get("ff5_days_lag", 0)
                except Exception as _e:
                    print(f"  [signals] QNT FF5 보충 실패: {_e}")
        signals = phase_signals(market_data, regime=regime, allocations=allocations)
        # C2: stop-loss SELL 시그널을 최우선 병합 (동일 심볼 중복 시 stop-loss 우선)
        if stop_loss_signals:
            sl_symbols = {(s.strategy, s.symbol) for s in stop_loss_signals}
            signals = stop_loss_signals + [
                s for s in signals if (s.strategy, s.symbol) not in sl_symbols
            ]
            print(f"  [STOP-LOSS] {len(stop_loss_signals)}개 강제 청산 시그널 병합")
        print()
    else:
        signals = []

    # Phase 2.3: TICKER NEWS (종목별 뉴스 수집 — Research Overlay 전)
    if signals and args.phase in ("all", "research"):
        try:
            from news.fetcher import fetch_news
            symbols_to_fetch = list(set(s.symbol for s in signals))[:30]
            print(f"[Phase 2.3: TICKER NEWS] {len(symbols_to_fetch)}개 종목 뉴스 수집 중...")
            if market_data.get("news") is None:
                market_data["news"] = {}
            fetched = 0
            for sym in symbols_to_fetch:
                if sym in market_data["news"]:
                    continue
                try:
                    articles = fetch_news(sym, max_articles=5)
                    market_data["news"][sym] = articles
                    fetched += len(articles)
                except Exception:
                    market_data["news"][sym] = []
            print(f"  종목별 뉴스: {fetched}건 수집 ({len(symbols_to_fetch)}종목)")
            print()
        except Exception as e:
            print(f"  [ticker_news] 수집 실패: {e}")

    # Phase 2.5: RESEARCH
    research_verdicts = {}
    if args.phase in ("all", "research"):
        if market_data is None:
            from strategies.momentum import fetch_momentum_data
            market_data = fetch_momentum_data(days=400)
        signals, _research_regime, research_verdicts = phase_research(
            signals, market_data, research_mode, args.no_cache
        )
        print()

    # Phase 3: RISK
    failed_signals = []
    failed_details = []
    if args.phase in ("all", "risk"):
        approved, failed_signals, failed_details = phase_risk(signals, market_data)
        print()
    else:
        approved = signals

    # Phase 3.5: APPEAL
    if args.phase in ("all",) and failed_signals and research_mode != "skip":
        appealed = phase_appeal(
            failed_signals, failed_details, research_verdicts, market_data, regime
        )
        approved.extend(appealed)
        print()

    # Phase 4: RESOLVE
    if args.phase in ("all", "resolve"):
        resolved = phase_resolve(approved)
        print()
    else:
        resolved = approved

    # Phase 4.5: CROSS-STRATEGY CHECK — aggregate symbol exposure
    if args.phase in ("all",) and resolved:
        resolved = _phase_cross_strategy_check(resolved)
        print()

    # Phase 5.5: REBALANCE (NEW)
    rebalanced_strategies = []
    if args.phase in ("all", "rebalance"):
        if market_data is None:
            market_data = phase_data()  # Full data fetch (LEV/VAL/QNT need their own data)
        _audit_log("rebalance", "start", {})
        rebalance_signals, rebalanced_strategies = phase_rebalance(market_data, dry_run=args.dry_run)
        # N-MEDIUM-1: rebalance 시그널도 risk gate 재통과 필수
        if rebalance_signals:
            rb_approved, rb_failed, _rb_details = phase_risk(rebalance_signals, market_data)
            print(
                f"  [REBALANCE] {len(rb_approved)}/{len(rebalance_signals)} "
                f"risk gate 통과 ({len(rb_failed)} 차단)"
            )
            resolved = resolved + rb_approved
        _audit_log("rebalance", "end", {
            "signals": len(rebalance_signals),
            "rebalanced_strategies": rebalanced_strategies,
        })
        print()

    # Phase 5: EXECUTE
    if args.phase in ("all", "execute"):
        _audit_log("execute", "start", {"signals": len(resolved), "dry_run": args.dry_run})
        results = phase_execute(resolved, dry_run=args.dry_run)
        _audit_log("execute", "end", {"results": len(results)})
        print()
    else:
        results = []

    # Phase 6: REPORT
    if args.phase in ("all", "report"):
        _audit_log("report", "start", {})
        phase_report(resolved, results, regime=regime_info, rebalanced_strategies=rebalanced_strategies)
        _audit_log("report", "end", {})
        print()

    print("=== Cycle Complete ===")
    _backup_state_files()
    _audit_log("main", "end", {"phase": args.phase, "resolved": len(resolved)})


if __name__ == "__main__":
    main()
