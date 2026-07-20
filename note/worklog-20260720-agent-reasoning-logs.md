# Agent Planning · 전략 비교 · Self-Correction 로그 개선

## 배경

현재 HAZOP Workflow는 `risk-draft-agent → 시스템 검증 → risk-review-agent → 시스템 재검증 → action-plan-agent` 순서로 안전하게 고정되어 있다. 그러나 화면에는 Skill/Tool 준비 로그와 검토 건수 요약이 중심이라, 평가자가 입력 기반 계획과 실제 수정 내용을 한눈에 확인하기 어렵다.

## 목표

- 안전한 고정 Workflow 순서는 변경하지 않는다.
- 실행 전에 실제 구조화된 5단계 Plan을 만든다.
- 근거 활용 전략 3개를 제한된 범위에서 비교하고 하나를 선택한다.
- 선택된 전략을 위험성평가 작성·검토·조치 Agent의 Context에 실제로 전달한다.
- 검토 전후 Row를 시스템 코드로 비교하여 수정 전·후·근거·위험도 재계산 결과를 실시간 로그로 표시한다.
- 내부 비공개 사고 원문이 아니라 검증 가능한 결정과 근거만 표시한다.

## 설계

### 1. Plan 모델

- `HazopExecutionPlan`: 고정 5단계, 성공 조건, 후보 전략, 선택 전략을 저장한다.
- `HazopPlanCandidate`: MSDS 우선, 사고이력 우선, 표준 HAZOP 우선 전략의 확인 결과·부족한 근거·선택 근거를 저장한다.
- 백분율이나 정확도로 오해될 수 있는 임의 숫자 점수는 화면과 Plan 객체에서 제거한다.
- 선택 규칙은 `고위험 물질+MSDS → 현장 이력 존재 → 표준 참조 존재 → MSDS 기본` 순서의 명시적 조건 분기로 고정한다.

### 2. 실제 적용

- 생성한 Plan을 `HazopDraftContext.execution_plan`에 보관한다.
- 작성·검토·조치 Agent 프롬프트에 선택 전략, 근거 우선순위, 검토 중점, Tool 호출 조건을 전달한다.
- Plan 생성 실패가 전체 PoC를 중단시키지 않도록 Plan은 결정론적 시스템 코드로 생성한다.

### 3. Self-Correction 이벤트

- 시스템 검증된 작성본과 검토 Agent 반환본을 Row 번호 기준으로 비교한다.
- 빈도, 강도, 원인, 결과, 안전조치, 근거가 바뀐 경우 수정 항목을 기록한다.
- 각 변경 Row마다 다음 이벤트를 순서대로 표시한다.
  1. 문제 발견
  2. 검토 근거
  3. 수정 적용
  4. 시스템 재검증 및 위험도 전후 비교
- 변경되지 않은 Row는 개별 로그를 쌓지 않고 최종 요약에 유지 건수로 표시한다.

### 4. 화면

- `planning`, `plan-candidate`, `plan-evaluation`, `plan-selected`, `self-correction`, `replanning` 로그 종류를 지원한다.
- 기존 Agent 부모/자식 그룹 구조는 유지한다.
- 좌측 색상 선은 사용하지 않는다.
- Planning과 Self-Correction은 로그 종류 라벨을 둥근 배경 배지로 표시하고 종류별 색상으로 구분한다.
- 모든 로그 종류(System, Workflow, Agent, Skill, Tool, 검증, 결과, 주의, 오류)에 서로 구분되는 배지 색상을 적용한다.
- 후보 A/B/C는 Plan 객체 안에서는 비교에 사용하되, 화면에 후보별 개별 카드를 반복 표시하지 않는다.
- Self-Correction 화면 로그는 검토 시작과 변경/유지/조치대상 변경 건수 요약만 표시한다. 상세 내용은 결과 표에서 확인한다.
- ReviewFinding의 위험성평가 번호가 없으면 `전체` 또는 실제 변경 Row 번호로 보정해 결과 표에 공란이 생기지 않게 한다.
- DeepAgents 기본 `TodoListMiddleware/write_todos`를 risk-draft-agent의 실제 Planning 도구로 사용한다.
- risk-draft-agent는 초안 작성 전에 `write_todos`로 실행 항목을 구성하며, 실제 Tool trace가 없으면 DeepAgent Planning 성공으로 표시하지 않는다.
- 화면에는 todo의 단계·상태만 고수준 Planning 로그로 표시하고 모델의 내부 사고 원문은 표시하지 않는다.
- 전체 Workflow 시작부의 Plan Validation, Plan Evaluation, Plan Selected 화면 로그는 제거한다.
- risk-draft-agent, risk-review-agent, action-plan-agent가 각각 자기 역할 범위에서 DeepAgent `write_todos` Planning을 수행한다.
- Agent 자식 로그는 화면에서 Planning → Skill → Agent/Tool → Self-Correction/검증 → 대기 → 결과 순서로 정렬한다.
- `모델 응답 대기 중입니다.`는 실행 중에는 해당 Agent 블록의 마지막 자식 로그로 유지한다.

