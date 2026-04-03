"""
종목 심층 분석 모듈 — 텐버거 시뮬레이션 포트폴리오
yfinance: 가격/기술적 지표 | FMP API: 펀더멘털/DCF/13F/내부자거래
"""
import os
import sys
import requests
import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime, date, timedelta

sys.path.insert(0, str(Path(__file__).parent))
from fmp_rate_limiter import can_call, record_calls

FMP_KEY = os.environ.get("FMP_API_KEY", "")
FMP_BASE = "https://financialmodelingprep.com/api"

# ── 포트폴리오 5종목 정적 thesis (전문 트레이더 초기 분석) ─────────────────
STOCK_THESIS = {
    "PLTR": {
        "company": "Palantir Technologies",
        "thesis_short": "정부/기업 AI 플랫폼 독점, 미-이란 분쟁 수혜, 흑자 전환 완료",
        "outlook": {
            "short": "AIP(AI Platform) 상업 계약 확대 + 미국 국방부 지출 증가. 단기 카탈리스트: 분기 실적 발표, 신규 정부 계약 공시. 리스크: 고밸류에이션 조정 가능성.",
            "mid": "미국 + 동맹국 정부 AI 플랫폼 표준 자리 잡기. Gotham(정부)→Foundry(기업)→AIP(AI) 3단계 성장 구조. 상업 고객 ARR 연 50%+ 성장 기대.",
            "long": "AI 시대의 핵심 인프라 레이어. 데이터 통합-분석-의사결정 자동화 전 주기 장악. 10년 TAM $500B+ 시장에서 핵심 플레이어. 텐배거 시나리오: AIP 글로벌 확장 + 국방 AI 독점.",
        },
        "bull": "AIP 상업 고객 연 100%+ 성장, 정부 AI 예산 2배 증가, 흑자 기반 자사주 매입 개시",
        "bear": "경쟁사(Microsoft, Palantir-clone) 진입, 정부 예산 삭감, 높은 주식 기반 보상 희석",
        "risks": ["고밸류에이션 (PSR 30x+)", "내부자 대규모 매도 이력", "정부 의존도 60%+"],
        "sector": "Defense AI / Government Tech",
    },
    "RKLB": {
        "company": "Rocket Lab USA",
        "thesis_short": "우주 경제 유일한 공개 순수주, Neutron 재사용 로켓 임박, TAM $1조",
        "outlook": {
            "short": "Electron 로켓 발사 빈도 증가(월 2회 이상 목표). 소형위성 수요 폭발. 단기 카탈리스트: Neutron 개발 마일스톤 공시. 리스크: 발사 실패 시 주가 급락.",
            "mid": "Neutron 재사용 로켓 첫 발사 성공 시 밸류에이션 재평가. 우주 시스템 사업(위성 부품/솔루션) 매출 비중 증가. NASA/DARPA 계약 확대.",
            "long": "SpaceX 독주 체제에서 유일한 상장 대안. 저궤도 위성 인터넷, 우주 관광, 행성 탐사 등 복합 시장 수혜. Neutron 성공 시 중형 위성 시장 진입으로 TAM 10배 확대.",
        },
        "bull": "Neutron 발사 성공, 대형 위성 계약 수주, 우주 경제 민영화 가속",
        "bear": "Neutron 개발 지연/실패, SpaceX Starship 소형위성 시장 잠식, 자본 소진",
        "risks": ["Neutron 개발 일정 지연 위험", "단발성 발사 실패 시 신뢰도 타격", "지속적 자본 조달 필요"],
        "sector": "Space Economy / Launch Services",
    },
    "HIMS": {
        "company": "Hims & Hers Health",
        "thesis_short": "텔레헬스 + GLP-1 비만약 복제약, 헬스케어 유통 파괴자",
        "outlook": {
            "short": "GLP-1(세마글루타이드) 복제약 공급 확대로 구독자 급증. 탈모/ED/정신건강 구독 기반 안정. 단기 리스크: FDA 복제약 규제 강화 가능성.",
            "mid": "처방전 없이 온라인으로 의약품 접근 가능한 플랫폼 모델 확장. 여성 건강 카테고리 강화. GLP-1 시장 $100B+ 진입 초기.",
            "long": "헬스케어 D2C(Direct-to-Consumer) 혁명의 선두. 처방→유통→복제약 생산 수직통합 완성 시 기존 제약 유통 마진 흡수. 텐배거 시나리오: GLP-1 시장 점유율 5% 달성.",
        },
        "bull": "GLP-1 복제약 시장 선점, 구독 이탈률 감소, 신규 카테고리(여성호르몬/수면) 론칭",
        "bear": "FDA 복제약 공급 중단 명령, 노보노디스크/일라이릴리 직접 경쟁, 보험 미적용",
        "risks": ["FDA 규제 리스크 (가장 중요)", "GLP-1 복제약 사업 불확실성", "의료 책임 소송"],
        "sector": "Telehealth / Consumer Health",
    },
    "APLD": {
        "company": "Applied Digital Corporation",
        "thesis_short": "AI 데이터센터 순수주, CoreWeave 대비 극도 저평가",
        "outlook": {
            "short": "AI 데이터센터 수요 폭발로 계약 증가. HPC(High Performance Computing) 호스팅 계약 공시 예정. 단기 리스크: 전력 조달 비용 상승.",
            "mid": "NVIDIA GPU 클러스터 임대 모델 수익 가시화. 하이퍼스케일러(Microsoft, Google, Amazon)로부터 장기 임대 계약 확보가 핵심.",
            "long": "AI 컴퓨팅 수요는 10년 이상 구조적 성장. 소형 데이터센터 사업자 중 가장 순수한 AI 인프라 플레이. CoreWeave IPO 대비 10배 이상 저평가 상태.",
        },
        "bull": "대형 하이퍼스케일러 장기 계약 체결, 전력 비용 절감 달성, AI 붐 지속",
        "bear": "자본 집약적 사업 구조로 희석 지속, 전력/냉각 비용 급등, 대형 경쟁사 시장 진입",
        "risks": ["높은 부채 비율", "계약 의존도 집중 리스크", "전력 비용 변동성"],
        "sector": "AI Infrastructure / Data Centers",
    },
    "IONQ": {
        "company": "IonQ Inc.",
        "thesis_short": "퀀텀 컴퓨팅 복권, AWS/Azure/Google 파트너십, 소액 베팅",
        "outlook": {
            "short": "퀀텀 컴퓨팅 산업화 초기 단계. 정부 R&D 계약 + 클라우드 플랫폼 파트너십으로 매출 발생. 단기는 순수 투기적 성격 강함.",
            "mid": "Forte Enterprise 시스템 출시로 기업 고객 확보 가속. 의약품 개발, 암호화, 금융 최적화 분야 파일럿 증가.",
            "long": "퀀텀 우위(Quantum Advantage) 달성 시 기존 컴퓨팅 전면 대체. 5-10년 타임라인. 성공 시 수백 배 수익 가능한 진정한 복권 티켓.",
        },
        "bull": "퀀텀 우위 조기 달성, 대형 제약/금융 계약, 정부 퀀텀 예산 10배 증가",
        "bear": "퀀텀 실용화 10년 이상 지연, IBM/Google의 퀀텀 기술 선점, 자금 소진",
        "risks": ["기술 실현 타임라인 극히 불확실", "경쟁사 대비 기술 우위 미검증", "상업화까지 대규모 자금 필요"],
        "sector": "Quantum Computing",
    },
}


