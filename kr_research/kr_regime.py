"""한국 시장 Regime 판별.

Regime Matrix:
  CRISIS:    KOSPI/SMA200 < 0.95 AND VKOSPI > 35
  BEAR:      KOSPI/SMA200 < 1.00 AND VKOSPI > 25
  BULL:      KOSPI/SMA200 > 1.05 AND VKOSPI < 18 AND BOK 금리 cut/hold
  EUPHORIA:  KOSPI/SMA200 > 1.10 AND VKOSPI < 15 AND BOK cut
  NEUTRAL:   그 외

보정 (반도체 수출 YoY):
  > +30%  → BULL conviction 상향
  < -10%  → BULL→NEUTRAL 다운그레이드
"""

from __future__ import annotations

from datetime import datetime

from kr_research.kr_data_fetcher import build_market_snapshot
from kr_research.kr_models import KRRegimeDetection

# Conviction 가중치 (KRAnalysisResult 집계 시 사용)
CONVICTION_WEIGHTS = {"STRONG": 1.0, "MODERATE": 0.6, "WEAK": 0.3}


def detect_kr_regime(force_refresh: bool = False) -> KRRegimeDetection:
    """KOSPI/SMA200 × VKOSPI × BOK 기준금리 → Regime 판별.

    Args:
        force_refresh: True면 캐시 무시하고 데이터 재수집

    Returns:
        KRRegimeDetection
    """
    snapshot = build_market_snapshot(force_refresh=force_refresh)

    kospi = snapshot.get("kospi", {})
    vkospi = snapshot.get("vkospi", {})
    usdkrw = snapshot.get("usdkrw", {})
    bok = snapshot.get("bok_rate", {})
    semi = snapshot.get("semiconductor_export", {})

    ratio = kospi.get("kospi_vs_sma200", 1.0)
    vkospi_level = vkospi.get("level", 20.0)
    krw_change = usdkrw.get("20d_change_pct", 0.0)
    bok_rate = bok.get("rate", 3.0)
    semi_yoy = semi.get("yoy_pct")  # None 가능

    # ── Regime 판별 ──────────────────────────────
    regime = "NEUTRAL"
    reasoning_parts = []

    if ratio < 0.95 and vkospi_level > 35:
        regime = "CRISIS"
        reasoning_parts.append(f"KOSPI/SMA200={ratio:.3f} (<0.95), VKOSPI={vkospi_level:.1f} (>35)")
    elif ratio < 1.00 and vkospi_level > 25:
        regime = "BEAR"
        reasoning_parts.append(f"KOSPI/SMA200={ratio:.3f} (<1.00), VKOSPI={vkospi_level:.1f} (>25)")
    elif ratio > 1.10 and vkospi_level < 15:
        regime = "EUPHORIA"
        reasoning_parts.append(f"KOSPI/SMA200={ratio:.3f} (>1.10), VKOSPI={vkospi_level:.1f} (<15)")
    elif ratio > 1.05 and vkospi_level < 18:
        regime = "BULL"
        reasoning_parts.append(f"KOSPI/SMA200={ratio:.3f} (>1.05), VKOSPI={vkospi_level:.1f} (<18)")
    else:
        reasoning_parts.append(f"KOSPI/SMA200={ratio:.3f}, VKOSPI={vkospi_level:.1f} - 중립 구간")

    # ── 반도체 수출 보정 ──────────────────────────
    if semi_yoy is not None:
        if semi_yoy > 30 and regime == "BULL":
            reasoning_parts.append(f"반도체 수출 YoY +{semi_yoy:.0f}% → BULL conviction 상향")
        elif semi_yoy < -10 and regime == "BULL":
            regime = "NEUTRAL"
            reasoning_parts.append(f"반도체 수출 YoY {semi_yoy:.0f}% (<-10%) → BULL→NEUTRAL 다운그레이드")

    # ── KRW 추가 컨텍스트 ──────────────────────────
    if krw_change > 2.0:
        reasoning_parts.append(f"KRW/USD 20일 +{krw_change:.1f}% (원화 약세 → 수출주 우호)")
    elif krw_change < -2.0:
        reasoning_parts.append(f"KRW/USD 20일 {krw_change:.1f}% (원화 강세 → 수출주 부담)")

    reasoning_parts.append(f"BOK 기준금리 {bok_rate:.2f}%")

    return KRRegimeDetection(
        regime=regime,
        kospi_vs_sma200=ratio,
        vkospi_level=vkospi_level,
        usdkrw_20d_change=krw_change,
        bok_rate=bok_rate,
        semiconductor_export_yoy=semi_yoy,
        reasoning=". ".join(reasoning_parts),
        timestamp=datetime.now().isoformat(),
    )
