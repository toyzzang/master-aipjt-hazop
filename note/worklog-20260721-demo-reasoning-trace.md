# 시연용 Agent 고수준 추론 로그 개선 설계

## 배경

시연 영상 제출 가이드는 5분 안에 `Planning`, 계획 비교, `Tool Call`, `Self-Correction`을 확대해 설명하도록 요구한다. 현재 화면은 Agent별 Planning과 최종 Tool trace를 표시하지만, 모델 응답 중에는 `Agent가 모델과 Tool을 사용해 작업 중입니다.`라는 대기 문구가 오래 유지된다. 또한 구조화 Plan 안의 A/B/C 근거 전략과 Self-Correction 전후 차이가 로그 화면에 직접 드러나지 않는다.

## 목표

- 고정 HAZOP Workflow는 변경하지 않는다.
- MSDS 우선, 사고이력 우선, 표준 HAZOP 우선의 세 전략을 한 Planner 카드 안에서 비교한다.
- 선택 조건과 선택된 전략이 실제 입력 근거와 함께 표시되게 한다.
- Agent별 로그는 부모 Agent와 자식 단계의 2단계 깊이로 유지한다.
- 실제 DeepAgent stream에서 발견한 Tool 호출과 결과만 실시간 로그로 표시한다.
- Tool 로그에 호출 목적, 입력, 결과 전달 위치를 표시한다.
- 독립 검토 전후의 대표 Row를 최대 3건 표시하고 위험도를 시스템이 재계산했음을 보여준다.
- Planning, Plan 선택, Self-Correction을 시연 중 쉽게 찾을 수 있도록 강조한다.
- DeepAgent와 규칙 기반 Demo 실행을 명확히 구분한다.
- 동일한 구조화 이벤트를 Backend 콘솔에도 기록한다.

## 비목표 및 안전 경계

- 모델의 비공개 Chain-of-Thought 원문은 저장하거나 화면에 표시하지 않는다.
- 실제로 생성하지 않은 Row별 진행률을 꾸며내지 않는다.
- A/B/C 비교를 자유 생성형 ToT라고 과장하지 않는다. 고정 Workflow 안의 제한된 근거 전략 비교로 설명한다.
- 위험도는 기존과 동일하게 시스템 코드가 `빈도 * 강도`로 계산한다.
- Node, 변수, Guideword 및 평가 Row 수는 변경하지 않는다.

## 구현 설계

### 1. 구조화 실행 이벤트

- `EngineEvent`와 브라우저 `AgentEvent`에 `emphasis`를 추가한다.
- `workflow-planner` 부모 그룹을 만들고 아래 자식 로그를 발생시킨다.
  - 후보 A/B/C
  - 입력 조건에 따른 평가 결과
  - 최종 선택 전략과 근거 우선순위
- 선택 전략 이벤트는 강조 표시한다.

### 2. Tool 실시간 trace

- DeepAgent stream snapshot에서 Tool call id별 상태를 추적한다.
- 처음 발견되면 `호출 시작`, Tool 결과가 생기면 `호출 완료/실패` 이벤트를 발생시킨다.
- 로그에는 Agent/Tool별 고정 정책에서 가져온 호출 목적, 전달 인수, 결과 요약, 결과가 전달되는 판단 영역을 표시한다.
- 실제 결과와 연결할 수 없는 경우 `판단에 반영됨`이라고 단정하지 않고 `다음 판단 입력으로 전달`이라고 표시한다.

### 3. Self-Correction 대표 변경

- 검토 전후 Row를 `no`로 비교한다.
- 조치 대상 변경, 위험도 변경, 기타 필드 변경 순서로 대표 Row를 최대 3건 선택한다.
- 각 대표 로그에는 문제 발견, 검토 근거, 변경 전, 변경 후, 시스템 재계산을 표시한다.
- 전체 수정/유지/조치 대상 변경 건수 요약은 유지한다.

### 4. 화면

