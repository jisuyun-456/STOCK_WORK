# Graph Report - .  (2026-04-14)

## Corpus Check
- 61 files · ~83,644 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 793 nodes · 1714 edges · 44 communities detected
- Extraction: 66% EXTRACTED · 34% INFERRED · 0% AMBIGUOUS · INFERRED: 580 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]

## God Nodes (most connected - your core abstractions)
1. `Direction` - 120 edges
2. `Signal` - 105 edges
3. `LeveragedETFStrategy` - 81 edges
4. `ResearchVerdict` - 64 edges
5. `RegimeDetection` - 57 edges
6. `QuantFactorStrategy` - 45 edges
7. `ValueQualityStrategy` - 44 edges
8. `MomentumStrategy` - 43 edges
9. `BaseStrategy` - 40 edges
10. `_make_strat()` - 39 edges

## Surprising Connections (you probably didn't know these)
- `Research Cache — avoid re-analyzing the same stock within TTL window.` --uses--> `ResearchVerdict`  [INFERRED]
  research\cache.py → research\models.py
- `Coerce numpy types to native Python so json.dump succeeds.      Python 3.14 의` --uses--> `ResearchVerdict`  [INFERRED]
  research\cache.py → research\models.py
- `Return cached verdicts if valid, else None.` --uses--> `ResearchVerdict`  [INFERRED]
  research\cache.py → research\models.py
- `Store verdicts in cache.` --uses--> `ResearchVerdict`  [INFERRED]
  research\cache.py → research\models.py
- `Clear entire cache (e.g., on regime change).` --uses--> `ResearchVerdict`  [INFERRED]
  research\cache.py → research\models.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (124): BaseStrategy, Direction, Base strategy interface and Signal data structures for paper trading., A trade signal produced by a strategy module., Abstract base class for all trading strategies.      Strategies are determinis, Check if rebalancing is due based on frequency., Signal, BaseStrategy (+116 more)

### Community 1 - "Community 1"
Cohesion: 0.04
Nodes (44): A_BasicRegimeTest, B_RegimeTransitionTest, C_DeltaRebalanceTest, D_EdgeCaseTest, E_WhipsawTest, F_MonthlySimulationTest, G_IntegrationTest, H_OrderSafetyTest (+36 more)