# ── 기술적 지표 계산 ─────────────────────────────────────────────────────────

def _calc_rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("inf"))
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return round(float(val), 1) if not pd.isna(val) else None


def _calc_macd(series: pd.Series):
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    val_macd = macd.iloc[-1]
    val_signal = signal.iloc[-1]
    if pd.isna(val_macd) or pd.isna(val_signal):
        return None, None, "N/A"
    diff = val_macd - val_signal
    trend = "상승" if diff > 0 else "하락"
    return round(float(val_macd), 3), round(float(val_signal), 3), trend


def fetch_technical(symbol: str) -> dict:
    """yfinance로 가격 + 기술적 지표 수집"""
    try:
        tk = yf.Ticker(symbol)
        hist = tk.history(period="1y")
        if hist.empty:
            return {"error": f"{symbol} 데이터 없음"}

        close = hist["Close"]
        volume = hist["Volume"]
        current = float(close.iloc[-1])
        prev = float(close.iloc[-2]) if len(close) > 1 else current
        change = current - prev
        change_pct = (change / prev) * 100 if prev else 0

        ma50 = float(close.rolling(50).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1])
        high52 = float(close.max())
        low52 = float(close.min())
        avg_vol20 = float(volume.rolling(20).mean().iloc[-1])
        latest_vol = float(volume.iloc[-1])
        vol_ratio = latest_vol / avg_vol20 if avg_vol20 else 1.0

        rsi = _calc_rsi(close)
        macd_val, macd_sig, macd_trend = _calc_macd(close)

        return {
            "current_price": round(current, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "volume": int(latest_vol),
            "volume_ratio": round(vol_ratio, 2),
            "ma50": round(ma50, 2),
            "ma200": round(ma200, 2),
            "above_ma50": current > ma50,
            "above_ma200": current > ma200,
            "high_52w": round(high52, 2),
            "low_52w": round(low52, 2),
            "pct_from_52w_high": round((current - high52) / high52 * 100, 1),
            "rsi": rsi,
            "macd": macd_val,
            "macd_signal": macd_sig,
            "macd_trend": macd_trend,
        }
    except Exception as e:
        return {"error": str(e)}


# ── FMP API 헬퍼 ─────────────────────────────────────────────────────────────

def _fmp_get(endpoint: str, params: dict = None) -> dict | list | None:
    if not FMP_KEY:
        return None
    try:
        p = {"apikey": FMP_KEY}
        if params:
            p.update(params)
        r = requests.get(f"{FMP_BASE}{endpoint}", params=p, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def fetch_fundamental(symbol: str) -> dict:
    """FMP API로 펀더멘털 + DCF 수집 (rate limiter 적용)"""
    result = {
        "per": None, "pbr": None, "psr": None,
        "revenue_growth": None, "operating_margin": None,
        "fcf": None, "debt_ratio": None,
        "dcf_price": None, "dcf_upside": None,
        "current_price": None,
    }

    if not FMP_KEY:
        result["note"] = "FMP_API_KEY 없음 — 펀더멘털 스킵"
        return result

    allowed, msg = can_call(2)
    if not allowed:
        result["note"] = msg
        return result

    # Key metrics (PER, PBR, PSR, FCF 등)
    km = _fmp_get(f"/v3/key-metrics/{symbol}", {"limit": 2, "period": "annual"})
    record_calls(1, f"key-metrics:{symbol}")

    if km and len(km) > 0:
        latest = km[0]
        result["per"] = _safe_round(latest.get("peRatio"))
        result["pbr"] = _safe_round(latest.get("pbRatio"))
        result["psr"] = _safe_round(latest.get("priceToSalesRatio"))
        result["fcf"] = _safe_round(latest.get("freeCashFlowPerShare"))

    # DCF
    dcf = _fmp_get(f"/v3/discounted-cash-flow/{symbol}")
    record_calls(1, f"dcf:{symbol}")
    if dcf and isinstance(dcf, list) and len(dcf) > 0:
        dcf_price = dcf[0].get("dcf")
        stock_price = dcf[0].get("Stock Price")
        if dcf_price and stock_price:
            result["dcf_price"] = round(float(dcf_price), 2)
            result["current_price"] = round(float(stock_price), 2)
            upside = (float(dcf_price) - float(stock_price)) / float(stock_price) * 100
            result["dcf_upside"] = round(upside, 1)

    # Income statement (revenue growth, operating margin)
    income = _fmp_get(f"/v3/income-statement/{symbol}", {"limit": 2, "period": "annual"})
    if income and len(income) >= 2:
        record_calls(1, f"income:{symbol}")
        rev_now = income[0].get("revenue", 0)
        rev_prev = income[1].get("revenue", 1)
        op_income = income[0].get("operatingIncome", 0)
        if rev_prev and rev_now:
            result["revenue_growth"] = round((rev_now - rev_prev) / rev_prev * 100, 1)
        if rev_now:
            result["operating_margin"] = round(op_income / rev_now * 100, 1)

    return result


def fetch_institutional(symbol: str) -> dict:
    """FMP API로 기관투자자(13F) + 내부자 거래 수집"""
    result = {
        "top_institutions": [],
        "insider_buy": 0,
        "insider_sell": 0,
        "short_float": None,
    }

    if not FMP_KEY:
        result["note"] = "FMP_API_KEY 없음"
        return result

    allowed, msg = can_call(2)
    if not allowed:
        result["note"] = msg
        return result

    # 기관 투자자
    inst = _fmp_get(f"/v3/institutional-holder/{symbol}")
    record_calls(1, f"institutional:{symbol}")
    if inst and isinstance(inst, list):
        result["top_institutions"] = [
            {"name": h.get("holder", ""), "shares": h.get("shares", 0), "change": h.get("change", 0)}
            for h in inst[:3]
        ]

    # 내부자 거래 (최근 30일)
    insider = _fmp_get(f"/v4/insider-trading", {"symbol": symbol, "limit": 20})
    record_calls(1, f"insider:{symbol}")
    if insider and isinstance(insider, list):
        cutoff = date.today() - timedelta(days=30)
        for tx in insider:
            tx_date_str = tx.get("transactionDate", "")
            try:
                tx_date = date.fromisoformat(tx_date_str[:10])
                if tx_date >= cutoff:
                    tx_type = tx.get("transactionType", "")
                    if "P-Purchase" in tx_type or "Buy" in tx_type:
                        result["insider_buy"] += 1
                    elif "S-Sale" in tx_type or "Sell" in tx_type:
                        result["insider_sell"] += 1
            except Exception:
                pass

    return result


def _safe_round(val, digits=2):
    try:
        return round(float(val), digits) if val is not None else None
    except (TypeError, ValueError):
        return None


# ── 메인 분석 함수 ────────────────────────────────────────────────────────────

def analyze_stock(symbol: str) -> dict:
    """단일 종목 전체 분석 반환"""
    thesis = STOCK_THESIS.get(symbol, {
        "company": symbol,
        "thesis_short": "",
        "outlook": {"short": "N/A", "mid": "N/A", "long": "N/A"},
        "bull": "N/A", "bear": "N/A",
        "risks": [],
        "sector": "Unknown",
    })

    technical = fetch_technical(symbol)
    fundamental = fetch_fundamental(symbol)
    institutional = fetch_institutional(symbol)

    return {
        "symbol": symbol,
        "company": thesis["company"],
        "sector": thesis["sector"],
        "thesis_short": thesis["thesis_short"],
        "technical": technical,
        "fundamental": fundamental,
        "institutional": institutional,
        "outlook": thesis["outlook"],
        "thesis": {
            "bull": thesis["bull"],
            "bear": thesis["bear"],
            "risks": thesis["risks"],
        },
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def analyze_portfolio(symbols: list) -> list:
    """포트폴리오 전체 종목 분석"""
    results = []
    for symbol in symbols:
        print(f"  → {symbol} 분석 중...", file=sys.stderr)
        data = analyze_stock(symbol)
        results.append(data)
    return results
