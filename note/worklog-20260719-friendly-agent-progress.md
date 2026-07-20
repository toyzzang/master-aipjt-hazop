# 사용자 친화적 Agent 진행 안내

## 요청

- #3/#4 로딩 영역에서 현재 작업을 사용자가 이해하기 쉬운 문장으로 설명한다.
- `read_file` 같은 내부 기술 로그는 숨긴 상태를 유지한다.
- 각 Sub Agent 블록 안에는 실제 적용하는 Skill의 목적을 풀어서 표시한다.
- `risk-review-agent` 역할 명칭을 `위험도 계산·근거 검토`로 통일한다.
- `action-plan-agent`는 위험도 9 이상 항목만 받아 조치계획을 작성한다고 표시한다.

## 표시 원칙

- 내부 동작: `read_file / SKILL.md / trace`는 표시하지 않는다.
- 사용자 의미: `빈도 판단 기준을 적용합니다`, `강도 판단 기준을 적용합니다`처럼 표시한다.
- Agent 부모 블록은 실행 중 스피너를 유지하고, Skill 안내는 해당 부모 안에 자식 로그로 표시한다.

## Agent별 안내

### risk-draft-agent

- hazop_risk_draft: Deviation, Cause, Consequence, Safeguard, 판단 근거 작성 기준
- frequency_estimation: 사고이력, 유사 HAZOP, 일반 HAZOP 규칙 순서로 빈도 근거 확인
- severity_estimation: MSDS와 사고 영향 범위를 기준으로 강도 판단

### risk-review-agent

- 역할명: 위험도 계산·근거 검토
- hazop_risk_review: 원인-결과 연결, 근거 누락, 안전조치 적절성 검토
- severity_estimation: MSDS 대비 강도 과소평가 여부 검토
- standard_hazop_comparison: 표준 HAZOP보다 낮은 평가의 근거 검토

### action-plan-agent

- 역할명: 고위험 항목 조치계획 작성
- hazop_action_plan: 위험도 9 이상 항목의 권고 조치와 완료 기준 작성
- severity_estimation: 조치 후에도 남는 사고 영향 강도 확인

## 성공 기준

- #3/#4 로딩 문구가 현재 처리 내용을 친근하게 설명한다.
- 세 Agent 블록 안에 Skill별 설명이 표시된다.
- `read_file` 문자열은 사용자 로그에 표시되지 않는다.
- 전체 테스트와 Frontend 빌드가 통과한다.
