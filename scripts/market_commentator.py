"""
Rule-based 시황 코멘트 생성 모듈
데이터 기반으로 신한증권 마켓뷰 스타일의 시황 요약 생성
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


# ── 섹터 한글명 매핑 ──────────────────────────────────────────────────────────
SECTOR_KR = {
    "Technology": "기술",
    "Healthcare": "헬스케어",
    "Financials": "금융",
    "Consumer Disc.": "소비재(경기)",
    "Communication": "커뮤니케이션",
    "Industrials": "산업재",
    "Consumer Staples": "필수소비재",
    "Energy": "에너지",
    "Utilities": "유틸리티",
    "Real Estate": "리얼에스테이트",
    "Materials": "소재",
}


def _get_vix_signal(vix_close: float) -> tuple[str, str]:
    """VIX 수치 → (무드, 설명)"""
    if vix_close is None:
        return "NEUTRAL", "VIX 데이터 없음"
    if vix_close > 30:
        return "RISK-OFF", f"VIX {vix_close:.1f} — 극심한 공포 구간, 방어적 포지션 유지"
    if vix_close > 25:
        return "RISK-OFF", f"VIX {vix_close:.1f} — 공포 구간, 단기 변동성 확대"
    if vix_close > 20:
        return "CAUTION", f"VIX {vix_close:.1f} — 경계 구간, 리스크 관리 필요"
    if vix_close > 15:
        return "NEUTRAL", f"VIX {vix_close:.1f} — 중립 구간"
    return "RISK-ON", f"VIX {vix_close:.1f} — 낮은 변동성, 위험선호 환경"


def _get_wti_signal(wti_change_pct: float, wti_close: float) -> str:
    """WTI 변화율 → 에너지 비용 해석"""
    if wti_change_pct is None:
        return "WTI 데이터 없음"
    if wti_change_pct >= 10:
        return f"WTI ${wti_close:.1f} ({wti_change_pct:+.1f}%) — 에너지 비용 급등 경고, 인플레 우려"
    if wti_change_pct >= 5:
        return f"WTI ${wti_close:.1f} ({wti_change_pct:+.1f}%) — 에너지 비용 상승 주의"
    if wti_change_pct <= -5:
        return f"WTI ${wti_close:.1f} ({wti_change_pct:+.1f}%) — 유가 하락, 에너지 비용 완화"
    return f"WTI ${wti_close:.1f} ({wti_change_pct:+.1f}%) — 안정적"


def _get_kr_summary(kr_indices: dict) -> str:
    """한국 시장 요약"""
    kospi = kr_indices.get("KOSPI", {})
    if kospi.get("error"):
        return "KOSPI 데이터 없음"
    close = kospi.get("close", 0)
    pct = kospi.get("change_pct", 0)
    if pct >= 2:
        return f"KOSPI {close:,.2f} ({pct:+.2f}%) — 강한 반등, 외국인 수급 확인 필요"
    if pct >= 0.5:
        return f"KOSPI {close:,.2f} ({pct:+.2f}%) — 소폭 상승"
    if pct <= -2:
        return f"KOSPI {close:,.2f} ({pct:+.2f}%) — 급락, 외국인 매도 지속 우려"
    if pct <= -0.5:
        return f"KOSPI {close:,.2f} ({pct:+.2f}%) — 약세"
    return f"KOSPI {close:,.2f} ({pct:+.2f}%) — 보합"


def _get_sector_leaders(sectors_daily: dict) -> tuple[str, str]:
    """당일 섹터 상승/하락 1위"""
    if not sectors_daily:
        return "N/A", "N/A"
    valid = {k: v for k, v in sectors_daily.items() if not v.get("error") and v.get("change_pct") is not None}
    if not valid:
        return "N/A", "N/A"
    top = max(valid, key=lambda k: valid[k]["change_pct"])
    bot = min(valid, key=lambda k: valid[k]["change_pct"])
    top_kr = SECTOR_KR.get(top, top)
    bot_kr = SECTOR_KR.get(bot, bot)
    top_pct = valid[top]["change_pct"]
    bot_pct = valid[bot]["change_pct"]
    return f"{top_kr} ({top_pct:+.2f}%)", f"{bot_kr} ({bot_pct:+.2f}%)"


def _determine_mood(vix_mood: str, nasdaq_pct: float, wti_pct: float, sectors_daily: dict) -> str:
    """종합 시장 무드 결정"""
    risk_off_signals = 0
    risk_on_signals = 0

    if vix_mood == "RISK-OFF":
        risk_off_signals += 2
    elif vix_mood == "CAUTION":
        risk_off_signals += 1
    elif vix_mood == "RISK-ON":
        risk_on_signals += 1

    if nasdaq_pct is not None:
        if nasdaq_pct >= 1:
            risk_on_signals += 1
        elif nasdaq_pct <= -1:
            risk_off_signals += 1

    if wti_pct is not None and wti_pct >= 5:
        risk_off_signals += 1

    if sectors_daily:
        valid = [v for v in sectors_daily.values() if not v.get("error") and v.get("change_pct") is not None]
        up = sum(1 for v in valid if v["change_pct"] > 0)
        total = len(valid)
        if total > 0:
            if up / total >= 0.7:
                risk_on_signals += 1
            elif up / total <= 0.3:
                risk_off_signals += 1

    if risk_off_signals >= 2:
        return "RISK-OFF"
    if risk_on_signals >= 2:
        return "RISK-ON"
    return "NEUTRAL"


def _build_headline(market_mood: str, top_sector: str, nasdaq_pct: float, wti_pct: float) -> str:
    """헤드라인 자동 생성"""
    if market_mood == "RISK-OFF":
        if wti_pct is not None and wti_pct >= 5:
            return f"유가 급등 + 변동성 확대 — 방어적 포지션 권고"
        return f"위험회피 심화 — {top_sector} 선별 강세, 전반적 약세 압력"
    if market_mood == "RISK-ON":
        if nasdaq_pct is not None and nasdaq_pct >= 1:
            return f"나스닥 반등 주도 — {top_sector} 수혜, 위험선호 회복"
        return f"위험선호 환경 — {top_sector} 상승, 성장주 모멘텀 유효"
    return f"혼조세 지속 — {top_sector} 부각, 선별적 대응 필요"


def _build_summary(us_indices: dict, kr_indices: dict, commodities: dict, market_mood: str) -> str:
    """2-3문장 데이터 기반 시황 요약"""
    lines = []

    nasdaq = us_indices.get("NASDAQ", {})
    if not nasdaq.get("error"):
        pct = nasdaq.get("change_pct", 0)
        close = nasdaq.get("close", 0)
        lines.append(f"나스닥 {close:,.0f}pt ({pct:+.2f}%)")

    kospi = kr_indices.get("KOSPI", {})
    if not kospi.get("error"):
        pct = kospi.get("change_pct", 0)
        close = kospi.get("close", 0)
        lines.append(f"KOSPI {close:,.2f}pt ({pct:+.2f}%)")

    wti = commodities.get("WTI Oil", {})
    gold = commodities.get("Gold", {})
    if not wti.get("error"):
        lines.append(f"WTI ${wti.get('close', 0):.1f} ({wti.get('change_pct', 0):+.1f}%)")
    if not gold.get("error"):
        lines.append(f"금 ${gold.get('close', 0):,.0f} ({gold.get('change_pct', 0):+.1f}%)")

    summary = " | ".join(lines)

    if market_mood == "RISK-OFF":
        summary += ". 지정학 리스크 및 변동성 확대로 안전자산 선호 심리 강화."
    elif market_mood == "RISK-ON":
        summary += ". 위험선호 심리 회복, 성장 자산 전반 상승 흐름."
    else:
        summary += ". 혼조세 속 개별 종목 및 섹터별 차별화 장세."

    return summary


def _get_key_risk(market_mood: str, vix_close: float, wti_pct: float, nasdaq_pct: float) -> str:
    """핵심 리스크 1가지"""
    if wti_pct is not None and wti_pct >= 10:
        return f"유가 급등({wti_pct:+.1f}%) → 인플레 재점화 + 기업 마진 압박"
    if vix_close is not None and vix_close > 25:
        return f"VIX {vix_close:.1f} — 시장 변동성 극대화, 급락 가능성"
    if nasdaq_pct is not None and nasdaq_pct <= -2:
        return f"나스닥 급락({nasdaq_pct:+.1f}%) — 성장주 밸류에이션 재평가"
    if market_mood == "RISK-OFF":
        return "지정학 리스크 장기화 — 투자심리 위축, 외국인 자금 유출"
    return "금리 불확실성 — Fed 피벗 지연 시 성장주 밸류에이션 조정"


def _get_key_opportunity(top_sector: str, market_mood: str, wti_pct: float) -> str:
    """핵심 기회 1가지"""
    if wti_pct is not None and wti_pct >= 5:
        return "에너지 안보 테마 — 재생에너지·방산 관련주 모멘텀 강화"
    if market_mood == "RISK-OFF":
        return "변동성 확대 = 우량주 매수 기회 — 장기 thesis 훼손 없는 종목 비중 확대"
    return f"{top_sector} 섹터 로테이션 수혜 — 모멘텀 지속 여부 확인 후 대응"


# ── 메인 함수 ─────────────────────────────────────────────────────────────────

def generate_market_commentary(
    us_indices: dict,
    kr_indices: dict,
    commodities: dict,
    sectors_daily: dict,
    macro: dict,
    volume_surge: list,
) -> dict:
    """시황 코멘트 생성 (rule-based)"""

    # 핵심 지표 추출
    vix_data = us_indices.get("VIX", {})
    vix_close = vix_data.get("close") if not vix_data.get("error") else None

    nasdaq_data = us_indices.get("NASDAQ", {})
    nasdaq_pct = nasdaq_data.get("change_pct") if not nasdaq_data.get("error") else None

    wti_data = commodities.get("WTI Oil", {})
    wti_pct = wti_data.get("change_pct") if not wti_data.get("error") else None
    wti_close = wti_data.get("close") if not wti_data.get("error") else None

    # 분석
    vix_mood, vix_signal = _get_vix_signal(vix_close)
    wti_signal = _get_wti_signal(wti_pct, wti_close)
    kr_summary = _get_kr_summary(kr_indices)
    top_sector, bottom_sector = _get_sector_leaders(sectors_daily)
    market_mood = _determine_mood(vix_mood, nasdaq_pct, wti_pct, sectors_daily)
    headline = _build_headline(market_mood, top_sector, nasdaq_pct, wti_pct)
    summary = _build_summary(us_indices, kr_indices, commodities, market_mood)
    key_risk = _get_key_risk(market_mood, vix_close, wti_pct, nasdaq_pct)
    key_opportunity = _get_key_opportunity(top_sector, market_mood, wti_pct)

    return {
        "headline": headline,
        "summary": summary,
        "vix_signal": vix_signal,
        "wti_signal": wti_signal,
        "kr_summary": kr_summary,
        "top_sector": top_sector,
        "bottom_sector": bottom_sector,
        "market_mood": market_mood,
        "key_risk": key_risk,
        "key_opportunity": key_opportunity,
    }
