"""한국 시장 분석 리포트 생성기.

reports/kr/YYYY-MM-DD-kr-analysis.md 파일 생성.
"""

from __future__ import annotations

import os
from datetime import datetime

from kr_research.kr_models import KRAnalysisResult, KRRegimeDetection


_REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports", "kr")


def _ensure_dir() -> None:
    os.makedirs(_REPORTS_DIR, exist_ok=True)


def _regime_emoji(regime: str) -> str:
    return {
        "BULL": "📈", "EUPHORIA": "🚀", "NEUTRAL": "➡️",
        "BEAR": "📉", "CRISIS": "🚨",
    }.get(regime, "")


def _verdict_line(verdict) -> str:
    direction_mark = {"AGREE": "✅", "DISAGREE": "❌", "CAUTION": "⚠️"}.get(verdict.direction, "")
    delta_str = f"{verdict.confidence_delta:+.3f}"
    return (
        f"| {verdict.agent:<30} | {direction_mark} {verdict.direction:<10} "
        f"| {delta_str} {verdict.conviction:<8} "
        f"| {verdict.reasoning[:80]} |"
    )


def generate_symbol_report(
    result: KRAnalysisResult,
    regime: KRRegimeDetection,
) -> str:
    """단일 종목 분석 리포트 생성 → 파일 경로 반환."""
    _ensure_dir()

    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{today}-kr-{result.symbol}-analysis.md"
    filepath = os.path.join(_REPORTS_DIR, filename)

    emoji = _regime_emoji(regime.regime)
    lines = [
        f"# 한국 주식 분석 — {result.symbol} {result.name}",
        f"> 생성일: {today} | KR Regime: {emoji} **{regime.regime}**",
        "",
        "## Regime 스냅샷",
        f"| 지표 | 값 |",
        f"|------|-----|",
        f"| KOSPI/SMA200 | {regime.kospi_vs_sma200:.4f} |",
        f"| VKOSPI | {regime.vkospi_level:.1f} |",
        f"| USD/KRW 20일 변화 | {regime.usdkrw_20d_change:+.1f}% |",
        f"| BOK 기준금리 | {regime.bok_rate:.2f}% |",
    ]
    if regime.semiconductor_export_yoy is not None:
        lines.append(f"| 반도체 수출 YoY | {regime.semiconductor_export_yoy:+.0f}% |")
    lines += [
        "",
        f"**Regime 판단:** {regime.reasoning}",
        "",
        "## 분석 결과",
        f"- **종목:** {result.symbol} {result.name} ({result.sector})",
        f"- **종합 점수:** {result.weighted_score:+.4f}",
        f"- **AGREE / DISAGREE / CAUTION:** {result.agree_count} / {result.disagree_count} / {result.caution_count}",
        f"- **판단:** {result.summary}",
        "",
        "## 에이전트 상세",
        "| 에이전트 | 방향 | 점수/확신 | 근거 |",
        "|----------|------|-----------|------|",
    ]

    for verdict in result.verdicts:
        lines.append(_verdict_line(verdict))

    lines += [
        "",
        "## 주요 지표",
        "```json",
    ]
    for verdict in result.verdicts:
        if verdict.key_metrics:
            lines.append(f"// {verdict.agent}")
            for k, v in verdict.key_metrics.items():
                lines.append(f"  {k}: {v}")
    lines += [
        "```",
        "",
        "---",
        "_분석 전용 — 매매 실행 없음. 투자 판단은 본인 책임._",
    ]

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


def generate_sector_report(
    results: list[KRAnalysisResult],
    sector: str,
    regime: KRRegimeDetection,
) -> str:
    """섹터 분석 리포트 생성 → 파일 경로 반환."""
    _ensure_dir()

    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{today}-kr-sector-{sector}-analysis.md"
    filepath = os.path.join(_REPORTS_DIR, filename)

    # 점수 내림차순 정렬
    sorted_results = sorted(results, key=lambda r: r.weighted_score, reverse=True)
    emoji = _regime_emoji(regime.regime)

    lines = [
        f"# 한국 섹터 분석 — {sector}",
        f"> 생성일: {today} | KR Regime: {emoji} **{regime.regime}**",
        "",
        "## 섹터 종목 랭킹",
        f"| 순위 | 코드 | 종목명 | 점수 | 판단 |",
        f"|------|------|--------|------|------|",
    ]

    for i, r in enumerate(sorted_results, 1):
        lines.append(
            f"| {i} | {r.symbol} | {r.name} | {r.weighted_score:+.4f} | {r.summary} |"
        )

    lines += [
        "",
        "---",
        "_분석 전용 — 매매 실행 없음._",
    ]

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


def generate_all_report(
    results: list[KRAnalysisResult],
    regime: KRRegimeDetection,
) -> str:
    """전체 KOSPI TOP50 스캔 리포트 → 파일 경로 반환."""
    _ensure_dir()

    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{today}-kr-full-scan.md"
    filepath = os.path.join(_REPORTS_DIR, filename)

    sorted_results = sorted(results, key=lambda r: r.weighted_score, reverse=True)
    emoji = _regime_emoji(regime.regime)

    top10 = sorted_results[:10]
    bottom10 = sorted_results[-10:]

    lines = [
        f"# KOSPI TOP50 전체 스캔 — {today}",
        f"> KR Regime: {emoji} **{regime.regime}** | 총 분석 종목: {len(results)}",
        "",
        "## TOP 10 (매수 신호)",
        "| 순위 | 코드 | 종목명 | 섹터 | 점수 | 판단 |",
        "|------|------|--------|------|------|------|",
    ]
    for i, r in enumerate(top10, 1):
        lines.append(f"| {i} | {r.symbol} | {r.name} | {r.sector} | {r.weighted_score:+.4f} | {r.summary} |")

    lines += [
        "",
        "## BOTTOM 10 (매도/회피 신호)",
        "| 순위 | 코드 | 종목명 | 섹터 | 점수 | 판단 |",
        "|------|------|--------|------|------|------|",
    ]
    for i, r in enumerate(bottom10, 1):
        lines.append(f"| {i} | {r.symbol} | {r.name} | {r.sector} | {r.weighted_score:+.4f} | {r.summary} |")

    lines += [
        "",
        "---",
        "_분석 전용 — 매매 실행 없음._",
    ]

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath
