# HAZOP 검증·검토·강도 Skill 보완 작업 설계

## 1. 목표

현재 DeepAgents 기반 HAZOP 생성 흐름을 아래 책임 분리 구조로 완성한다.

1. Workflow/System code가 Excel을 검증하고 입력된 모든 물질의 MSDS를 최초 1회 조회한다.
2. 위험성평가 작성 Agent는 초안 중 정보가 부족할 때만 MSDS 상세 조회, 사고이력 조회, 표준 HAZOP 조회 Tool을 추가 호출한다.
3. System code가 정답이 분명한 항목을 검증하고 위험도를 계산한다.
4. 독립 `risk-review-agent` LLM 호출이 의미·논리·근거 품질을 검토하고 보완한 전체 Row를 반환한다.
5. System code가 검토 반영본을 다시 검증·계산하고 위험도 9 이상 항목만 선별한다.
6. `action-plan-agent` LLM이 고위험 항목의 조치계획 초안을 생성한다.
7. Workflow/System code가 결과 Excel을 저장한다.

## 2. 확인된 현재 문제

- `risk-review-agent`는 정의와 화면 로그만 있고 독립 LLM 호출 및 결과 반영이 없다.
- 조치계획은 Azure OpenAI 연결 시 DeepAgent/LLM 호출로 생성되지만, 검토 전 초안을 바로 고위험 선별에 사용한다.
- 최초 MSDS 조회는 Workflow에 있으나 Agent가 필요할 때 추가 상세 조회할 MSDS Tool이 없다.
- 강도 전용 Skill과 1~4 강도 기준표가 없다.
- DeepAgents Skill 경로로 각 Skill 디렉터리를 직접 전달하여, Skill 모음의 하위 디렉터리를 찾는 로더가 아무 Skill도 발견하지 못한다.
- Skill 디렉터리의 밑줄 이름과 `SKILL.md` frontmatter의 하이픈 이름이 달라 DeepAgents 0.6.3 이름 검증에 실패한다.
- `read_file` Tool 제외 및 전체 파일 읽기 거부 권한 때문에 Agent가 Skill 본문을 읽을 수 없다.
- DeepAgents 기본 `StateBackend`는 메모리 파일만 보기 때문에 로컬 절대경로의 `SKILL.md`를 읽을 수 없다.

## 3. 구현 범위

### 3.1 Workflow/System code 검증

다음을 AI가 아닌 일반 코드로 검증한다.

- Node/변수/Guideword 입력 일치
- 입력 Guideword 수와 결과 Row 수의 정확한 일치
- 중복/누락 Row 금지
- 빈도 1~5, 강도 1~4 범위
- 판단/빈도/강도 근거 존재
- 시스템의 `빈도 * 강도` 위험도 계산
- 위험도 9 이상 조치 대상 선별
- 조치계획이 선별된 원본 위험성평가 Row만 참조하는지 확인

### 3.2 AI 의미 검토

별도 LLM 호출인 `risk-review-agent`가 아래를 검토한다.

- 원인과 결과의 현실적 연결
- 고위험 물질 누출 등의 강도 과소평가
- 현재 안전조치가 예방/완화 중 무엇을 담당하는지
- MSDS와 결과 문장의 모순
- 사고이력 및 표준 HAZOP 대비 낮은 평가의 근거 충분성

검토 Agent는 지적 목록만 반환하지 않고 보완한 전체 위험성평가 Row를 반환한다. 시스템은 그 Row를 다시 검증·계산한 뒤 최종 초안에 사용한다.

### 3.3 Severity Skill

`severity-estimation` Skill을 추가하고 다음 기준을 고정한다.

- 강도 1: 영향 없음, 이상 등급/관리사고
- 강도 2: 경미한 불휴업 재해, C급/준사고
- 강도 3: 경미한 휴업 재해, B급 경미재해
- 강도 4: 중대재해, A급/사망 등 중대재해

판단 근거 우선순위는 MSDS 물질 위험성 및 영향 범위, 사고이력, 표준 HAZOP, 사용자 입력, 일반 보수적 판단 순서로 둔다. 자료가 부족하면 근거에 `확인 필요`를 남긴다.

### 3.4 Skill 로딩 복구

- DeepAgents에는 Skill 하위 디렉터리를 담은 `skills` 루트 경로 하나를 전달한다.
- Skill 폴더명과 frontmatter `name`을 하이픈 형식으로 일치시킨다.
- `read_file`은 유지하되 쓰기/실행 Tool은 제외한다.
- 읽기 권한은 Skill 루트만 허용하고 나머지 경로는 거부한다.
- 로컬 Skill 루트를 실제로 읽을 수 있도록 `FilesystemBackend`를 명시한다.

## 4. 성공 기준

- Skill 메타데이터 로더가 모든 HAZOP Skill과 새 `severity-estimation`을 발견한다.
- DeepAgent에 `read_file`이 보이고 쓰기/실행 Tool은 보이지 않는다.
- Workflow의 최초 MSDS 조회는 입력 물질마다 1회 수행된다.
- Agent Tool 목록에 추가 MSDS 상세 조회, 사고이력, 표준 HAZOP 조회가 포함된다.
- 위험성평가 작성 LLM과 독립 검토 LLM이 별도로 호출된다.
- 검토 Agent가 반환한 보완 Row가 시스템 재검증 후 최종 결과와 조치계획 입력에 사용된다.
- 조치계획은 위험도 9 이상 항목에 대해 LLM `action-plan-agent`가 생성한다.
- 기존 demo fallback은 Azure OpenAI 미설정/장애 시에만 PoC 지속용으로 유지하되, 실제 LLM 검토로 오인시키는 로그를 남기지 않는다.
- 단위 테스트와 시나리오 테스트가 통과한다.

## 5. 변경 제한

- Excel 입력/출력 양식과 위험도 기준(9 이상)은 바꾸지 않는다.
- 실제 사고이력 DB와 표준 HAZOP 저장소 연결은 이번 범위에 포함하지 않으며, 연결되지 않은 경우 명시적으로 `확인 필요`를 반환한다.
- AI가 Node, 변수, Guideword 또는 위험도 점수를 새로 확정하지 못하게 한다.

## 6. 구현 및 검증 결과

- DeepAgents 0.6.3 실제 Skill 로더로 8개 Skill 발견을 확인했다.
- `severity-estimation` Skill과 강도 1~4 기준표를 추가했다.
- 입력 물질 중복 제거 후 물질별 Workflow 최초 조회가 정확히 1회씩 실행되는 테스트를 추가했다.
- 위험성평가 작성, 독립 의미 검토, 조치계획 작성이 각각 별도 LLM Agent 생성으로 이어지고 세 Agent 모두 MSDS/사고이력/표준 HAZOP 보완 조회 Tool을 받는지 확인했다.
- 독립 검토가 Silane 누출 강도를 2에서 4로 보완한 경우, 시스템 재계산 결과 12가 최종 위험성평가와 조치계획 입력에 반영되는 테스트를 추가했다.
- 시스템 검증의 Row 누락 및 강도 범위 초과 거부를 확인했다.
- 전체 Python 테스트: `20 passed`
- Python compileall 및 Git diff whitespace 검사 통과
- Frontend TypeScript typecheck 및 production build 통과
- 현재 실행 환경에는 Azure OpenAI 설정 4종이 없어 실제 외부 LLM 호출은 수행하지 못했으며, LLM 단계는 독립 Agent를 모사한 단위 테스트로 검증했다.
