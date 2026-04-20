"""한국 주식 분석 진입점.

Usage:
    python kr_research/kr_analyzer.py --symbol 005930
    python kr_research/kr_analyzer.py --sector 반도체
    python kr_research/kr_analyzer.py --all

Also callable from /analyze-kr Claude Code command:
    run_analysis(target="005930")
    run_analysis(target="sector:반도체")
    run_analysis(target="all")
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime

# Windows cp949 터미널 인코딩 문제 해결
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 프로젝트 루트를 sys.path에 추가
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from kr_research.kr_agent_runner import run_all_agents, aggregate_verdicts
from kr_research.kr_data_fetcher import (
    build_market_snapshot,
    fetch_kr_stock,
    load_universe,
)
from kr_research.kr_models import KRAnalysisResult
from kr_research.kr_regime import detect_kr_regime
from kr_research.kr_report_generator import (
    generate_all_report,
    generate_sector_report,
    generate_symbol_report,
)

_VERDICTS_PATH = os.path.join(_PROJECT_ROOT, "state", "kr_verdicts.json")


# ─────────────────────────────────────────────
# 캐시 (24h TTL)
# ─────────────────────────────────────────────

def _load_verdicts_cache() -> dict:
    try:
        if os.path.exists(_VERDICTS_PATH):
            with open(_VERDICTS_PATH, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_verdicts_cache(cache: dict) -> None:
    try:
        with open(_VERDICTS_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[kr_analyzer] 캐시 저장 실패: {e}")


def _is_cache_valid(entry: dict) -> bool:
    ts_str = entry.get("timestamp", "")
    if not ts_str:
        return False
    try:
        ts = datetime.fromisoformat(ts_str)
        return (datetime.now() - ts).total_seconds() < 86400  # 24h
    except Exception:
        return False


# ─────────────────────────────────────────────
# 단일 종목 분석
# ─────────────────────────────────────────────

def _lookup_stock_info(code: str) -> dict:
    """universe에서 종목 이름/섹터 조회."""
    universe = load_universe()
    clean = code.replace(".KS", "").strip()
    for s in universe:
        if s["code"] == clean:
            return s
    return {"code": clean, "name": clean, "sector": "미분류"}


def analyze_symbol(code: str, regime=None, force_refresh: bool = False) -> KRAnalysisResult:
    """단일 종목 분석.

    Args:
        code: "005930" 또는 "005930.KS"
        regime: KRRegimeDetection (없으면 자동 감지)
        force_refresh: 캐시 무시 여부

    Returns:
        KRAnalysisResult
    """
    clean = code.replace(".KS", "").strip()
    info = _lookup_stock_info(clean)

    # 캐시 확인
    if not force_refresh:
        cache = _load_verdicts_cache()
        entry = cache.get(clean, {})
        if _is_cache_valid(entry):
            print(f"[kr_analyzer] {clean} 캐시 사용 (유효 시간 내)")
            # KRVerdict 객체로 재구성 (JSON → dataclass)
            from kr_research.kr_models import KRVerdict, KRRegimeDetection
            raw_verdicts = entry.pop("verdicts", [])
            raw_regime = entry.pop("regime", None)
            filtered = {k: v for k, v in entry.items() if k in KRAnalysisResult.__dataclass_fields__}
            filtered["verdicts"] = [KRVerdict.from_dict(v) for v in (raw_verdicts or [])]
            if raw_regime:
                filtered["regime"] = KRRegimeDetection(**{
                    k: v for k, v in raw_regime.items()
                    if k in KRRegimeDetection.__dataclass_fields__
                })
            result = KRAnalysisResult(**filtered)
            return result

    if regime is None:
        regime = detect_kr_regime()

    print(f"[kr_analyzer] {clean} ({info['name']}) 분석 중...")
    stock_data = fetch_kr_stock(clean)
    stock_data["sector"] = info.get("sector", "미분류")

    verdicts = run_all_agents(clean, stock_data, regime)
    agg = aggregate_verdicts(verdicts)

    result = KRAnalysisResult(
        symbol=clean,
        name=info.get("name", clean),
        sector=info.get("sector", "미분류"),
        verdicts=verdicts,
        regime=regime,
        weighted_score=agg["weighted_score"],
        agree_count=agg["agree"],
        disagree_count=agg["disagree"],
        caution_count=agg["caution"],
        summary=agg["summary"],
        timestamp=datetime.now().isoformat(),
    )

    # 캐시 저장
    cache = _load_verdicts_cache()
    cache[clean] = result.to_dict()
    _save_verdicts_cache(cache)

    return result


# ─────────────────────────────────────────────
# 섹터 분석
# ─────────────────────────────────────────────

def analyze_sector(sector: str, regime=None) -> list[KRAnalysisResult]:
    """특정 섹터 전체 종목 분석."""
    universe = load_universe()
    sector_stocks = [s for s in universe if s["sector"] == sector]

    if not sector_stocks:
        print(f"[kr_analyzer] 섹터 '{sector}' 에 해당하는 종목 없음")
        return []

    if regime is None:
        regime = detect_kr_regime()

    results = []
    for stock in sector_stocks:
        result = analyze_symbol(stock["code"], regime=regime)
        results.append(result)
        time.sleep(0.3)  # 레이트 리밋

    return results


# ─────────────────────────────────────────────
# 전체 스캔
# ─────────────────────────────────────────────

def analyze_all(regime=None) -> list[KRAnalysisResult]:
    """KOSPI TOP50 전체 스캔."""
    universe = load_universe()
    if regime is None:
        regime = detect_kr_regime()

    results = []
    total = len(universe)
    for i, stock in enumerate(universe, 1):
        print(f"[kr_analyzer] [{i}/{total}] {stock['code']} {stock['name']} 분석 중...")
        result = analyze_symbol(stock["code"], regime=regime)
        results.append(result)
        time.sleep(0.3)

    return results


# ─────────────────────────────────────────────
# 콘솔 출력
# ─────────────────────────────────────────────

def _print_regime(regime) -> None:
    print(f"\nKR Regime: {regime.regime}")
    print(f"  KOSPI/SMA200: {regime.kospi_vs_sma200:.4f}")
    print(f"  VKOSPI:       {regime.vkospi_level:.1f}")
    print(f"  USD/KRW 20d:  {regime.usdkrw_20d_change:+.1f}%")
    print(f"  BOK 금리:     {regime.bok_rate:.2f}%")
    if regime.semiconductor_export_yoy is not None:
        print(f"  반도체수출YoY: {regime.semiconductor_export_yoy:+.0f}%")
    print(f"  근거: {regime.reasoning}\n")


def _print_result(result: KRAnalysisResult) -> None:
    print(f"\n{'='*70}")
    print(f"  {result.symbol} {result.name} ({result.sector})")
    print(f"{'='*70}")

    direction_marks = {"AGREE": "✅", "DISAGREE": "❌", "CAUTION": "⚠️"}
    for v in result.verdicts:
        mark = direction_marks.get(v.direction, "")
        print(
            f"  {v.agent:<30} {mark} {v.direction:<10} "
            f"{v.confidence_delta:+.3f} {v.conviction:<8} "
            f"{v.reasoning[:60]}"
        )

    print(f"\n  Aggregate: {result.agree_count} AGREE / {result.disagree_count} DISAGREE / {result.caution_count} CAUTION")
    print(f"  Weighted Score: {result.weighted_score:+.4f}")
    print(f"  판단: {result.summary}")
    print()


# ─────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────

def run_analysis(
    target: str,
    force_refresh: bool = False,
    report: bool = True,
) -> dict:
    """analyze-kr 커맨드 진입점.

    Args:
        target: "005930" | "sector:반도체" | "all"
        force_refresh: 캐시 무시
        report: 마크다운 리포트 생성 여부

    Returns:
        {"regime": dict, "results": list[dict], "report_path": str}
    """
    regime = detect_kr_regime(force_refresh=force_refresh)
    _print_regime(regime)

    report_path = ""

    if target.startswith("sector:"):
        sector = target.split(":", 1)[1].strip()
        print(f"[kr_analyzer] 섹터 분석: {sector}")
        results = analyze_sector(sector, regime=regime)
        for r in results:
            _print_result(r)
        if report and results:
            report_path = generate_sector_report(results, sector, regime)

    elif target == "all":
        print("[kr_analyzer] KOSPI TOP50 전체 스캔")
        results = analyze_all(regime=regime)
        for r in results:
            _print_result(r)
        if report and results:
            report_path = generate_all_report(results, regime)

    else:
        # 단일 종목
        result = analyze_symbol(target, regime=regime, force_refresh=force_refresh)
        _print_result(result)
        results = [result]
        if report:
            report_path = generate_symbol_report(result, regime)

    if report_path:
        print(f"\n리포트 저장: {report_path}")

    return {
        "regime": regime.to_dict(),
        "results": [r.to_dict() for r in results],
        "report_path": report_path,
    }


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="한국 주식 시장 분석")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--symbol", help="종목 코드 (예: 005930)")
    group.add_argument("--sector", help="섹터명 (예: 반도체)")
    group.add_argument("--all", action="store_true", help="KOSPI TOP50 전체 스캔")
    parser.add_argument("--force-refresh", action="store_true", help="캐시 무시")
    parser.add_argument("--no-report", action="store_true", help="리포트 생성 안함")

    args = parser.parse_args()

    if args.symbol:
        target = args.symbol
    elif args.sector:
        target = f"sector:{args.sector}"
    else:
        target = "all"

    run_analysis(
        target=target,
        force_refresh=args.force_refresh,
        report=not args.no_report,
    )


if __name__ == "__main__":
    main()