### 5. Agent 내부 로그의 실시간 순서 보정

- Agent 시작 직후에는 `Planning: DeepAgent가 실행계획을 수립하는 중입니다.` 한 개만 spinner로 표시한다.
- DeepAgent stream에서 첫 `write_todos` 결과가 확인되면 같은 Planning 블록을 완료 상태로 갱신하고 1~5단계를 표시한다.
- Planning 다음에 Skill 목록은 한 블록, Tool 목록은 한 블록으로 묶어 표시한다.
- Context는 독립된 Agent 로그로 중간 삽입하지 않고 모델 실행 상태의 설명에 포함한다.
- review Agent에서는 `Self-Correction 진행 중`과 `모델 응답 대기 중`을 동시에 표시하지 않는다. 전자는 review Agent의 모델 실행 상태 자체로 사용한다.
- 종류별 강제 정렬을 제거하고 서버에서 발생한 실행 순서를 유지하되, Planning/Skill/Tool 블록은 같은 종류의 상태 갱신으로 처리한다.
- `모델 응답 대기`는 Agent, Result는 진회색, 검증은 남색, Skill과 Tool은 같은 파란색 계열, Self-Correction은 주의와 다른 보라색 계열을 사용한다.
- Planning만 진행 중 블록을 완료 블록으로 갱신한다. Skill과 Tool은 준비 상태와 실제 적용 결과가 서로 다른 사실이므로 기존 블록을 덮어쓰지 않고 새 블록으로 추가한다.
- Context 구성은 Excel, MSDS, 사고이력, 위험도 기준표를 LLM용 Prompt로 합치는 독립 단계로 표시하되 Tool 연결 다음, 모델 작업 시작 전에 배치한다.
- Skill 적용 성공 trace가 확인된 뒤에만 모델 작업/Self-Correction spinner를 시작해 실행 중 상태 아래에 뒤늦은 Skill 로그가 붙지 않게 한다.
- 검토 요약 제목에 담당자 확인 필요 건수를 표시하고, 결과 표의 `담당자 확인 필요=True`는 빨간색 굵은 글씨로 강조한다.
- Planning과 Self-Correction 배지는 초록색으로 통일하고, 검증 배지는 Workflow와 같은 청록색을 사용한다.
- 모델과 Tool을 번갈아 사용하는 Agent loop를 단순한 `모델 응답 대기`로 오해하지 않도록 실행 중 문구를 `Agent가 모델과 Tool을 사용해 작업 중입니다.`로 표시한다.
- Skill과 Tool은 같은 노란색, 주의는 주황색, 오류는 빨간색 배지로 명확히 구분한다.
- 검증 배지는 진회색으로 표시한다.

## 성공 기준

- DeepAgent 모드와 Demo 모드 모두 실행 초기에 5단계 Plan 로그가 나타난다.
- 후보 3개, 평가 결과, 선택 전략이 구조화된 로그로 나타난다.
- 선택 전략이 각 LLM 프롬프트에 포함된다.
- 검토로 빈도·강도가 바뀌면 수정 전후 점수와 시스템 재계산 위험도가 로그에 나타난다.
- 위험도는 기존과 동일하게 시스템 코드만 계산한다.
- 기존 HAZOP 입력 Allowlist, 점수 범위, 고위험 9점 분기 규칙을 유지한다.
- Python 테스트, TypeScript typecheck, 프론트엔드 build가 통과한다.

## 범위 제외

- AI가 전체 Workflow 순서를 바꾸는 자유 계획 기능
- 내부 Chain-of-Thought 원문 공개
- 동일 Row에 대한 다중 LLM 답안 생성
- 외부 사고이력 또는 표준 HAZOP 데이터베이스 신규 연결