### Community 2 - "Community 2"
Cohesion: 0.03
Nodes (54): ABC, get_analyst_consensus(), yfinance ticker.info → 애널리스트 컨센서스 + 목표주가.  Usage:     from fundamentals.analyst, 종목별 애널리스트 추천 지수와 목표주가를 반환한다.      Returns:         {symbol: {             "rec_m, APSource, Associated Press RSS news source adapter., NewsSource, Abstract base class for news source adapters. (+46 more)

### Community 3 - "Community 3"
Cohesion: 0.13
Nodes (34): _append_monitor_log(), _apply_paperclip_verdicts(), _audit_log(), _backup_state_files(), _build_symbol_strategy_map(), _check_allocation_integrity(), _check_negative_cash(), _ensure_inception() (+26 more)

### Community 4 - "Community 4"
Cohesion: 0.11
Nodes (28): System prompts for Research Division agents.  Derived from .claude/agents/*.md, _build_agent_context(), _gemini_call_with_retry(), _get_claude_client(), _get_gemini_client(), get_research_mode(), _parse_verdict_json(), Hybrid LLM agent runner for Research Overlay.  Supports 3 modes: - rules: Ori (+20 more)

### Community 5 - "Community 5"
Cohesion: 0.1
Nodes (24): append_and_save(), build_daily_snapshot(), build_sparkline_path(), _compute_mdd(), _compute_sharpe(), compute_strategy_metrics(), _compute_win_rate(), _empty_metrics() (+16 more)

### Community 6 - "Community 6"
Cohesion: 0.15
Nodes (19): build_report_context(), collect_comps_data(), collect_dcf_data(), collect_financial_data(), _ensure_v1_defaults(), _fmp_get(), _fmt_m(), generate_equity_report() (+11 more)

### Community 7 - "Community 7"
Cohesion: 0.15
Nodes (21): close_position(), get_account_info(), get_client(), get_open_orders(), get_order_by_client_id(), get_positions(), is_market_open(), _order_to_dict() (+13 more)

### Community 8 - "Community 8"
Cohesion: 0.15
Nodes (21): _arrow(), _build_dashboard_context(), _build_paper_dashboard_context(), _build_ticker_data(), _fmt_pct(), _fmt_price(), _fmt_value(), generate_dashboard() (+13 more)

### Community 9 - "Community 9"
Cohesion: 0.15
Nodes (20): _build_symbol_strategy_map(), copy_to_obsidian(), generate_daily_analysis(), _get_account(), _get_market_data(), _get_positions(), _get_regime_and_news(), _load_portfolios() (+12 more)

### Community 10 - "Community 10"
Cohesion: 0.19
Nodes (18): check_cash_buffer(), check_correlation(), check_portfolio_var(), check_position_limit(), check_sector_concentration(), get_sector(), _load_sector_cache(), Pre-trade risk validation — 5 risk gates that every signal must pass.  Gates: (+10 more)

### Community 11 - "Community 11"
Cohesion: 0.19
Nodes (15): _dedup_by_title(), fetch_all_news(), fetch_macro_news(), fetch_macro_news_enhanced(), fetch_news(), fetch_rss_news(), News fetcher — yfinance 뉴스 수집 + BeautifulSoup 본문 스크래핑.  yf.Ticker(symbol).news, 종목의 최신 뉴스를 yfinance에서 수집하고 본문을 스크래핑한다.      yf.Ticker(symbol).news 에서 URL 목록을 (+7 more)

### Community 12 - "Community 12"
Cohesion: 0.18
Nodes (15): _parse_atom_entry(), _parse_date(), parse_rss_feed(), _parse_rss_item(), Generic RSS/Atom feed parser using xml.etree.ElementTree (stdlib)., Get text content with Atom namespace fallback., Remove HTML tags from text., Parse RFC 2822 date to ISO format. Returns raw string on failure. (+7 more)

### Community 13 - "Community 13"
Cohesion: 0.21
Nodes (15): analyze_portfolio(), analyze_stock(), _calc_macd(), _calc_rsi(), fetch_fundamental(), fetch_institutional(), fetch_technical(), _fmp_get() (+7 more)

### Community 14 - "Community 14"
Cohesion: 0.19
Nodes (14): check_portfolio_mdd(), check_stop_loss(), check_strategy_mdd(), check_take_profit(), check_trailing_stop(), evaluate_position(), get_config(), Intraday Monitor Rules Engine — stop-loss, take-profit, trailing stop.  Each che (+6 more)

### Community 15 - "Community 15"
Cohesion: 0.21
Nodes (13): get_cached(), invalidate_all(), invalidate_symbol(), _json_default(), _load_cache(), Research Cache — avoid re-analyzing the same stock within TTL window., Coerce numpy types to native Python so json.dump succeeds.      Python 3.14 의, Return cached verdicts if valid, else None. (+5 more)

### Community 16 - "Community 16"
Cohesion: 0.42
Nodes (13): _fmt_pct(), _fmt_price(), _get_price_change(), _load_portfolios(), main(), yfinance로 단기/장기 등락률 조회., _section(), section_global() (+5 more)

### Community 17 - "Community 17"
Cohesion: 0.27
Nodes (12): _build_headline(), _build_summary(), _determine_mood(), generate_market_commentary(), _get_key_opportunity(), _get_key_risk(), _get_kr_summary(), _get_sector_leaders() (+4 more)

### Community 18 - "Community 18"
Cohesion: 0.19
Nodes (12): _get_env(), 리포트 포맷터 — Jinja2 기반 Markdown/HTML 렌더링 + 파일 저장, Jinja2 → Markdown (daily_report.md.j2), Jinja2 → HTML (email_template.html), docs/reports/YYYY-MM-DD-daily.md 저장, Jinja2 → 시뮬레이션 상세 Markdown (simulation_section.md.j2), docs/simulation/YYYY-MM-DD-simulation.md 저장, save_report() (+4 more)

### Community 19 - "Community 19"
Cohesion: 0.31
Nodes (12): _get_current_price(), get_portfolio_summary(), init_portfolio(), load_state(), main(), 시뮬레이션 포트폴리오 트래커 - portfolio_state.json 초기화 / P&L 업데이트 / 요약 반환 - CLI: python si, 당일 종가로 P&L 업데이트 + daily_snapshots 누적, 일일 리포트에서 호출: 상태 로드 → 업데이트 → 요약 반환 (+4 more)

### Community 20 - "Community 20"
Cohesion: 0.23
Nodes (11): _classify_trend(), _compute_bollinger(), compute_indicators(), _compute_macd(), _compute_rsi(), Technical indicators — RSI, MACD, Bollinger Bands, Volume analysis.  Pure pand, Compute MACD line, signal line, histogram, and cross signal., Compute Bollinger Bands and %B. (+3 more)

### Community 21 - "Community 21"
Cohesion: 0.18
Nodes (9): fetch_kr_indices(), fetch_macro(), fetch_sector_performance(), fetch_us_indices(), 데이터 수집 모듈 — yfinance(미국/글로벌/한국) + FRED(매크로), 기준금리, CPI, 실업률, GDP (FRED_API_KEY 없으면 빈 dict), 나스닥, S&P500, DJI, VIX 전일 데이터, S&P500 11개 섹터 ETF 등락률 (+1 more)

### Community 22 - "Community 22"
Cohesion: 0.31
Nodes (10): _patch_config(), strategy_params.json 파라미터 → 전략 클래스 반영 검증 테스트., min_composite_score=0.45 설정 시 낮은 스코어 종목이 제외되는지 확인., test_momentum_reads_max_positions(), test_momentum_reads_position_pct(), test_momentum_reads_stop_loss(), test_qnt_min_composite_score_filters(), test_qnt_reads_max_positions() (+2 more)

### Community 23 - "Community 23"
Cohesion: 0.24
Nodes (9): compute_polymarket_score(), fetch_macro_markets(), _log_weight(), PolymarketSignal, Polymarket prediction market integration for macro regime signals.  Fetches pu, Aggregate prediction market data into a macro sentiment score.      Score: -1., Convert volume to log-scale weight., Single prediction market data point. (+1 more)

### Community 24 - "Community 24"
Cohesion: 0.4
Nodes (9): can_call(), get_status(), _load(), main(), FMP API Rate Limiter — 250콜/일 한도 관리 사용법:   python scripts/fmp_rate_limiter.py ch, n콜을 실행할 수 있는지 확인.     Returns: (허용 여부, 메시지), n콜 사용 기록. 차단 시 기록하지 않고 에러 반환., record_calls() (+1 more)

### Community 25 - "Community 25"
Cohesion: 0.31
Nodes (4): _current_weights(), get_target_mix(), _needs_rebalance(), _positions_market_value()

### Community 26 - "Community 26"
Cohesion: 0.32
Nodes (7): fetch_google_news_symbol(), _parse_pub_date(), Google News RSS — 종목별 뉴스 검색 수집기.  Google News RSS 검색 엔드포인트를 사용해 특정 종목에 대한 최신 기사를, HTML 태그/엔티티 제거 후 공백 정리., RFC 822 날짜 → ISO 8601 UTC 문자열., 종목별 Google News RSS 기사 수집.      Args:         symbol: 종목 티커 (예: "AAPL"), _strip_html()

### Community 27 - "Community 27"
Cohesion: 0.36
Nodes (7): generate_report(), main(), 일일 투자 리포트 메인 오케스트레이터 CLI: python3 scripts/daily_report.py [--mode auto|manual], Gmail SMTP로 리포트 이메일 발송 (PDF 첨부 옵션), email_summary.html 렌더링 (1페이지 요약), _render_email_summary(), send_email()

### Community 28 - "Community 28"
Cohesion: 0.25
Nodes (7): generate_html_preview(), generate_pdf(), get_pdf_path(), PDF 생성 모듈 — WeasyPrint + Jinja2 templates/pdf_report.html → A4 PDF, docs/reports/YYYY-MM-DD-report.pdf, context → templates/pdf_report.html 렌더링 → WeasyPrint → PDF 저장     반환: 저장된 PDF 파, PDF 생성이 불가한 환경(Windows 로컬)에서 HTML 미리보기 저장     반환: 저장된 HTML 파일 경로

### Community 29 - "Community 29"
Cohesion: 0.46
Nodes (7): apply_rebalance_risk_gate(), _check_drift(), compute_rebalance_orders(), _get_strategy_signals(), _is_schedule_due(), run_rebalance_check(), should_rebalance()

### Community 30 - "Community 30"
Cohesion: 0.29
Nodes (5): 떠오르는 기업 스크리닝 — 거래량 급등, 52주 신고가, 섹터별 모멘텀 yfinance 기반 (OpenBB screener 대체), 거래량 급등 TOP N — 최근 거래량 vs 20일 평균 비율, 11개 섹터 ETF 1주/1개월 수익률, sector_momentum(), volume_surge()

### Community 31 - "Community 31"
Cohesion: 0.43
Nodes (6): _audit_list(), _classify(), _load_json(), main(), Return 'LIVE' | 'STALE' | 'DELISTED' for a single ticker., Classify every ticker in a universe list.

### Community 32 - "Community 32"
Cohesion: 0.4
Nodes (5): load_strategy_params(), strategy_params.json 로더 — 모듈 레벨 캐시로 중복 IO 방지., strategy_params.json을 읽어 dict로 반환. 모듈 캐시 사용., 캐시를 버리고 다시 읽는다 (테스트/변경 감지용)., reload_strategy_params()

### Community 33 - "Community 33"
Cohesion: 0.53
Nodes (5): calculate_consensus(), detect_regime(), detect_regime_enhanced(), get_regime_weights(), _neutral_fallback()

### Community 34 - "Community 34"
Cohesion: 0.33
Nodes (3): current_cycle(), 매크로 분석 모듈 — 경기사이클 판단 → 유리 섹터 → 대표 종목 추천, 현재 경기사이클 위치 판단 (간이 규칙 기반)      판단 로직 (Investment Clock):     - 금리 높음 + CPI 높음 +

### Community 35 - "Community 35"
Cohesion: 0.9
Nodes (4): execute_signal(), execute_signals(), _log_result(), _next_seq()

### Community 36 - "Community 36"
Cohesion: 0.6
Nodes (3): _fetch_fmp_profile(), fetch_value_data(), _fetch_yf_fundamentals()

### Community 37 - "Community 37"
Cohesion: 0.83
Nodes (3): _load_json(), main(), _section()

### Community 38 - "Community 38"
Cohesion: 0.5
Nodes (3): ExitRule, Exit rules for a position., Default exit rules. Override per strategy if needed.

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (0): 

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (1): Fetch articles from this source.          Returns:             [{"title", "bo

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (1): Generate order ID prefix for strategy attribution.

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (1): Generate trade signals from market data.          Args:             market_da

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **173 isolated node(s):** `strategy_params.json 로더 — 모듈 레벨 캐시로 중복 IO 방지.`, `strategy_params.json을 읽어 dict로 반환. 모듈 캐시 사용.`, `캐시를 버리고 다시 읽는다 (테스트/변경 감지용).`, `Alpaca Trading Client — paper/live toggle via environment variable.  Switch be`, `Get singleton Alpaca TradingClient.      Environment variables required:` (+168 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 39`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (1 nodes): `Fetch articles from this source.          Returns:             [{"title", "bo`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (1 nodes): `Generate order ID prefix for strategy attribution.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (1 nodes): `Generate trade signals from market data.          Args:             market_da`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Direction` connect `Community 0` to `Community 1`?**
  _High betweenness centrality (0.077) - this node is a cross-community bridge._
- **Why does `Signal` connect `Community 0` to `Community 4`?**
  _High betweenness centrality (0.076) - this node is a cross-community bridge._
- **Are the 118 inferred relationships involving `Direction` (e.g. with `numpy 스칼라 타입을 native Python으로 변환 (Python 3.14 호환).` and `C5 fix: portfolios.json에 inception 필드가 없으면 현재 allocated로 초기화.      inception.t`) actually correct?**
  _`Direction` has 118 INFERRED edges - model-reasoned connections that need verification._
- **Are the 103 inferred relationships involving `Signal` (e.g. with `numpy 스칼라 타입을 native Python으로 변환 (Python 3.14 호환).` and `C5 fix: portfolios.json에 inception 필드가 없으면 현재 allocated로 초기화.      inception.t`) actually correct?**
  _`Signal` has 103 INFERRED edges - model-reasoned connections that need verification._
- **Are the 76 inferred relationships involving `LeveragedETFStrategy` (e.g. with `numpy 스칼라 타입을 native Python으로 변환 (Python 3.14 호환).` and `C5 fix: portfolios.json에 inception 필드가 없으면 현재 allocated로 초기화.      inception.t`) actually correct?**
  _`LeveragedETFStrategy` has 76 INFERRED edges - model-reasoned connections that need verification._
- **Are the 61 inferred relationships involving `ResearchVerdict` (e.g. with `numpy 스칼라 타입을 native Python으로 변환 (Python 3.14 호환).` and `C5 fix: portfolios.json에 inception 필드가 없으면 현재 allocated로 초기화.      inception.t`) actually correct?**
  _`ResearchVerdict` has 61 INFERRED edges - model-reasoned connections that need verification._
- **Are the 55 inferred relationships involving `RegimeDetection` (e.g. with `numpy 스칼라 타입을 native Python으로 변환 (Python 3.14 호환).` and `C5 fix: portfolios.json에 inception 필드가 없으면 현재 allocated로 초기화.      inception.t`) actually correct?**
  _`RegimeDetection` has 55 INFERRED edges - model-reasoned connections that need verification._