- Agent 부모 카드 아래에 Planning/Context/Tool/Self-Correction/Validation을 자식으로 유지한다.
- `risk-review-agent`의 Self-Correction은 별도 상위 단계로 표시하고, 같은 모델 응답에서 시작된 근거 조회 Tool은 그 아래 2단계 자식으로 묶는다.
- Self-Correction 근거 조회 상태는 `0/2 → 1/2 → 2/2`처럼 같은 블록에서 갱신하고, 전체 완료 전에는 "조회 결과 취합 후 Row 재검토" 대기 상태를 표시한다.
- 병렬 Tool 자식은 사고·정비 이력, 표준 HAZOP처럼 사람이 이해하기 쉬운 이름과 실행/완료 상태로 표시한다.
- 부모 카드를 펼치고 접을 수 있게 한다.
- 전체, Planning, Tool, Self-Correction 필터를 제공한다.
- 로그 확대 버튼으로 16:9 영상에서 로그가 화면 대부분을 차지하게 한다.
- `emphasis` 이벤트는 테두리와 배경으로 강조한다.
- 실행 중과 완료 결과에 `DeepAgent` 또는 `규칙 기반 Demo` 배지를 표시한다.

### 5. Backend 콘솔 로그

- HAZOP Engine 진행 콜백에서 `AGENT_TRACE` 접두어와 JSON payload를 INFO 로그로 남긴다.
- 필드: request_id, agent_id, kind, phase, title, detail, loading, emphasis.
- 브라우저에 전달되는 실제 이벤트만 기록하고 모델 프롬프트 원문이나 비공개 사고 원문은 기록하지 않는다.

## KOSHA/MSDS 데이터 경계

- 현재 KOSHA 연동은 공식 JSON API가 아니라 HTML form POST 기반 사이트 내부 검색이다.
- 검색 결과 HTML에서 `chem_id`, 물질명을 추출하고 상세 HTML에서 H문구와 P문구를 추출한다.
- 내부 표준 구조는 `MsdsSummary(material, hazards[], handling[], source)`이다.
- KOSHA가 단일 `고위험 여부` Boolean을 주는 구조가 아니므로, 유해성 문구와 물질명을 바탕으로 시스템이 보수적으로 고위험 신호를 판별한다.
- 향후에는 고위험 판정 결과에 발견 키워드와 MSDS 출처를 함께 보관해 설명 가능성을 높인다.

## 성공 기준

- DeepAgent/Demo 모두 실행 초기에 A/B/C 비교와 선택 전략이 표시된다.
- DeepAgent stream의 Tool 호출 시작/결과가 Agent 자식 로그로 나타난다.
- Self-Correction 중 함께 실행된 Tool 2건이 Self-Correction 아래에 묶이고 `0/2`, `1/2`, `2/2` 진행률이 실제 trace 상태에 맞춰 갱신된다.
- Self-Correction 변경이 있으면 대표 Row 전후와 재계산값이 표시된다.
- 로그 확대, 접기/펼치기, 핵심 종류 필터가 동작한다.
- Backend 터미널에서 `AGENT_TRACE` JSON을 확인할 수 있다.
- Demo 실행은 `규칙 기반 Demo`로 명확히 표시된다.
- Python 테스트, TypeScript typecheck, frontend build가 통과한다.

## 검증 시나리오

- `HAZOP_ColdChain_NH3-Refrigeration.xlsx`: 고위험 물질 + MSDS로 전략 A 선택, 고위험 조치계획과 Self-Correction 시연
- `HAZOP_CleanTech_CT-DIW-100.xlsx`: 저위험 물질 + 사고이력 또는 표준 문서 조건에 따른 전략 B/C 선택 테스트
- 단위 테스트: 전략 이벤트, Tool 상태 이벤트, Self-Correction 대표 Row, Backend JSON 로그

## 구현 및 검증 결과

- Self-Correction 이벤트에 안정적인 `event_key`를 부여해 진행률 문구가 같은 블록에서 갱신되도록 구현했다.
- Tool 이벤트에 `parent_kind=self-correction`과 Tool call ID 기반 `event_key`를 전달해 시작/완료가 같은 하위 항목으로 표시되도록 구현했다.
- 실제 stream snapshot의 Tool 상태를 집계해 `0/2 → 1/2 → 2/2`가 생성되는 단위 테스트를 추가했다.
- 전체 Python 테스트 32건 통과, TypeScript typecheck 통과, Vite production build 통과, `git diff --check` 통과.

## 2차 화면·근거 저장소 보완 설계

### Agent 작업과 Tool의 부모·자식 관계

- `Agent가 모델과 Tool을 사용해 작업 중입니다.`와 Self-Correction을 실제 작업 부모로 사용한다.
- 같은 Agent 단계에서 발생한 Tool call/result는 해당 작업 부모의 하위 항목으로 묶고 Tool call ID로 시작/완료 상태를 같은 줄에서 갱신한다.
- Tool이 모두 끝나면 부모 스피너를 잘못 종료하지 않는다. Agent 전체 모델 작업이 끝날 때까지 부모는 `Tool 결과 취합·초안 생성 중` 또는 `근거 통합·전체 Row 검토 중`으로 갱신한다.
- Self-Correction 부모에는 입력 연결 보존, 원인-결과 연결, MSDS 모순, 빈도·강도 근거, 수정본 구조화라는 공개 가능한 검토 기준을 표시한다. 비공개 Chain-of-Thought는 표시하지 않는다.

### 로그 시인성

- 초록색 배경·테두리 강조는 모두 제거하고 중립적인 회색/청색 계열을 사용한다.
- Agent 카드가 길어질 때 Agent 이름과 실행 상태가 카드 상단에 sticky로 남도록 한다.
- 대표 변경 제목은 단순 `평가 003` 대신 `평가 003 · Node · 변수/Guideword`로 표시해 Excel의 몇 번째 평가 Row인지 바로 이해할 수 있게 한다.

### 다중 MSDS 조회

- `Workflow 필수 MSDS 조회`를 부모 카드로 만들고 입력 물질별 조회를 자식 카드로 표시한다.
- 모든 물질 조회 Task를 먼저 시작해 여러 물질이 동시에 조회 중임을 보여주고, 물질별 KOSHA 검색/fallback/요약 결과를 같은 자식 카드에서 완료 상태로 갱신한다.
- Node에 같은 물질이 반복되어도 물질명 기준으로 한 번만 조회하고, 서로 다른 물질은 모두 조회한다.

### 로컬 표준 HAZOP 문서 저장소

- PoC 단계에서는 별도 DB 설치가 필요한 SQLite 대신 버전 관리 가능한 JSON 문서를 사용한다.
- NH3 냉동, Silane 가스 공급, HF Etch 세 표준 문서 샘플을 `app/data/standard_hazop`에 둔다.
- `reference_id`로 문서를 찾고 query와 유사한 Row를 검색해 원인·결과·안전조치·빈도/강도 참조값을 반환한다.
- Workflow 시작 시 표준 문서를 실제로 선조회해 `standard_hazop_context`에 넣고, Plan 선택과 세 Agent Prompt가 해당 Context를 사용한다.
- 검색 결과가 없을 때만 `확인 필요`를 표시한다.

### 2차 성공 기준

- risk-draft/action-plan Tool이 일반 Agent 작업 블록 아래에 표시된다.
- Self-Correction은 Tool 2/2 완료 후에도 실제 Agent 완료 전까지 스피너와 다음 검토 상태가 유지된다.
- 로그 영역 어디를 보더라도 현재 긴 Agent 카드의 Agent 이름을 확인할 수 있다.
- 여러 물질 입력 시 MSDS 부모 아래 모든 고유 물질의 조회 카드가 나타난다.
- `STD-HAZOP-NH3-REFRIGERATION-2026-001` 조회가 실제 샘플 Row를 반환하고 Prompt Context에 포함된다.
- 초록색 로그 강조 박스가 남아 있지 않는다.

## 2차 구현 및 검증 결과

- 일반 Agent 작업과 Self-Correction 모두 Tool call/result를 현재 작업 블록 아래에 연결했다.
- Tool 완료 뒤 상위 작업은 실제 Agent 완료 전까지 스피너를 유지하되, `Tool 결과 취합·구조화 결과 생성 중` 또는 `근거 통합·전체 Row 검토 중`으로 상태 문구를 갱신한다.
- Self-Correction에 공개 가능한 5개 검토 기준을 표시하고 대표 변경 제목에 Node·변수·Guideword를 추가했다.
- Agent 카드 헤더를 sticky 처리하고 로그의 초록색 강조 색을 회색·청색·보라 계열로 교체했다.
- 여러 고유 물질의 MSDS 조회를 하나의 Workflow 카드 아래에서 병렬 시작하고 물질별 완료 상태로 갱신하도록 구현했다.
- NH3/Silane/HF 표준 HAZOP JSON 3개와 실제 reference/query 검색을 구현하고 DeepAgent Prompt와 Demo 근거에 연결했다.
- 전체 Python 테스트 33건, TypeScript typecheck, Vite production build, `git diff --check`가 모두 통과했다.

