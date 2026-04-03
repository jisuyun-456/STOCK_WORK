# /skill-creator — 새 스킬 생성

새 스킬을 만들 때 아래 절차를 따르세요.
글로벌 `superpowers:writing-skills`를 기반으로 STOCK_WORK 프로젝트 컨벤션을 적용합니다.

## 1. 스킬 유형 결정

| 유형 | 저장 위치 | 예시 |
|------|----------|------|
| 리포트/분석 | `.claude/skills/report/` | 일일 리포트, 종목 분석 |
| 리서치 절차 | `.claude/skills/research/` | 밸류에이션, 스크리닝 |
| 리스크/세금 | `.claude/skills/risk/` | VaR 계산, 세금 시뮬레이션 |
| 포트폴리오 | `.claude/skills/portfolio/` | 리밸런싱, 편출입 |
| 기술/DB | `.claude/skills/tech/` | 데이터 파이프라인, API 연동 |
| 프로젝트 명령 | `.claude/commands/` | 세션 루틴 |

## 2. 스킬 파일 골격

```markdown
---
name: {skill-id}
description: 한 줄 설명 (트리거 키워드 포함)
---

# {스킬명}

## 언제 사용
- 트리거 조건 명시

## Step 1: {첫 번째 단계}
...

## Step N: {마지막 단계}
...

## 출력 형식
...
```

## 3. 명명 규칙

- 파일명: `kebab-case.md` (예: `daily-report.md`)
- name 필드: 파일명과 동일
- description: 동사로 시작 (예: "일일 시장 분석 리포트 생성 및 Gmail 전송")

## 4. 검증

스킬 생성 후 `Skill` 도구로 호출 테스트:
```
Skill tool → skill: "{skill-id}"
```

## 5. superpowers 활용

복잡한 스킬이면 먼저 글로벌 스킬 참고:
```
Skill tool → skill: "superpowers:writing-skills"
```
