# Graph Report - .  (2026-04-16)

## Corpus Check
- 80 files · ~110,281 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1314 nodes · 3056 edges · 83 communities detected
- Extraction: 57% EXTRACTED · 43% INFERRED · 0% AMBIGUOUS · INFERRED: 1322 edges (avg confidence: 0.5)
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
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]

## God Nodes (most connected - your core abstractions)
1. `Direction` - 219 edges
2. `Signal` - 199 edges
3. `LeveragedETFStrategy` - 134 edges
4. `RegimeDetection` - 125 edges
5. `ValueQualityStrategy` - 115 edges
6. `QuantFactorStrategy` - 98 edges
7. `MomentumStrategy` - 96 edges
8. `ResearchVerdict` - 79 edges
9. `GrowthSmallCapStrategy` - 68 edges
10. `BaseStrategy` - 67 edges

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
Cohesion: 0.08
Nodes (142): Hybrid LLM agent runner for Research Overlay.  Supports 3 modes: - rules: Ori, Build context message for a specific agent., Parse LLM response into ResearchVerdict., Parse LLM response into ResearchVerdict., Get Anthropic client. Returns None if unavailable., Run 5 agents in parallel via Claude API (Haiku 4.5)., Gemini API call with exponential backoff on 429., Run 5 agents sequentially via Gemini Flash (rate limit aware with retry). (+134 more)

### Community 1 - "Community 1"
Cohesion: 0.03
Nodes (114): BaseStrategy, Direction, ExitRule, Base strategy interface and Signal data structures for paper trading., Exit rules for a position., Abstract base class for all trading strategies.      Strategies are determinis, Default exit rules. Override per strategy if needed., Check if rebalancing is due based on frequency. (+106 more)

### Community 2 - "Community 2"
Cohesion: 0.04
Nodes (70): BacktestReport, calc_alpha(), calc_mdd(), calc_sharpe(), calc_win_rate(), detect_regime(), detect_regime_hmm_vectorized(), generate_windows() (+62 more)

### Community 3 - "Community 3"
Cohesion: 0.05
Nodes (43): A_BasicRegimeTest, B_RegimeTransitionTest, C_DeltaRebalanceTest, D_EdgeCaseTest, E_WhipsawTest, F_MonthlySimulationTest, H_OrderSafetyTest, I_CapitalInjectionTest (+35 more)