## 3차 로그 계층·물질 정규화 보완 설계

- 긴 Agent 카드에서는 Agent 헤더뿐 아니라 현재 실행 중인 작업 요약도 두 번째 sticky 영역으로 유지한다. Tool 하위 목록 자체는 sticky에 포함하지 않아 화면을 가리지 않게 한다.
- 우측 상단 모델/실행 모드 배지는 제거한다. Backend의 실제 `run_mode` 값과 Demo 구분 이벤트는 유지한다.
- 모든 최상위·1단계 로그 카드 배경은 흰색으로 통일한다. 2단계로 중첩된 Tool/대표 변경 카드만 연한 청색 배경과 얇은 청색 테두리로 계층을 구분한다.
- `Ammonia Water`, `Aqueous Ammonia`, `Ammonium Hydroxide`는 기체 Ammonia로 합치지 않고 `Ammonia Water`라는 별도 검색어와 내장 MSDS 요약으로 유지한다.
- Self-Correction 완료 요약에 `event_key`를 부여하고 대표 변경 최대 3건과 나머지 안내를 해당 요약의 하위 이벤트로 연결한다.
- 대표 선정 기준을 완료 요약에 공개한다: 1순위 조치계획 대상 변경, 2순위 위험도 점수 변경, 3순위 그 밖의 필드 변경, 동률이면 평가 Row 번호순.
- Agent Planning은 최초 계획만 표시하지 않고 stream에서 바뀐 Todo 상태를 같은 Planning 블록에 갱신해 계획과 실행 흐름의 연결을 확인할 수 있게 한다. 계획 생성 사실과 실제 완료 사실을 구분한다.

## 3차 구현 및 검증 결과

- Agent 헤더 아래 현재 작업 요약만 2차 sticky 처리하고, Tool 목록은 정상 스크롤되도록 분리했다.
- 화면의 DeepAgent 모델 배지를 제거하고 최상위·1단계 카드 배경을 흰색으로 통일했다. 중첩 카드만 연한 청색으로 표시한다.
- Ammonia Water 계열을 별도 물질로 정규화하고 내장 MSDS fallback을 추가했다.
- 대표 변경과 나머지 안내를 Self-Correction 완료 요약의 하위 이벤트로 연결하고 선정 기준을 요약에 표시했다.
- write_todos 공개 체크리스트가 stream에서 바뀔 때 `Planning 실행 현황 · n/m 완료`로 같은 Planning 블록을 갱신하도록 구현했다.
- 전체 Python 테스트 35건, TypeScript typecheck, Vite production build, `git diff --check`가 모두 통과했다.

## 4차 Self-Correction 정확성·MSDS 원문 검색 보완 설계

- 현재 모든 Row가 수정된 것처럼 보일 수 있는 핵심 원인은 다음 두 가지로 확인했다.
  - review Agent가 전체 Row를 다시 표현하면 문자열·근거 배열의 작은 차이도 수정으로 계산한다.
  - `risk_assessment_no="전체"`인 담당자 확인 의견을 모든 Row 비고에 복사해 전체 Row가 변경된 것으로 계산한다.
- 수정 적용은 `ReviewFinding.risk_assessment_no`가 명시된 Row로 제한한다. 지적되지 않은 Row는 review Agent가 다시 작성했더라도 시스템 검증본으로 되돌린다.
- `전체` 확인 의견은 검토 내역 표에만 보관하고 모든 Row 비고에 복사하지 않는다.
- review Agent Prompt에 문장 다듬기·동의어 치환 금지, 실제 결함이 있는 Row만 수정, 수정 Row마다 정확한 평가 번호의 finding 필수 규칙을 추가한다.
- 중복된 `초안 검토 및 보완 결과` 이벤트는 제거하고 Self-Correction 완료 요약 한 곳에서 `검토 지적 수`, `실제 수정 Row 수`, `담당자 확인 필요 수`를 구분한다.
- MSDS 검색어는 사용자가 입력한 토큰의 앞뒤 공백만 제거하고 그대로 KOSHA에 전달한다. alias 치환, 대표 물질명 정규화, 부분 문자열 병합을 제거한다. 쉼표·줄바꿈 분리는 여러 물질을 구분하기 위한 입력 문법으로만 유지한다.

