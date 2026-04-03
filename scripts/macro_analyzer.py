"""
매크로 분석 모듈 — 경기사이클 판단 → 유리 섹터 → 대표 종목 추천
"""

# 경기사이클별 유리 섹터 매핑 (Investment Clock 기반)
CYCLE_SECTOR_MAP = {
    "recovery": {
        "label": "회복기 (Recovery)",
        "sectors": ["Technology", "Consumer Disc.", "Industrials", "Financials"],
        "rationale": "금리 인하 + 경기 회복 → 성장주·경기민감주 유리",
    },
    "expansion": {
        "label": "확장기 (Expansion)",
        "sectors": ["Technology", "Industrials", "Materials", "Energy"],
        "rationale": "강한 성장 + 인플레 시작 → 원자재·산업재 수혜",
    },
    "peak": {
        "label": "정점기 (Peak/Overheat)",
        "sectors": ["Energy", "Materials", "Consumer Staples"],
        "rationale": "인플레 가속 + 금리 인상 → 실물자산·방어주 선호",
    },
    "contraction": {
        "label": "수축기 (Contraction)",
        "sectors": ["Healthcare", "Utilities", "Consumer Staples"],
        "rationale": "경기 둔화 + 금리 인하 기대 → 방어주·배당주 유리",
    },
}

# 섹터별 대표 종목 (시총 상위)
SECTOR_REPRESENTATIVES = {
    "Technology": [
        {"symbol": "AAPL", "name": "Apple"},
        {"symbol": "MSFT", "name": "Microsoft"},
        {"symbol": "NVDA", "name": "NVIDIA"},
        {"symbol": "AVGO", "name": "Broadcom"},
    ],
    "Healthcare": [
        {"symbol": "UNH", "name": "UnitedHealth"},
        {"symbol": "JNJ", "name": "Johnson & Johnson"},
        {"symbol": "LLY", "name": "Eli Lilly"},
    ],
    "Financials": [
        {"symbol": "JPM", "name": "JPMorgan Chase"},
        {"symbol": "V", "name": "Visa"},
        {"symbol": "MA", "name": "Mastercard"},
    ],
    "Consumer Disc.": [
        {"symbol": "AMZN", "name": "Amazon"},
        {"symbol": "TSLA", "name": "Tesla"},
        {"symbol": "HD", "name": "Home Depot"},
    ],
    "Communication": [
        {"symbol": "GOOGL", "name": "Alphabet"},
        {"symbol": "META", "name": "Meta"},
        {"symbol": "NFLX", "name": "Netflix"},
    ],
    "Industrials": [
        {"symbol": "CAT", "name": "Caterpillar"},
        {"symbol": "UNP", "name": "Union Pacific"},
        {"symbol": "HON", "name": "Honeywell"},
    ],
    "Consumer Staples": [
        {"symbol": "PG", "name": "Procter & Gamble"},
        {"symbol": "KO", "name": "Coca-Cola"},
        {"symbol": "COST", "name": "Costco"},
    ],
    "Energy": [
        {"symbol": "XOM", "name": "ExxonMobil"},
        {"symbol": "CVX", "name": "Chevron"},
        {"symbol": "COP", "name": "ConocoPhillips"},
    ],
    "Utilities": [
        {"symbol": "NEE", "name": "NextEra Energy"},
        {"symbol": "DUK", "name": "Duke Energy"},
        {"symbol": "SO", "name": "Southern Co."},
    ],
    "Real Estate": [
        {"symbol": "PLD", "name": "Prologis"},
        {"symbol": "AMT", "name": "American Tower"},
        {"symbol": "EQIX", "name": "Equinix"},
    ],
    "Materials": [
        {"symbol": "LIN", "name": "Linde"},
        {"symbol": "APD", "name": "Air Products"},
        {"symbol": "SHW", "name": "Sherwin-Williams"},
    ],
}


def current_cycle(macro_data: dict) -> str:
    """
    현재 경기사이클 위치 판단 (간이 규칙 기반)

    판단 로직 (Investment Clock):
    - 금리 높음 + CPI 높음 + 실업률 낮음 → peak
    - 금리 높음 + CPI 하락 + 실업률 상승 → contraction
    - 금리 낮음/인하 + CPI 낮음 + 실업률 높음 → recovery
    - 금리 낮음 + CPI 상승 + GDP 성장 → expansion
    """
    if not macro_data:
        return "expansion"  # 데이터 없으면 기본값

    fed_rate = macro_data.get("Fed Funds Rate", 3.0)
    cpi = macro_data.get("CPI (YoY)", 250)  # CPI 수준 (인덱스)
    unemployment = macro_data.get("Unemployment", 4.0)
    gdp = macro_data.get("GDP Growth", 2.0)

    # 간이 판단 규칙
    high_rate = fed_rate >= 4.5
    high_unemployment = unemployment >= 5.0

    if high_rate and not high_unemployment:
        return "peak"
    elif high_rate and high_unemployment:
        return "contraction"
    elif not high_rate and high_unemployment:
        return "recovery"
    else:
        return "expansion"


def favored_sectors(cycle: str) -> dict:
    """경기사이클별 유리한 섹터 + 근거"""
    return CYCLE_SECTOR_MAP.get(cycle, CYCLE_SECTOR_MAP["expansion"])


def recommend_stocks(sectors: list[str], top_n: int = 5) -> list[dict]:
    """유리 섹터의 대표 종목 추천"""
    picks = []
    for sector in sectors:
        reps = SECTOR_REPRESENTATIVES.get(sector, [])
        for stock in reps:
            picks.append({**stock, "sector": sector})
            if len(picks) >= top_n:
                return picks
    return picks[:top_n]


if __name__ == "__main__":
    import json

    # 테스트: FRED 데이터 없이 기본값으로 실행
    cycle = current_cycle({})
    print(f"Current Cycle: {cycle}")

    info = favored_sectors(cycle)
    print(f"Label: {info['label']}")
    print(f"Sectors: {info['sectors']}")
    print(f"Rationale: {info['rationale']}")

    picks = recommend_stocks(info["sectors"])
    print(f"\nRecommended Stocks:")
    print(json.dumps(picks, indent=2))
