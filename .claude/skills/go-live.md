---
name: go-live
description: >
  Paper Trading에서 Live Trading으로 전환하는 체크리스트.
  트리거: /go-live, 실전 전환, 라이브, live 전환
---

# /go-live - Paper to Live Migration Checklist

## 전환 전 필수 확인 (10항목)

### Performance Verification
- [ ] 1. Paper Trading 최소 1개월 이상 운영
- [ ] 2. 전략별 수익률이 벤치마크(SPY) 대비 양수
- [ ] 3. 전체 포트폴리오 MDD < 15%
- [ ] 4. Win Rate > 45% (전략 평균)

### System Verification
- [ ] 5. GitHub Actions trading-cycle.yml이 최근 2주간 실패 없이 동작
- [ ] 6. Risk Guardian이 최근 2주간 정상 작동 (FAIL 시그널 0건 실행)
- [ ] 7. trade_log.jsonl에 데이터 무결성 확인 (빈 레코드 없음)

### Account Verification
- [ ] 8. Alpaca Live 계좌 개설 + 자금 입금 완료
- [ ] 9. Live API Key 발급 완료

### Final Switch
- [ ] 10. GitHub Actions secret 변경: ALPACA_MODE=paper -> ALPACA_MODE=live

## 전환 절차

```bash
# 1. 현재 Paper 성과 최종 확인
python run_cycle.py --phase report

# 2. GitHub Actions secret 변경 (GitHub UI에서)
# Settings > Secrets > ALPACA_MODE = live

# 3. 첫 Live 사이클은 dry-run으로 확인
python run_cycle.py --phase all --dry-run

# 4. 이상 없으면 Live 실행
python run_cycle.py --phase all
```

## 롤백 방법
Live에서 문제 발생 시:
```
ALPACA_MODE=paper  # GitHub secret 변경
```
코드 변경 0. 즉시 Paper 모드로 복귀.

## 주의사항
- Live 전환 후에도 동일한 리스크 게이트 적용
- 첫 1주는 포지션 크기를 Paper의 50%로 축소 권장
- 세금 영향 발생: 매도 시 양도소득세 (해외주식 연 250만원 기본공제 후 22%)