## 4차 구현 및 검증 결과

- finding이 정확한 평가 번호를 지정한 Row에만 review 수정본을 적용하고, 지적되지 않은 Row는 시스템 검증 초안으로 복원하도록 구현했다.
- `전체` 담당자 확인 의견을 모든 Row 비고에 복사하던 로직을 제거했다.
- 검토 의견 중복을 제거하고 별도 검토결과 로그를 Self-Correction 요약으로 합쳤다.
- 대표 변경 상세를 `수정 이유 → 적용 내용 → 위험도/판정 → 핵심 근거` 순서로 줄였다.
- 사용자 MSDS key-in의 alias 정규화와 부분 문자열 대표명 치환을 제거했다. 완전히 동일한 입력의 중복 호출 방지만 유지한다.
- 전체 Python 테스트 36건, TypeScript typecheck, Vite production build, `git diff --check`가 모두 통과했다.

## 5차 분류 배지 색상 원복

- 사용자 요청의 "박스 배경색 제거"는 로그 카드 면적의 배경색만 의미한다.
- 최상위·1단계 로그 카드는 계속 흰색으로 유지하고, 중첩 박스의 연한 청색 계층 표시는 유지한다.
- Planning, Plan 후보/평가/선택, Self-Correction, Workflow, Agent, Skill, Tool, 검증, 결과, 주의, 오류의 동그란 분류 배지는 기존 종류별 색상으로 원복한다.

## 6차 Planning 한국어·최종 완료 상태 보완

- 세 Agent system prompt에 `write_todos` 항목을 반드시 한국어로 작성하도록 명시한다.
- 이미 모델이 영어 Todo를 반환해도 시연 화면에는 알려진 HAZOP 실행 항목을 한국어로 표시한다.
- Agent의 구조화 결과가 실제 반환·파싱된 뒤 기록되는 최종 Planning 이벤트에서는, 앞 항목이 모두 완료이고 마지막 `결과 반환` 항목만 진행 중인 경우에 한해 시스템이 결과 반환 성공을 근거로 마지막 항목을 `완료 · 시스템 확인`으로 마감한다.
- 앞 단계에 대기/진행 중 항목이 남아 있으면 임의로 완료 처리하지 않는다.

### 구현 및 검증 결과

- Prompt의 한국어 Todo 규칙과 영어 HAZOP Todo 표시 변환을 구현했다.
- 구조화 결과 반환 성공 시 `4/5`의 마지막 반환 항목만 `완료 · 시스템 확인`으로 마감해 최종 `5/5`가 되도록 구현했다.
- 두 개 이상 미완료 항목이 남으면 상태를 그대로 유지하는 안전 테스트를 추가했다.
- 전체 Python 테스트 38건, TypeScript typecheck, Vite production build, `git diff --check`가 모두 통과했다.

## 7차 A/B/C 근거 전략 비교 제거

- Workflow 순서를 바꾸지 않고 문구상 근거 우선순위만 바꾸는 후보 A/B/C 비교는 시연 복잡도에 비해 실질적 가치가 낮아 제거한다.
- `Workflow Planner · 근거 활용 전략을 비교합니다`, 후보 A/B/C, Plan 평가, Plan 선택 이벤트를 모두 제거한다.
- `HazopExecutionPlan`은 고정 5단계와 성공 조건만 보관하며 candidates, selected_candidate_id, selected_candidate 메서드를 제거한다.
- Agent Prompt에는 후보 전략 대신 고정 Workflow, 확보된 MSDS·사고이력·표준 HAZOP Context와 부족한 경우에만 Tool을 호출하는 원칙을 직접 전달한다.

## 8차 로컬 사고·정비 이력 저장소 연결

### 목적

- `lookup_incident_history`가 항상 0건을 반환하는 임시 구현을 제거한다.
- 별도 DB 설치 없이도 시연에서 JSON 파일을 실제 검색하고 Agent Context에 전달하는 흐름을 보여준다.
- 샘플 데이터는 실제 사고 통계가 아니라는 점을 명확히 표시해 실제 근거처럼 오해되지 않게 한다.

### 설계