### Community 4 - "Community 4"
Cohesion: 0.03
Nodes (54): ABC, get_analyst_consensus(), yfinance ticker.info → 애널리스트 컨센서스 + 목표주가.  Usage:     from fundamentals.analyst, 종목별 애널리스트 추천 지수와 목표주가를 반환한다.      Returns:         {symbol: {             "rec_m, APSource, Associated Press RSS news source adapter., NewsSource, Abstract base class for news source adapters. (+46 more)

### Community 5 - "Community 5"
Cohesion: 0.05
Nodes (14): _atom_xml(), tests/test_news_triggers.py — news.triggers 단위 테스트.  모든 외부 네트워크(yfinance, SEC ED, requests.get mock: CIK JSON 첫 호출, Atom XML 두 번째 호출., CIK 없는 티커는 건너뛰고 다른 종목에 영향 없음., SEC 서버 오류 시 graceful False., User-Agent 헤더가 SEC 요구 사항 준수 (식별 가능한 문자열 포함)., CIK JSON은 1회만 로드 (캐시 작동)., FOMC True 면 yfinance/SEC 호출 없음. (+6 more)

### Community 6 - "Community 6"
Cohesion: 0.06
Nodes (16): EUPHORIA (5th regime) tests — allocator, consensus detection, HMM score., EUPHORIA는 BULL과 같은 점수(1.0) — HMM 연속 스코어링 일관성., score_from_regime_prob이 EUPHORIA 확률을 올바르게 반영한다., EUPHORIA 50% + BULL 50% → score ≈ 1.0 (둘 다 최고점)., LEV + LEV_ST는 모든 레짐에서 0.50 고정., 과매수 리스크 축소 — BULL(0%)보다 CASH 비율이 높아야 한다., EUPHORIA → BEAR 전환 시 exit signal 발생해야 한다 (severity 0)., EUPHORIA → BULL 전환은 리스크 감소이므로 exit signal 없음. (+8 more)

### Community 7 - "Community 7"
Cohesion: 0.13
Nodes (34): _append_monitor_log(), _audit_log(), _backup_state_files(), _build_symbol_strategy_map(), _check_allocation_integrity(), _check_inception_drift(), _check_negative_cash(), _collect_held_symbols() (+26 more)

### Community 8 - "Community 8"
Cohesion: 0.09
Nodes (30): System prompts for Research Division agents.  Derived from .claude/agents/*.md, _build_agent_context(), _get_claude_client(), get_research_mode(), _parse_verdict_json(), run_all_agents(), run_all_agents_appeal(), _run_claude_agents() (+22 more)

### Community 9 - "Community 9"
Cohesion: 0.1
Nodes (21): _generate_signals(), _make_fundamentals(), _make_strategy(), tests/test_value_quality_crisis.py  VAL 전략의 CRISIS 레짐 gate 통과율 개선 검증. 핵심: 필터 통과, position_pct 미설정 시 기본값 = 1/max_positions., position_pct=0.15 < 1/max_positions(0.20) → 0.15 적용., 수정 후 risk_validator position_limit 체크 통과 시뮬., VAL position_limit = 0.25 → weight 0.20 ≤ 0.25 → PASS. (+13 more)

### Community 10 - "Community 10"
Cohesion: 0.11
Nodes (28): _build_symbol_strategy_map(), _calc_cumulative_returns(), _calc_daily_pnl(), _calc_mdd(), _calc_position_aging(), copy_to_obsidian(), generate_daily_analysis(), _get_account() (+20 more)

### Community 11 - "Community 11"
Cohesion: 0.1
Nodes (24): append_and_save(), build_daily_snapshot(), build_sparkline_path(), _compute_mdd(), _compute_sharpe(), compute_strategy_metrics(), _compute_win_rate(), _empty_metrics() (+16 more)

### Community 12 - "Community 12"
Cohesion: 0.15
Nodes (19): build_report_context(), collect_comps_data(), collect_dcf_data(), collect_financial_data(), _ensure_v1_defaults(), _fmp_get(), _fmt_m(), generate_equity_report() (+11 more)

### Community 13 - "Community 13"
Cohesion: 0.15
Nodes (21): close_position(), get_account_info(), get_client(), get_open_orders(), get_order_by_client_id(), get_positions(), is_market_open(), _order_to_dict() (+13 more)

### Community 14 - "Community 14"
Cohesion: 0.15
Nodes (21): _arrow(), _build_dashboard_context(), _build_paper_dashboard_context(), _build_ticker_data(), _fmt_pct(), _fmt_price(), _fmt_value(), generate_dashboard() (+13 more)

### Community 15 - "Community 15"
Cohesion: 0.18
Nodes (20): check_cash_buffer(), check_correlation(), check_cross_strategy_concentration(), check_portfolio_var(), check_position_limit(), check_sector_concentration(), get_sector(), _load_sector_cache() (+12 more)

### Community 16 - "Community 16"
Cohesion: 0.16
Nodes (15): _bdate_range(), _mk_regime_data(), Synthetic 3-ticker universe: LEADER has 30% return, others flat., test_calc_alpha_negative(), test_detect_regime_bear(), test_detect_regime_bull(), test_detect_regime_crisis(), test_detect_regime_neutral() (+7 more)

### Community 17 - "Community 17"
Cohesion: 0.17
Nodes (19): clean_lock_file(), _mk_portfolios(), _mk_signal(), Remove actual lock file before and after each test to prevent state leak., Build minimal portfolios.json structure with synthetic NAV history., test_caution_at_minus_3pct_daily(), test_caution_halves_buy_weights(), test_clear_lock_unblocks() (+11 more)

### Community 18 - "Community 18"
Cohesion: 0.18
Nodes (13): _apply_hysteresis(), _count_transitions(), _detect_flicker(), run_cycle.py 하이스테리시스 로직 미러 (독립 테스트용)., test_flicker_off_at_3_transitions(), test_flicker_off_when_no_transitions(), test_flicker_on_at_4_transitions(), test_flicker_on_with_mixed_regimes() (+5 more)

### Community 19 - "Community 19"
Cohesion: 0.23
Nodes (5): _make_market_data(), _make_prices(), tests/test_growth_smallcap.py — GrowthSmallCapStrategy 유닛 테스트, TestFetchGrowthData, TestGenerateSignals

### Community 20 - "Community 20"
Cohesion: 0.19
Nodes (15): _dedup_by_title(), fetch_all_news(), fetch_macro_news(), fetch_macro_news_enhanced(), fetch_news(), fetch_rss_news(), News fetcher — yfinance 뉴스 수집 + BeautifulSoup 본문 스크래핑.  yf.Ticker(symbol).news, 종목의 최신 뉴스를 yfinance에서 수집하고 본문을 스크래핑한다.      yf.Ticker(symbol).news 에서 URL 목록을 (+7 more)

### Community 21 - "Community 21"
Cohesion: 0.18
Nodes (15): _parse_atom_entry(), _parse_date(), parse_rss_feed(), _parse_rss_item(), Generic RSS/Atom feed parser using xml.etree.ElementTree (stdlib)., Get text content with Atom namespace fallback., Remove HTML tags from text., Parse RFC 2822 date to ISO format. Returns raw string on failure. (+7 more)

### Community 22 - "Community 22"
Cohesion: 0.21
Nodes (15): analyze_portfolio(), analyze_stock(), _calc_macd(), _calc_rsi(), fetch_fundamental(), fetch_institutional(), fetch_technical(), _fmp_get() (+7 more)

### Community 23 - "Community 23"
Cohesion: 0.19
Nodes (14): _calc_rsi(), calculate_consensus(), _classify_regime_from_data(), detect_regime(), detect_regime_enhanced(), get_regime_weights(), _neutral_fallback(), Weighted Consensus algorithm with Regime-Aware dynamic weighting. (+6 more)

### Community 24 - "Community 24"
Cohesion: 0.2
Nodes (13): _cik_for(), has_8k_filing(), is_earnings_week(), is_fomc_week(), _load_cik_cache(), News analysis triggers.  뉴스 수집/감성 분석을 실제로 수행해야 하는 3가지 조건을 판단한다: 1) FOMC week, SEC EDGAR company_tickers.json 에서 Ticker→CIK 매핑을 로드한다 (1회 캐시)., Ticker → 10자리 zero-padded CIK. 없으면 None. (+5 more)

### Community 25 - "Community 25"
Cohesion: 0.42
Nodes (13): _fmt_pct(), _fmt_price(), _get_price_change(), _load_portfolios(), main(), yfinance로 단기/장기 등락률 조회., _section(), section_global() (+5 more)

### Community 26 - "Community 26"
Cohesion: 0.2
Nodes (10): Cross-strategy sector concentration gate tests., MOM/VAL/QNT 전략별 sector limit이 30% 이하인지 확인., check_cross_strategy_concentration() 단위 테스트., portfolios['strategies'] 한 항목 형식 생성., test_blocks_when_cross_strategy_exceeds_threshold(), test_empty_positions_passes(), test_passes_when_below_threshold(), test_trade_value_included_in_calculation() (+2 more)

### Community 27 - "Community 27"
Cohesion: 0.23
Nodes (12): check_stop_loss(), check_strategy_mdd(), check_take_profit(), check_trailing_stop(), evaluate_position(), get_config(), Intraday Monitor Rules Engine — stop-loss, take-profit, trailing stop.  Each che, Hard stop-loss: exit if unrealized P&L % breaches threshold. (+4 more)

### Community 28 - "Community 28"
Cohesion: 0.27
Nodes (12): _build_headline(), _build_summary(), _determine_mood(), generate_market_commentary(), _get_key_opportunity(), _get_key_risk(), _get_kr_summary(), _get_sector_leaders() (+4 more)

### Community 29 - "Community 29"
Cohesion: 0.19
Nodes (12): _get_env(), 리포트 포맷터 — Jinja2 기반 Markdown/HTML 렌더링 + 파일 저장, Jinja2 → Markdown (daily_report.md.j2), Jinja2 → HTML (email_template.html), docs/reports/YYYY-MM-DD-daily.md 저장, Jinja2 → 시뮬레이션 상세 Markdown (simulation_section.md.j2), docs/simulation/YYYY-MM-DD-simulation.md 저장, save_report() (+4 more)

### Community 30 - "Community 30"
Cohesion: 0.31
Nodes (12): _get_current_price(), get_portfolio_summary(), init_portfolio(), load_state(), main(), 시뮬레이션 포트폴리오 트래커 - portfolio_state.json 초기화 / P&L 업데이트 / 요약 반환 - CLI: python si, 당일 종가로 P&L 업데이트 + daily_snapshots 누적, 일일 리포트에서 호출: 상태 로드 → 업데이트 → 요약 반환 (+4 more)

### Community 31 - "Community 31"
Cohesion: 0.26
Nodes (12): _patch_config(), strategy_params.json 파라미터 → 전략 클래스 반영 검증 테스트., min_composite_score=0.45 설정 시 낮은 스코어 종목이 제외되는지 확인., target_weight = 1/max_positions (not 1/len(ranked)).      Bug history: 1/len(r, test_momentum_reads_max_positions(), test_momentum_reads_position_pct(), test_momentum_reads_stop_loss(), test_qnt_min_composite_score_filters() (+4 more)

### Community 32 - "Community 32"
Cohesion: 0.23
Nodes (11): _classify_trend(), _compute_bollinger(), compute_indicators(), _compute_macd(), _compute_rsi(), Technical indicators — RSI, MACD, Bollinger Bands, Volume analysis.  Pure pand, Compute MACD line, signal line, histogram, and cross signal., Compute Bollinger Bands and %B. (+3 more)

### Community 33 - "Community 33"
Cohesion: 0.29
Nodes (10): _all_tickers(), _fetch_ff5(), fetch_historical(), _load_ff5_csv(), _load_prices_csv(), Download Kenneth French FF5 daily factors via pandas_datareader., Union of all strategy universes + benchmarks., Returns (prices, spy, vix, ff5).      prices: DataFrame[dates × tickers]     spy (+2 more)

### Community 34 - "Community 34"
Cohesion: 0.18
Nodes (9): fetch_kr_indices(), fetch_macro(), fetch_sector_performance(), fetch_us_indices(), 데이터 수집 모듈 — yfinance(미국/글로벌/한국) + FRED(매크로), 기준금리, CPI, 실업률, GDP (FRED_API_KEY 없으면 빈 dict), 나스닥, S&P500, DJI, VIX 전일 데이터, S&P500 11개 섹터 ETF 등락률 (+1 more)

### Community 35 - "Community 35"
Cohesion: 0.24
Nodes (9): compute_polymarket_score(), fetch_macro_markets(), _log_weight(), PolymarketSignal, Polymarket prediction market integration for macro regime signals.  Fetches pu, Aggregate prediction market data into a macro sentiment score.      Score: -1., Convert volume to log-scale weight., Single prediction market data point. (+1 more)

### Community 36 - "Community 36"
Cohesion: 0.4
Nodes (9): can_call(), get_status(), _load(), main(), FMP API Rate Limiter — 250콜/일 한도 관리 사용법:   python scripts/fmp_rate_limiter.py ch, n콜을 실행할 수 있는지 확인.     Returns: (허용 여부, 메시지), n콜 사용 기록. 차단 시 기록하지 않고 에러 반환., record_calls() (+1 more)

### Community 37 - "Community 37"
Cohesion: 0.22
Nodes (1): G_IntegrationTest

### Community 38 - "Community 38"
Cohesion: 0.31
Nodes (4): _current_weights(), get_target_mix(), _needs_rebalance(), _positions_market_value()

### Community 39 - "Community 39"
Cohesion: 0.32
Nodes (7): fetch_google_news_symbol(), _parse_pub_date(), Google News RSS — 종목별 뉴스 검색 수집기.  Google News RSS 검색 엔드포인트를 사용해 특정 종목에 대한 최신 기사를, HTML 태그/엔티티 제거 후 공백 정리., RFC 822 날짜 → ISO 8601 UTC 문자열., 종목별 Google News RSS 기사 수집.      Args:         symbol: 종목 티커 (예: "AAPL"), _strip_html()

### Community 40 - "Community 40"
Cohesion: 0.36
Nodes (7): generate_report(), main(), 일일 투자 리포트 메인 오케스트레이터 CLI: python3 scripts/daily_report.py [--mode auto|manual], Gmail SMTP로 리포트 이메일 발송 (PDF 첨부 옵션), email_summary.html 렌더링 (1페이지 요약), _render_email_summary(), send_email()

### Community 41 - "Community 41"
Cohesion: 0.25
Nodes (7): generate_html_preview(), generate_pdf(), get_pdf_path(), PDF 생성 모듈 — WeasyPrint + Jinja2 templates/pdf_report.html → A4 PDF, docs/reports/YYYY-MM-DD-report.pdf, context → templates/pdf_report.html 렌더링 → WeasyPrint → PDF 저장     반환: 저장된 PDF 파, PDF 생성이 불가한 환경(Windows 로컬)에서 HTML 미리보기 저장     반환: 저장된 HTML 파일 경로

### Community 42 - "Community 42"
Cohesion: 0.46
Nodes (7): apply_rebalance_risk_gate(), _check_drift(), compute_rebalance_orders(), _get_strategy_signals(), _is_schedule_due(), run_rebalance_check(), should_rebalance()

### Community 43 - "Community 43"
Cohesion: 0.29
Nodes (5): 떠오르는 기업 스크리닝 — 거래량 급등, 52주 신고가, 섹터별 모멘텀 yfinance 기반 (OpenBB screener 대체), 거래량 급등 TOP N — 최근 거래량 vs 20일 평균 비율, 11개 섹터 ETF 1주/1개월 수익률, sector_momentum(), volume_surge()

### Community 44 - "Community 44"
Cohesion: 0.43
Nodes (6): _audit_list(), _classify(), _load_json(), main(), Return 'LIVE' | 'STALE' | 'DELISTED' for a single ticker., Classify every ticker in a universe list.

### Community 45 - "Community 45"
Cohesion: 0.4
Nodes (5): load_strategy_params(), strategy_params.json 로더 — 모듈 레벨 캐시로 중복 IO 방지., strategy_params.json을 읽어 dict로 반환. 모듈 캐시 사용., 캐시를 버리고 다시 읽는다 (테스트/변경 감지용)., reload_strategy_params()

### Community 46 - "Community 46"
Cohesion: 0.33
Nodes (3): current_cycle(), 매크로 분석 모듈 — 경기사이클 판단 → 유리 섹터 → 대표 종목 추천, 현재 경기사이클 위치 판단 (간이 규칙 기반)      판단 로직 (Investment Clock):     - 금리 높음 + CPI 높음 +

### Community 47 - "Community 47"
Cohesion: 0.7
Nodes (4): main(), print_summary_table(), _result_to_dict(), write_report_json()

### Community 48 - "Community 48"
Cohesion: 0.83
Nodes (3): _load_json(), main(), _section()

### Community 49 - "Community 49"
Cohesion: 0.67
Nodes (1): Reset inception.strategies to match current allocated amounts.  performance.json

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (0): 

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (1): Fetch articles from this source.          Returns:             [{"title", "bo

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (1): Build (ret, log_vix, vol21) feature DataFrame from price series.          Raises

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (1): Load model from disk. Returns None on any failure.

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (0): 

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (1): Generate order ID prefix for strategy attribution.

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (1): Generate trade signals from market data.          Args:             market_da

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (0): 

### Community 58 - "Community 58"
Cohesion: 1.0
Nodes (1): MOM 25%+QNT 20% Technology → 총 45% > 30% → BLOCK.

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (1): MOM 10%+QNT 10% Technology → 총 20% < 30% → PASS.

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (1): Unknown 섹터는 per-strategy 게이트에서 처리 → cross-strategy PASS.

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (1): Check correlation between new symbol and existing holdings.

### Community 62 - "Community 62"
Cohesion: 1.0
Nodes (1): Ensure strategy maintains minimum cash buffer after trade.

### Community 63 - "Community 63"
Cohesion: 1.0
Nodes (1): Run all 5 risk checks on a proposed trade.      Args:         symbol: Ticker

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (1): Convert regime probability dict to continuous 0~1 composite score.      state_pr

### Community 65 - "Community 65"
Cohesion: 1.0
Nodes (1): Check if total portfolio NAV has hit MDD threshold.

### Community 66 - "Community 66"
Cohesion: 1.0
Nodes (1): Run all position-level checks in priority order.      Returns (should_exit, reas

### Community 67 - "Community 67"
Cohesion: 1.0
Nodes (1): Get sector for a symbol. Uses hardcoded map → cache → yfinance fallback.

### Community 68 - "Community 68"
Cohesion: 1.0
Nodes (1): Check that a single position doesn't exceed max_pct of strategy capital.

### Community 69 - "Community 69"
Cohesion: 1.0
Nodes (1): Check that sector exposure doesn't exceed max_pct.

### Community 70 - "Community 70"
Cohesion: 1.0
Nodes (1): Parametric VaR check (95% 1-day) for portfolio.

### Community 71 - "Community 71"
Cohesion: 1.0
Nodes (1): Check correlation between new symbol and existing holdings.

### Community 72 - "Community 72"
Cohesion: 1.0
Nodes (1): Ensure strategy maintains minimum cash buffer after trade.

### Community 73 - "Community 73"
Cohesion: 1.0
Nodes (1): Run all 5 risk checks on a proposed trade.      Args:         symbol: Ticker

### Community 74 - "Community 74"
Cohesion: 1.0
Nodes (1): Extract notional value from trade entry.

### Community 75 - "Community 75"
Cohesion: 1.0
Nodes (1): Copy report to Obsidian vault.

### Community 76 - "Community 76"
Cohesion: 1.0
Nodes (1): Compute Maximum Drawdown (%). Returns negative number.

### Community 77 - "Community 77"
Cohesion: 1.0
Nodes (1): Compute annualized Sharpe ratio. Returns None if < 20 observations.

### Community 78 - "Community 78"
Cohesion: 1.0
Nodes (1): Win rate from filled trades only (sell with positive pnl).

### Community 79 - "Community 79"
Cohesion: 1.0
Nodes (1): Build one entry for the daily[] array in performance.json.

### Community 80 - "Community 80"
Cohesion: 1.0
Nodes (1): Append daily entry, recompute aggregates, save performance.json.      Duplicat

### Community 81 - "Community 81"
Cohesion: 1.0
Nodes (1): Convert nav_history to SVG path string for inline sparkline.

### Community 82 - "Community 82"
Cohesion: 1.0
Nodes (1): Generate reports/strategy/{CODE}-monthly.md for current month.

## Knowledge Gaps
- **255 isolated node(s):** `strategy_params.json 로더 — 모듈 레벨 캐시로 중복 IO 방지.`, `strategy_params.json을 읽어 dict로 반환. 모듈 캐시 사용.`, `캐시를 버리고 다시 읽는다 (테스트/변경 감지용).`, `Alpaca Trading Client — paper/live toggle via environment variable.  Switch be`, `Get singleton Alpaca TradingClient.      Environment variables required:` (+250 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 50`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `Fetch articles from this source.          Returns:             [{"title", "bo`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `Build (ret, log_vix, vol21) feature DataFrame from price series.          Raises`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `Load model from disk. Returns None on any failure.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `Generate order ID prefix for strategy attribution.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (1 nodes): `Generate trade signals from market data.          Args:             market_da`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (1 nodes): `MOM 25%+QNT 20% Technology → 총 45% > 30% → BLOCK.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (1 nodes): `MOM 10%+QNT 10% Technology → 총 20% < 30% → PASS.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (1 nodes): `Unknown 섹터는 per-strategy 게이트에서 처리 → cross-strategy PASS.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (1 nodes): `Check correlation between new symbol and existing holdings.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (1 nodes): `Ensure strategy maintains minimum cash buffer after trade.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (1 nodes): `Run all 5 risk checks on a proposed trade.      Args:         symbol: Ticker`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (1 nodes): `Convert regime probability dict to continuous 0~1 composite score.      state_pr`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (1 nodes): `Check if total portfolio NAV has hit MDD threshold.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 66`** (1 nodes): `Run all position-level checks in priority order.      Returns (should_exit, reas`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 67`** (1 nodes): `Get sector for a symbol. Uses hardcoded map → cache → yfinance fallback.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 68`** (1 nodes): `Check that a single position doesn't exceed max_pct of strategy capital.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 69`** (1 nodes): `Check that sector exposure doesn't exceed max_pct.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 70`** (1 nodes): `Parametric VaR check (95% 1-day) for portfolio.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 71`** (1 nodes): `Check correlation between new symbol and existing holdings.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 72`** (1 nodes): `Ensure strategy maintains minimum cash buffer after trade.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 73`** (1 nodes): `Run all 5 risk checks on a proposed trade.      Args:         symbol: Ticker`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 74`** (1 nodes): `Extract notional value from trade entry.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 75`** (1 nodes): `Copy report to Obsidian vault.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 76`** (1 nodes): `Compute Maximum Drawdown (%). Returns negative number.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 77`** (1 nodes): `Compute annualized Sharpe ratio. Returns None if < 20 observations.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 78`** (1 nodes): `Win rate from filled trades only (sell with positive pnl).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 79`** (1 nodes): `Build one entry for the daily[] array in performance.json.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 80`** (1 nodes): `Append daily entry, recompute aggregates, save performance.json.      Duplicat`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 81`** (1 nodes): `Convert nav_history to SVG path string for inline sparkline.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 82`** (1 nodes): `Generate reports/strategy/{CODE}-monthly.md for current month.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Direction` connect `Community 1` to `Community 0`, `Community 3`, `Community 37`, `Community 17`, `Community 19`?**
  _High betweenness centrality (0.087) - this node is a cross-community bridge._
- **Why does `Signal` connect `Community 0` to `Community 1`, `Community 17`?**
  _High betweenness centrality (0.082) - this node is a cross-community bridge._
- **Are the 217 inferred relationships involving `Direction` (e.g. with `numpy 스칼라 타입을 native Python으로 변환 (Python 3.14 호환).` and `C5 fix: portfolios.json에 inception 필드가 없으면 현재 allocated로 초기화.      inception.t`) actually correct?**
  _`Direction` has 217 INFERRED edges - model-reasoned connections that need verification._
- **Are the 197 inferred relationships involving `Signal` (e.g. with `numpy 스칼라 타입을 native Python으로 변환 (Python 3.14 호환).` and `C5 fix: portfolios.json에 inception 필드가 없으면 현재 allocated로 초기화.      inception.t`) actually correct?**
  _`Signal` has 197 INFERRED edges - model-reasoned connections that need verification._
- **Are the 129 inferred relationships involving `LeveragedETFStrategy` (e.g. with `numpy 스칼라 타입을 native Python으로 변환 (Python 3.14 호환).` and `C5 fix: portfolios.json에 inception 필드가 없으면 현재 allocated로 초기화.      inception.t`) actually correct?**
  _`LeveragedETFStrategy` has 129 INFERRED edges - model-reasoned connections that need verification._
- **Are the 123 inferred relationships involving `RegimeDetection` (e.g. with `numpy 스칼라 타입을 native Python으로 변환 (Python 3.14 호환).` and `C5 fix: portfolios.json에 inception 필드가 없으면 현재 allocated로 초기화.      inception.t`) actually correct?**
  _`RegimeDetection` has 123 INFERRED edges - model-reasoned connections that need verification._
- **Are the 110 inferred relationships involving `ValueQualityStrategy` (e.g. with `numpy 스칼라 타입을 native Python으로 변환 (Python 3.14 호환).` and `C5 fix: portfolios.json에 inception 필드가 없으면 현재 allocated로 초기화.      inception.t`) actually correct?**
  _`ValueQualityStrategy` has 110 INFERRED edges - model-reasoned connections that need verification._