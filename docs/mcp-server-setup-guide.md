# MCP 서버 설치 가이드 — Yahoo Finance + FMP + Korean Stock

> 생성일: 2026-04-03 | STOCK_WORK 프로젝트용

---

## 설치할 MCP 서버 3개

| # | MCP 서버 | 목적 | 데이터 |
|---|---------|------|--------|
| 1 | Yahoo Finance MCP | 글로벌 주가/재무/옵션/뉴스 | 무제한 (비공식) |
| 2 | Financial Modeling Prep (FMP) | 미국 대기업 심층 재무 (SEC 파싱) | 250콜/일 (무료) |
| 3 | Korean Stock (DART & KRX) | 한국 주식 + DART 공시 | DART API 키 필요 |

---

## 1. Yahoo Finance MCP

### GitHub
- https://github.com/Alex2Yang97/yahoo-finance-mcp
- 또는 https://github.com/barvhaim/yfinance-mcp-server

### 설치 (uvx 방식)
```bash
# Claude Code에서 MCP 서버 추가
claude mcp add yahoo-finance -- uvx yahoo-finance-mcp
```

### 또는 settings.json에 직접 추가
```json
{
  "mcpServers": {
    "yahoo-finance": {
      "command": "uvx",
      "args": ["yahoo-finance-mcp"]
    }
  }
}
```

### 제공 기능
- 실시간/히스토리컬 주가 (OHLCV)
- 기본 재무제표 (Income Statement, Balance Sheet, Cash Flow)
- 옵션 체인
- 뉴스/추천등급
- 종목 정보 (시가총액, PE, 배당 등)

---

## 2. Financial Modeling Prep (FMP)

### API 키 발급
1. https://financialmodelingprep.com/ 가입
2. Free Plan 선택 (250 API calls/day)
3. Dashboard에서 API Key 복사

### GitHub
- https://github.com/aekanun2020/mcp-server-fmp (또는 유사)

### 설치
```bash
# pip으로 설치
pip install mcp-server-fmp

# Claude Code에서 MCP 서버 추가
claude mcp add fmp -- python -m mcp_server_fmp --api-key YOUR_FMP_API_KEY
```

### 또는 settings.json에 직접 추가
```json
{
  "mcpServers": {
    "fmp": {
      "command": "python",
      "args": ["-m", "mcp_server_fmp", "--api-key", "YOUR_FMP_API_KEY"],
      "env": {
        "FMP_API_KEY": "YOUR_FMP_API_KEY"
      }
    }
  }
}
```

### 제공 기능 (무료 250콜/일)
- SEC 10-K/10-Q 파싱된 재무제표 (30년 히스토리)
- DCF Valuation 데이터
- 애널리스트 추정치/목표가
- 기업 프로필/실적 캘린더
- 섹터별 성과
- 기관 보유 현황 (13F 기반)

---

## 3. Korean Stock (DART & KRX) MCP

### DART API 키 발급
1. https://opendart.fss.or.kr/ 가입
2. 인증키 신청 → 발급 (즉시)

### GitHub
- https://github.com/your-repo/korean-stock-mcp (FastMCP 기반)

### 설치
```bash
# pip으로 설치
pip install korean-stock-mcp

# Claude Code에서 MCP 서버 추가
claude mcp add korean-stock -- python -m korean_stock_mcp --dart-api-key YOUR_DART_KEY
```

### 또는 settings.json에 직접 추가
```json
{
  "mcpServers": {
    "korean-stock": {
      "command": "python",
      "args": ["-m", "korean_stock_mcp"],
      "env": {
        "DART_API_KEY": "YOUR_DART_KEY"
      }
    }
  }
}
```

### 제공 기능
- KOSPI/KOSDAQ/KONEX 전 종목 시세
- DART 전자공시 (사업보고서, 재무제표, 주요사항 등)
- pykrx 기반 히스토리컬 데이터
- 외국인/기관/개인 매매 동향

---

## 설치 후 STOCK_WORK settings.json 최종 형태

```json
{
  "permissions": {
    "allow": [
      "Bash(python3 -:*)",
      "Bash(git:*)",
      "Bash(bash .claude/hooks/*)"
    ],
    "deny": [
      "Bash(rm -rf:*)"
    ]
  },
  "mcpServers": {
    "yahoo-finance": {
      "command": "uvx",
      "args": ["yahoo-finance-mcp"]
    },
    "fmp": {
      "command": "python",
      "args": ["-m", "mcp_server_fmp"],
      "env": {
        "FMP_API_KEY": "${FMP_API_KEY}"
      }
    },
    "korean-stock": {
      "command": "python",
      "args": ["-m", "korean_stock_mcp"],
      "env": {
        "DART_API_KEY": "${DART_API_KEY}"
      }
    }
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/protect-sensitive-files.sh"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/investment-risk-gate.sh"
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/log-agent-usage.sh"
          }
        ]
      }
    ]
  }
}
```

---

## .env 파일 (API 키 관리)

```bash
# STOCK_WORK/.env (git에서 제외됨)
FMP_API_KEY=your_fmp_api_key_here
DART_API_KEY=your_dart_api_key_here
FRED_API_KEY=your_fred_api_key_here
```

---

## 설치 순서

```
1. FMP 가입 → API 키 발급 (https://financialmodelingprep.com/)
2. DART 가입 → API 키 발급 (https://opendart.fss.or.kr/)
3. .env 파일에 키 저장
4. STOCK_WORK 세션에서:
   claude mcp add yahoo-finance -- uvx yahoo-finance-mcp
   claude mcp add fmp -- python -m mcp_server_fmp
   claude mcp add korean-stock -- python -m korean_stock_mcp
5. Claude Code 재시작
6. "삼성전자 주가 알려줘" 로 테스트
```

---

## 에이전트 연동 구조

```
사용자: "애플 재무 분석해줘"
    │
    ▼
orchestrator → 패턴1 (종합 종목)
    │
    ├── ST-01 equity-research
    │     └── FMP MCP → 10년치 재무제표, DCF 데이터
    │
    ├── ST-02 technical-strategist
    │     └── Yahoo Finance MCP → OHLCV 차트 데이터
    │
    └── ST-03 macro-economist
          └── FRED API → 금리/CPI/고용 매크로 데이터
    │
    ▼
D6 investment-expert → 통합 투자 의견
```