- `app/data/incident_history/incident_history_samples.json`에 암모니아 냉동, 실란·수소 공급, HF 식각, DI Water 설비의 사고·Near Miss·정비 샘플을 둔다.
- 각 레코드는 물질, 공정, 설비/Node, 변수, Guideword, 사건 유형, 발생일, 원인, 영향, 후속 조치, 빈도 참고값을 가진다.
- 조회 Tool은 query 토큰과 레코드 필드의 겹침을 점수화하고, 일치도가 높은 최대 5건만 반환한다.
- 일치 결과의 `frequency_hint`는 최종 확정값이 아니라 빈도 검토용 참고값이다.
- Workflow 시작 시 사용자 입력, 물질, Node, Guideword를 조합해 저장소를 선조회하고 `IncidentHistoryContext`에 저장한다.
- risk-draft, risk-review, action-plan Agent Prompt에 같은 선조회 Context를 전달한다.
- Agent가 `lookup_incident_history`를 추가 호출하면 동일 JSON 저장소를 다시 검색한다.

### 성공 기준

- NH3 냉동설비 검색은 1건 이상과 빈도 참고값을 반환한다.
- 관련 없는 검색은 0건과 `확인 필요` 근거를 반환한다.
- 실행 Workflow의 공통 Context에 사고·정비 이력 조회 결과가 포함된다.
- JSON 파싱·검색·Workflow 연결 테스트가 통과한다.

## 9차 최종 시연 영상 가이드 반영

### 목적

- 시작/종료 3초 표지를 제외하면 실제 브라우저와 Excel 화면만 사용한다.
- 중간 단계 표지, FAST FORWARD 배지, 완료 후 과거 로그 재탐색을 제거한다.
- 결과 자체보다 `입력 검증 → Agent Planning → Skill → Tool → Context → Self-Correction → 시스템 재검증` 흐름을 자막으로 증명한다.
- 세 물질을 사용하는 `HAZOP_ASM_Epsilon3200.xlsx`를 최종 시연 샘플로 사용한다.

### 화면 수정

- Maker, Model, 유사 HAZOP ID, 운전 의도, 사고·정비 이력의 초기값을 모두 빈 문자열로 변경한다.
- Node별 물질 입력의 예시 placeholder를 제거해 업로드 후에도 입력칸이 완전히 빈 상태가 되게 한다.
- Excel 업로드로 읽은 Node와 Guideword는 표시하되 사용자 업무정보와 물질은 자동 입력하지 않는다.

### 영상 문서 원칙

- 각 구간 자막은 먼저 시스템 전체 단계, 다음으로 현재 Agent의 역할을 설명한다.
- 한 화면 자막은 최대 2줄, 한 줄 약 35자, 핵심 로그는 확대 후 4~8초 정지한다.
- 이미 제거한 A/B/C 후보 비교를 실제 기능처럼 설명하지 않는다. 대신 고정 Workflow 안에서 부족한 근거만 조회하는 근거 선별 원칙을 설명한다.
- 결과 구간은 판단 근거, 위험도 9 이상 조치계획, 담당자 확인 필요 항목만 선별한다.

### 성공 기준

- 새 브라우저 진입 시 모든 업무 입력란이 빈 상태다.
- ASM 샘플 업로드 후 Node별 물질 입력도 빈 상태다.
- 영상 전략 Markdown에 시작/종료 표지, 실제 Key-in 값, 구간별 촬영 동작·자막·정지 시간이 포함된다.
- 프런트 타입 검사와 빌드가 통과한다.

## 10차 연결 표준 HAZOP 단일 조회

- 사용자가 입력한 표준 HAZOP ID는 Workflow 준비 단계에서 정확히 한 번만 조회한다.
- 조회 결과를 `StandardHazopContext`에 저장하고 Draft·Review·Action Agent가 모두 재사용한다.
- 각 Agent의 Tool 목록에서 `lookup_standard_hazop`을 제거해 같은 문서를 반복 조회하지 못하게 한다.
- Agent Skill과 Prompt에는 추가 조회 대신 선조회 Context를 사용하도록 명시한다.
- 화면에는 `로컬 표준 HAZOP 문서를 조회했습니다.` 로그가 실행당 최대 한 번만 표시되어야 한다.

## 11차 테스트 모드와 영상 촬영 모드 입력값 분리

