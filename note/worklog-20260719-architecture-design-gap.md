# 첨부 HAZOP AI Agent 아키텍처 설계 반영 작업

## 1. 작업 목적

첨부 설계문서 `HAZOP AI Agent 아키텍처 보완사항 정리`를 현재 `feature/agent-review-severity` 작업본과 대조하고, 이미 반영된 부분은 유지하며 남은 구조적 차이만 보완한다.

## 2. 현재 작업본에 이미 반영된 항목

- Workflow가 입력 물질별 MSDS를 중복 제거 후 최초 1회 조회한다.
- 위험성평가 작성, 독립 AI 의미 검토, 조치계획 작성을 Workflow가 별도 Agent 호출로 강제한다.
- Review Agent가 보완한 전체 Risk Row를 시스템이 다시 검증하고 최종 결과에 사용한다.
- Node/변수/Guideword 및 Row 개수 일치, 빈도·강도 범위, 근거 존재, 위험도 계산, 고위험 선별, Action 참조를 시스템 코드가 검사한다.
- 위험도 9 이상인 경우에만 Action Plan Agent를 호출한다.
- 추가 MSDS, 사고이력, 표준 HAZOP 조회 함수가 Agent Tool로 등록된다.
- `severity-estimation` Skill과 강도 1~4 기본 기준이 존재한다.
- Skill source 루트, 폴더명/frontmatter 이름, `read_file`, 읽기 전용 FilesystemBackend 문제가 수정됐다.
- DeepAgents 실제 로더가 8개 Skill을 발견하는 테스트가 존재한다.

## 3. 추가 보완이 필요한 항목

### 3.1 Excel 위험도기준 Context

- `위험도기준` Sheet의 빈도·강도·위험도 기준을 구조화해 파싱한다.
- `HazopDraftContext`에 업로드 기준표와 출처/누락 상태를 넣는다.
- Risk Draft, Risk Review, Action Plan Prompt에 동일한 기준표를 전달한다.
- 기준표가 없으면 프로젝트 기본 기준을 사용하되 `확인 필요` 상태를 명시한다.

### 3.2 스키마 수준 안전 규칙

- 빈도 1~5, 강도 1~4를 Pydantic 필드 범위로 강제한다.
- 필수 근거 목록과 근거 문장의 최소 길이를 스키마에서 강제한다.
- 시스템 검증도 이 규칙을 다시 확인하여 방어 계층을 이중화한다.
- Agent 참고용 위험도 Tool도 범위 밖 값을 조용히 보정하지 않고 오류로 거부한다.

### 3.3 Review 결과 보존

- `review_findings`를 문자열 목록이 아닌 구조화 결과로 만든다.
- 검토 대상 Row, 검토 범주, 발견 내용, 반영 내용, 담당자 확인 필요 여부를 보존한다.
- 최종 `HazopDraftResult`, `HazopResult`, result.json과 진행 로그에 포함한다.

### 3.4 실제 실행 trace와 로그 일치

- Agent 실행 전에는 `Skill을 읽었습니다`, `Tool을 호출했습니다` 같은 완료 표현을 사용하지 않는다.
- DeepAgents 반환 메시지에서 실제 `read_file`과 Domain Tool 호출을 추출한다.
- 필수 Skill의 `SKILL.md` 읽기 성공이 trace에 없으면 해당 LLM 실행을 실패 처리한다.
- 실제 trace에서 확인된 Skill/Tool만 화면 로그에 표시한다.
- Workflow 직접 실행은 `workflow`, 시스템 규칙 검증은 `validation`, 실제 Agent Tool은 `tool`로 구분한다.

### 3.5 MSDS 보완 Tool 계약

- `lookup_msds_detail(material, cas_number=None, requested_sections=None)` 형태를 지원한다.
- 물질명, 요청 CAS, 요청 Section, 유해성, 취급·저장, 누출·화재 대응, 출처, 성공 여부, fallback 여부, 조회 trace를 반환한다.
- 실제 KOSHA 서비스가 제공하지 않는 CAS/Section 세분 정보는 `확인 필요`로 명시한다.

## 4. 이번 범위에서 제외되는 항목

- 실제 사고이력 DB Repository 연결
- 실제 표준 HAZOP 문서 검색 인덱스/Repository 연결
- 운영 인증정보와 외부 DB schema가 없으므로 placeholder를 임의 데이터로 대체하지 않는다.

쉽게 말하면, Agent가 사용할 안전한 업무 창구와 결과 형식은 완성하지만 실제 사내 DB가 없는 상태에서 사고이력이나 표준문서를 만들어내지는 않는다.

## 5. 성공 기준

- 세 샘플 Excel에서 `위험도기준` 15개 행을 읽고 Context에 전달한다.
- 기준표가 없는 Excel도 프로젝트 기본 기준과 `확인 필요` 표시로 안전하게 처리한다.
- Pydantic이 빈도 0/6, 강도 0/5, 빈 근거를 거부한다.
- Review Agent 결과가 최종 API/JSON 결과에 남는다.
- 실제 Skill 읽기와 Tool 호출만 trace 로그로 표시된다.
- 세 전문 Agent가 지정된 필수 Skill을 실제로 읽지 않으면 LLM 모드가 성공 처리되지 않는다.
- MSDS 보완 Tool의 확장된 반환 계약이 테스트된다.
- 기존 샘플 회귀 테스트와 전체 테스트, compileall, Frontend typecheck/build가 통과한다.

## 6. 구현 결과

- `validate_and_parse_excel_with_criteria()`가 업로드 `위험도기준` 15개 행을 구조화한다.
- 기존 `validate_and_parse_excel()`의 2개 반환값 계약은 호환 목적으로 유지했다.
- 업로드 기준표가 없으면 동일한 프로젝트 기본 15개 기준을 사용하고 `requires_confirmation=true`를 남긴다.
- Risk Draft, Risk Review, Action Plan Prompt가 동일한 기준표 JSON을 받는다.
- 시스템의 위험등급 문구도 업로드 기준표의 `위험도` 행에서 결정한다.
- Demo 강도·빈도 근거에도 적용 점수, 기준표 문구, MSDS 출처를 포함한다.
- 빈도·강도 범위와 필수 evidence를 Pydantic 스키마와 시스템 검증이 모두 강제한다.
- Agent 참고용 위험도 Tool은 범위 밖 값을 보정하지 않고 오류로 거부한다.
- Review Finding을 Row 번호, 범주, 발견 내용, 반영 내용, 담당자 확인 여부 구조로 저장한다.
- 담당자 확인이 필요한 Review Finding은 Risk Row 비고에도 `검토 확인 필요`로 연결한다.
- Review Finding은 result.json/API 응답과 화면의 `독립 AI 검토 의견` 표에 표시한다.
- DeepAgents 반환 메시지에서 실제 `read_file`과 Domain Tool 호출을 추출한다.
- 각 전문 Agent가 필수 Skill을 실제로 읽은 성공 trace가 없으면 LLM 모드를 성공 처리하지 않는다.
- Workflow 직접 실행, Agent 실행, 실제 Skill/Tool, 시스템 검증 로그 종류를 분리했다.
- MSDS 보완 Tool에 CAS, 요청 Section, 성공/fallback 여부, 출처, 제한사항을 포함했다.
- DeepAgents 실제 권한 객체와 절대경로 패턴을 적용해 Skill 밖 읽기와 전체 쓰기를 차단했다.

## 7. 검증 결과

- Python 전체 테스트: `24 passed`
- 세 회귀 샘플의 위험도기준 15개 행 파싱 확인
- 기준표 없는 Excel의 기본 기준 fallback 및 담당자 확인 표시 확인
- Python compileall 통과
- Frontend TypeScript typecheck 통과
- Frontend production build 통과
- Git diff whitespace 검사 통과
- 현재 실행 환경에는 Azure OpenAI 연결값 4종이 없어 실제 외부 LLM 호출은 수행하지 못했다. 실제 trace 형태를 모사한 Agent 테스트로 Skill 읽기 강제와 세 Agent 순서를 검증했다.