- 일반 주소로 접속하면 빠른 기능 테스트를 위해 기존 예시 입력값과 Node별 물질 placeholder를 표시한다.
- URL에 `?recording=1`을 붙인 촬영 모드에서만 Maker, Model, 표준 HAZOP ID, 운전 의도, 사고·정비 이력 초기값을 비운다.
- 촬영 모드에서는 Node별 물질 placeholder도 표시하지 않는다.
- 두 모드는 화면 입력 편의만 다르고 Backend Workflow와 Agent 동작은 완전히 동일하다.
- 영상 전략 문서에는 촬영 시작 주소와 일반 테스트 주소를 모두 기록한다.

## 12차 선조회 근거 로그를 Draft Agent 작업 블록에 복구

- DeepAgent 모드에서는 `risk-draft-agent` 부모 블록을 근거 선조회 전에 먼저 연다.
- `Agent가 모델과 Tool을 사용해 작업 중입니다.` 활동 블록 아래에 사고·정비 이력과 표준 HAZOP 조회를 중첩한다.
- 두 조회는 `조회 중 → 조회 완료`를 같은 event_key로 갱신해 스피너와 완료 상태를 모두 보여준다.
- 조회 완료 후 공통 Context 전달 완료 상태를 같은 활동 블록에 표시한다.
- 표준 HAZOP 실제 조회는 기존 단일 선조회 1회를 유지하며 Agent별 반복 호출은 다시 허용하지 않는다.
- Demo fallback은 실제 모델 Agent 작업처럼 오해하지 않도록 기존 최상위 Workflow 로그를 유지한다.

## 13차 Tool 취합 상태 블록 문구·표시 순서 원복

- Draft Agent 활동 제목을 `Tool 결과를 취합해 Agent 결과를 생성 중입니다.`로 고정한다.
- 하위 완료 항목은 `사고·정비 이력 조회`, `표준 HAZOP 조회`로 간결하게 표시한다.
- 활동 설명은 `조회 결과를 모델 Context에 전달했습니다. 구조화 결과를 생성하고 검증하는 중입니다.`로 표시한다.
- 중첩 Tool이 있는 활동 블록은 `활동 제목 → Tool 목록 → 활동 설명` 순서로 렌더링한다.
- 이후 모델 스트림 이벤트가 도착해도 같은 event_key를 갱신하여 제목과 Tool 완료 내역을 유지한다.

## 14차 오후 3:34 기준점 복원 + 표준 HAZOP 단일 조회 유지

- 파일 변경 시각으로 확인한 15:34 상태의 로그/화면 구조로 복원한다.
- 사고·정비 이력 JSON 조회와 Agent 공통 Context 전달은 당시 구현을 유지한다.
- 이후 추가한 선조회 로그의 Draft Agent 중첩, 촬영 URL 모드, Tool 취합 렌더링 순서 변경은 되돌린다.
- 예외로 표준 HAZOP은 연결된 문서를 Workflow에서 1회만 조회하고, 세 Agent는 같은 Context를 재사용하는 최신 요구를 유지한다.

## 15차 Draft Agent Tool 취합 블록에 선조회 결과만 이동

- 15:34 복원 상태의 다른 UI·Planning·Skill·Self-Correction 로그는 변경하지 않는다.
- DeepAgent 모드에서 사고·정비 이력과 연결 표준 HAZOP 결과 두 건만 최상위 로그에서 제외한다.
- 두 결과의 기존 상세 내용은 그대로 `risk-draft-agent > Tool 결과를 취합해 Agent 결과를 생성 중입니다.` 하위에 표시한다.
- 표준 HAZOP 조회 실행은 Workflow 선조회 1회를 유지하며 Agent Tool로 재조회하지 않는다.
- Demo fallback에서는 Draft Agent 실행처럼 오해되지 않도록 기존 최상위 결과 로그를 유지한다.

## 16차 Agent 고정 헤더에 Planning 실행 현황 표시

- 각 Agent 카드의 기존 sticky 헤더 안에 해당 Agent의 Planning 현재 제목을 한 줄로 표시한다.
- 진행 중에는 `↻`, 완료 후에는 `✓`를 표시한다.
- 상세 Planning 블록과 다른 로그 구조·순서·동작은 변경하지 않는다.
- Tool·Context·Self-Correction 영역을 스크롤해도 Agent 이름과 Planning 완료 현황을 함께 확인할 수 있어야 한다.
- Tool 호출 목적은 후보별 정책이 아니라 Tool별 고정 설명에서 가져온다.
- 각 전문 Agent의 실제 `write_todos` Planning과 실행 현황은 유지한다.
