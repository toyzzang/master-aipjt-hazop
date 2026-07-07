# Deepagent 기반 HAZOP Engine 최종 설계 및 구현 계획

## 1. 목적

현재 HAZOP PoC는 `app/services/agent.py` 안에서 Excel 검증, MSDS 조회, LLM 초안 생성, 위험도 계산, 조치계획서 생성, 로그 생성을 한 흐름으로 처리한다.

이번 작업의 목적은 전체 웹앱을 Agent Framework로 바꾸는 것이 아니다. Deep Agents(`langchain-ai/deepagents`)는 실제 전문 판단이 필요한 아래 영역에만 적용한다.

- `#3 위험성평가` 초안 생성
- `#4 조치계획서` 초안 생성
- 전문 판단 절차 관리
- 판단 근거 생성
- 초안 검토
- 작성 -> 검토 -> 필요 시 수정 루프

쉽게 말하면, 업로드/다운로드/DB/Excel 저장 같은 시스템 업무는 기존 Python 코드가 계속 맡고, HAZOP 판단 초안을 만드는 엔진만 Deepagent 구조로 분리한다.

## 2. 핵심 설계 원칙

### 2.1 Deepagent는 판단 흐름만 관리한다

Deepagent는 다음을 담당한다.

- 어떤 근거 자료를 봐야 하는지 판단한다.
- 사고이력, 표준 HAZOP, MSDS 근거를 바탕으로 초안을 만든다.
- 작성 초안을 검토한다.
- 근거 부족, 표준 HAZOP 불일치, 규칙 위반을 찾아낸다.
- 필요하면 수정 초안을 다시 요청한다.

Deepagent가 담당하지 않는 일은 다음과 같다.

- 파일 업로드
- 파일 다운로드
- DB 저장
- 최종 Excel 저장
- 최종 위험도 계산
- FastAPI 라우팅

### 2.2 AI는 기준을 새로 만들지 않는다

고정 규칙은 기존 프로젝트 원칙을 유지한다.

- AI는 Node, 변수, Guideword를 새로 만들면 안 된다.
- AI는 업로드 Excel의 `#1 노드리스트`, `#2 가이드워드` 기준으로만 작성한다.
- 빈도는 1~5 후보만 허용한다.
- 강도는 1~4 후보만 허용한다.
- 위험도는 AI가 계산하지 않는다.
- 최종 위험도는 시스템 코드가 `빈도 * 강도`로 계산한다.
- 위험도 9 이상이면 `#4 조치계획서` 생성 대상이다.
- Agent 로그에는 판단과 근거를 함께 남긴다.

### 2.3 빈도 산정은 근거 데이터를 우선한다

빈도는 "얼마나 자주 발생할 수 있는가"에 대한 판단이다. 따라서 단순히 Node/변수/Guideword만 보고 정하지 않는다.

우선순위는 다음과 같다.

1. 기존 사고이력, Near Miss, 알람, 정비/점검 이력
2. 유사 표준공정위험성평가서의 빈도 판단
3. 사용자 비고/이력 정보
4. 일반 HAZOP 판단 규칙
5. 데이터 부족 시 `확인 필요`

## 3. 개념 구분

### 3.1 일반 코드

일반 코드는 정해진 시스템 처리를 담당한다.

- Excel 업로드 저장
- Excel 다운로드
- DB 저장
- 결과 JSON 저장
- 최종 Excel export
- SSE 로그 전송

### 3.2 Tool

Tool은 Agent가 호출할 수 있는 단일 기능이다.

예:

- Excel 읽기
- MSDS 조회
- 사고이력 조회
- 표준 HAZOP 조회
- 위험도 계산
- LLM JSON 호출
- Schema 검증

Tool은 "판단 절차"가 아니라 "기능 버튼"이다.

### 3.3 Skill

Skill은 업무 절차, 판단 기준, 금지 규칙, 출력 형식을 묶은 전문 작업 설명서다.

예:

- HAZOP 위험성평가 초안 작성 절차
- HAZOP 초안 검토 절차
- 조치계획서 작성 절차
- 사고이력 기반 빈도 산정 절차
- 표준 HAZOP 참조 절차

Deep Agents 문서 기준으로 Skill은 `SKILL.md`가 있는 디렉터리 단위로 관리한다.

### 3.4 Agent

Agent는 Skill과 Tool을 사용해서 실제 판단을 수행하는 담당자다.

예:

- `RiskDraftAgent`: `#3 위험성평가` 초안 작성자
- `RiskReviewAgent`: 초안 검토자
- `ActionPlanAgent`: `#4 조치계획서` 작성자

### 3.5 Workflow

Workflow는 전체 순서와 중간 상태를 관리한다.

예:

```text
MSDS 근거 정리
-> 사고이력 분석
-> 표준 HAZOP 참조
-> 빈도 후보 산정
-> #3 초안 작성
-> #3 초안 검토
-> 위험도 계산
-> #4 조치계획서 작성
```

## 4. 최종 폴더 구조

1차 구현 목표 구조는 다음과 같다.

```text
app/
  hazop_engine/
    __init__.py
    context.py
    workflow.py
    events.py

    agents/
      __init__.py
      deepagent_factory.py

    skills/
      hazop_risk_draft/
        SKILL.md
      hazop_risk_review/
        SKILL.md
      hazop_action_plan/
        SKILL.md
      incident_history_analysis/
        SKILL.md
      standard_hazop_reference/
        SKILL.md
      frequency_estimation/
        SKILL.md
      standard_hazop_comparison/
        SKILL.md

    tools/
      __init__.py
      msds_tools.py
      incident_history_tools.py
      standard_hazop_tools.py
      risk_tools.py
      validation_tools.py
```

기존 서비스 파일은 당장 크게 이동하지 않는다.

- `app/services/excel.py`
- `app/services/msds.py`
- `app/services/risk.py`
- `app/services/llm.py`
- `app/services/db.py`

초기에는 위 서비스를 Deepagent Tool 래퍼가 호출한다.

## 5. Context 설계

`HazopDraftContext`는 Deepagent 실행 중 공유되는 작업 메모리다.

쉽게 말하면, 여러 Agent와 Skill이 함께 보는 "작업 파일철"이다.

예상 필드:

```text
input_data
nodes
guidewords
msds_context
incident_history_context
standard_hazop_context
frequency_evidence
draft_risk_rows
review_findings
final_risk_rows
action_rows
events
```

Deepagent 자체도 상태를 관리할 수 있지만, 안전문서 생성에서는 명시적인 Context 모델을 유지한다.

근거:

- 어떤 데이터가 어떤 판단에 쓰였는지 추적하기 쉽다.
- 테스트하기 쉽다.
- 나중에 Deepagent API가 바뀌어도 외부 인터페이스를 유지할 수 있다.

## 6. Skill 목록과 역할

### 6.1 `HazopRiskDraftSkill`

역할:

- `#2 가이드워드` 각 Row를 기준으로 `#3 위험성평가` 초안을 작성한다.

절차:

1. Node, 변수, Guideword를 입력값 그대로 확인한다.
2. 물질과 MSDS 근거를 확인한다.
3. 사고이력 근거를 확인한다.
4. 표준 HAZOP 유사 항목을 확인한다.
5. Guideword가 의미하는 일탈을 작성한다.
6. 가능한 원인을 작성한다.
7. 가능한 결과를 작성한다.
8. 현재안전조치를 작성한다.
9. 빈도/강도 후보와 근거를 작성한다.
10. `risk_score`는 0으로 둔다.

금지:

- 새 Node 생성 금지
- 새 변수 생성 금지
- 새 Guideword 생성 금지
- 위험도 직접 계산 금지
- 근거 없는 단정 금지

### 6.2 `HazopRiskReviewSkill`

역할:

- 생성된 `#3 위험성평가` 초안을 검토한다.

검토 기준:

- 입력 Excel에 없는 Node/변수/Guideword가 있는가?
- 빈도는 1~5 범위인가?
- 강도는 1~4 범위인가?
- 판단근거/빈도근거/강도근거가 비어 있지 않은가?
- 고위험 물질인데 강도가 너무 낮게 잡히지 않았는가?
- 표준 HAZOP와 크게 다른 판단이 있는가?
- 근거 부족 시 `확인 필요`가 남아 있는가?

### 6.3 `HazopActionPlanSkill`

역할:

- 위험도 9 이상 항목에 대해 `#4 조치계획서` 초안을 작성한다.

절차:

1. 고위험 Row를 확인한다.
2. 현재 안전조치의 부족한 점을 찾는다.
3. 개선권고사항을 작성한다.
4. 조치 후 빈도 후보를 작성한다.
5. 조치 후 강도 후보를 작성한다.
6. 조치 근거를 작성한다.

주의:

- 조치 후 위험도도 시스템 코드가 다시 계산한다.
- 물질 자체 위험성이 바뀌지 않는 경우 강도는 보통 유지한다.

### 6.4 `IncidentHistoryAnalysisSkill`

역할:

- 기존 사고이력, Near Miss, 알람, 정비/점검 이력을 분석해 빈도 산정 근거를 만든다.

초기 PoC에서는 실제 DB가 없으면 demo/empty 결과를 반환한다.

출력 예:

```json
{
  "matched_incidents": 0,
  "frequency_hint": null,
  "evidence": ["사고이력 데이터가 없어 표준 HAZOP와 사용자 비고를 우선 참고"]
}
```

### 6.5 `StandardHazopReferenceSkill`

역할:

- 사용자가 입력한 표준공정위험성평가서 Link 또는 ID를 기준으로 유사 Row를 찾는다.

분석 대상:

- Node 유사성
- 변수 유사성
- Guideword 유사성
- 물질/공정 유사성
- 기존 원인/결과/안전조치
- 기존 빈도/강도 판단

초기 PoC에서는 실제 문서 저장소가 없으면 연결 ID를 로그에 남기고 `확인 필요` 근거를 반환한다.

### 6.6 `FrequencyEstimationSkill`

역할:

- 사고이력, 표준 HAZOP, 사용자 비고, Guideword 성격을 종합해서 빈도 후보를 산정한다.

원칙:

- 사고이력이 있으면 가장 우선한다.
- 유사 표준 HAZOP의 빈도 판단을 강한 근거로 사용한다.
- 데이터가 부족하면 낮은 확신도와 함께 `확인 필요`를 남긴다.

### 6.7 `StandardHazopComparisonSkill`

역할:

- 생성된 초안과 표준 HAZOP 유사 항목의 차이를 검토한다.

예:

- 표준 HAZOP는 Silane Leak 강도 4인데 초안은 강도 2인 경우 경고한다.
- 표준 HAZOP의 현재안전조치에 ESV가 있는데 초안에서 누락된 경우 보완 의견을 남긴다.

## 7. Tool 목록과 역할

### 7.1 `msds_lookup_tool`

- 기존 `app/services/msds.py`를 호출한다.
- KOSHA MSDS 조회, Bing fallback, 내장 요약 fallback 흐름은 유지한다.

### 7.2 `incident_history_lookup_tool`

- 사고이력 데이터를 조회한다.
- 초기 PoC에서는 빈 결과 또는 샘플 데이터를 반환한다.
- 추후 사고이력 DB/API 연결 지점이 된다.

### 7.3 `standard_hazop_lookup_tool`

- 표준공정위험성평가서 Link 또는 ID를 조회한다.
- 초기 PoC에서는 실제 문서 조회가 불가능하면 입력된 ID와 `확인 필요` 근거를 반환한다.

### 7.4 `calculate_risk_tool`

- 기존 `app/services/risk.py`를 호출한다.
- 빈도 clamp, 강도 clamp, 위험도 계산, 위험도 등급, 조치필요여부 판단을 수행한다.
- Deepagent가 아니라 시스템 코드가 최종 계산한다.

### 7.5 `validate_hazop_rows_tool`

- Pydantic schema로 LLM/Deepagent 결과를 검증한다.
- 필수 필드 누락, 타입 오류, 범위 오류를 확인한다.
- 입력 Excel에 없는 Node/변수/Guideword 사용 여부를 확인한다.

## 8. Deepagent 구성

Deep Agents는 `create_deep_agent()`를 통해 생성한다.

개념 코드:

```python
from deepagents import create_deep_agent


def create_hazop_deep_agent(model, tools, system_prompt):
    return create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
    )
```

실제 구현 시 확인할 부분:

- Azure OpenAI를 LangChain chat model 형태로 연결하는 방법
- `deepagents` 패키지 버전 고정
- `langchain-openai` 필요 여부
- async 실행 지원 방식
- event streaming을 SSE 로그로 연결하는 방식

## 9. Workflow 실행 흐름

외부 진입점은 하나로 둔다.

```python
async def generate_hazop_draft(context: HazopDraftContext) -> HazopDraftResult:
    ...
```

내부 흐름:

```text
1. Deepagent 입력 메시지 구성
2. MSDS/사고이력/표준 HAZOP Tool 제공
3. 사고이력 분석
4. 표준 HAZOP 참조
5. 빈도 후보 산정
6. #3 위험성평가 초안 작성
7. #3 초안 검토
8. 검토 지적사항이 있으면 수정
9. 시스템 코드로 빈도/강도 clamp 및 위험도 계산
10. 위험도 9 이상 항목 선별
11. #4 조치계획서 초안 작성
12. 조치 후 위험도 시스템 코드로 재계산
13. 결과 schema 검증
14. `HazopDraftResult` 반환
```

## 10. 기존 코드와 연결 방식

기존 `app/services/agent.py`의 큰 흐름은 유지한다.

유지:

- request_id 생성
- 작업 폴더 생성
- Excel 검증
- MSDS 조회 로그
- SSE 로그 전송
- 결과 Excel export
- result.json 저장
- done/error 이벤트

교체:

- 기존 `_run_risk_llm_with_progress()`
- 기존 `_generate_risk_rows_demo()` 일부 역할
- 기존 `_run_action_llm_with_progress()`
- 기존 `_generate_action_rows_demo()` 일부 역할

변경 후:

```text
run_hazop_agent()
  -> validate_and_parse_excel()
  -> material/MSDS 준비
  -> generate_hazop_draft(context)
  -> export_result_excel()
```

초기 구현에서는 Deepagent 실패 시 기존 demo generator fallback을 유지한다.

## 11. 로그 설계

사용자는 AI/Agent 개념에 익숙하지 않으므로 로그는 판단과 근거를 쉽게 보여줘야 한다.

예:

```text
사고이력 근거를 확인했습니다.
근거: 현재 PoC에는 사고이력 DB가 없어 사용자 비고와 표준 HAZOP 근거를 우선 참고합니다.

표준 HAZOP 유사 항목을 확인했습니다.
근거: 입력된 표준 HAZOP ID를 참조 대상으로 기록했지만 실제 문서 조회 기능은 아직 PoC 범위입니다.

빈도 후보를 산정했습니다.
근거: 유사 사고이력 없음, 표준 HAZOP 확인 필요, Guideword 특성상 빈도 2 후보를 제안합니다.
```

## 12. 의존성 계획

`requirements.txt`에 추가 후보:

```text
deepagents
langchain
langchain-openai
langgraph
```

주의:

- 실제 필요한 패키지는 설치/ import 테스트 후 확정한다.
- 버전은 가능하면 고정한다.
- Azure OpenAI 연결은 기존 `openai.AsyncAzureOpenAI` 직접 호출 방식과 다를 수 있으므로 별도 검증한다.

## 13. 구현 순서

### 1단계: 설계 고정

- 이 문서를 기준으로 사용자 확인을 받는다.
- 구현 범위를 확정한다.

### 2단계: 의존성 추가 및 import 검증

- `requirements.txt`에 Deep Agents 관련 패키지를 추가한다.
- 로컬에서 import 가능한지 확인한다.
- Azure OpenAI LangChain 연결 방식을 검증한다.

### 3단계: `hazop_engine` 골격 생성

- `context.py`
- `workflow.py`
- `events.py`
- `agents/deepagent_factory.py`
- `tools/`
- `skills/*/SKILL.md`

### 4단계: Tool 래퍼 구현

- MSDS 조회 Tool
- 사고이력 조회 Tool
- 표준 HAZOP 조회 Tool
- 위험도 계산 Tool
- Schema 검증 Tool

### 5단계: Skill 문서 작성

- HAZOP 위험성평가 초안 작성 Skill
- HAZOP 초안 검토 Skill
- 조치계획서 작성 Skill
- 사고이력 분석 Skill
- 표준 HAZOP 참조 Skill
- 빈도 산정 Skill
- 표준 HAZOP 비교 Skill

### 6단계: Deepagent factory 구현

- `create_deep_agent()` 래퍼 작성
- Tool 목록 연결
- system prompt 작성
- 필요 시 filesystem/shell 도구는 숨기거나 제한한다.

### 7단계: Workflow 구현

- `generate_hazop_draft(context)` 구현
- Deepagent 결과를 Pydantic schema로 검증
- 시스템 코드로 위험도 재계산
- 결과를 `HazopDraftResult`로 반환

### 8단계: 기존 `agent.py` 연결

- 기존 초안 생성 구간만 `hazop_engine.workflow.generate_hazop_draft()`로 교체한다.
- 기존 demo fallback을 유지한다.
- 기존 SSE 이벤트 흐름은 유지한다.

### 9단계: 테스트 추가

- schema 검증 테스트
- Node/변수/Guideword 신규 생성 금지 테스트
- 위험도 시스템 계산 테스트
- 위험도 9 이상만 조치계획서 생성 테스트
- Deepagent 실패 시 fallback 테스트

### 10단계: 샘플 시나리오 검증

- `HAZOP_CleanTech_CT-DIW-100.xlsx`
- `HAZOP_ASM_Epsilon3200.xlsx`
- `HAZOP_ThermoVac_TV-ETCH-200.xlsx`

## 14. 성공 기준

구현 완료 판단 기준:

- 샘플 Excel 3개가 정상 생성된다.
- 웹 화면에서 Excel 업로드가 된다.
- Agent 로그가 실시간으로 표시된다.
- Deepagent 기반으로 `#3 위험성평가` 초안이 생성된다.
- 위험도는 시스템 코드가 `빈도 * 강도`로 계산한다.
- 위험도 9 이상 항목만 `#4 조치계획서` 대상으로 선별된다.
- `#4 조치계획서` 초안이 생성된다.
- 결과 Excel을 다운로드할 수 있다.
- AI가 입력 Excel에 없는 Node/변수/Guideword를 새로 만들지 않는다.
- 빈도 판단에는 사고이력/표준 HAZOP 근거 부족 여부가 명시된다.
- Deepagent 실패 시 demo fallback으로 PoC 흐름이 끊기지 않는다.

## 15. 검증 명령

기본 검증:

```bash
python scripts/create_sample_excels.py
python -m compileall app scripts tests
pytest
```

웹 검증:

```bash
uvicorn app.main:app --reload --port 8000
```

Docker 검증:

```bash
docker compose up --build
```

API 확인:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/jobs
```

## 16. 주요 리스크와 대응

### 16.1 Deep Agents API/버전 리스크

리스크:

- `deepagents` API가 버전에 따라 바뀔 수 있다.

대응:

- `deepagent_factory.py`에만 Deep Agents 직접 호출을 모은다.
- 외부에서는 `generate_hazop_draft(context)`만 호출한다.

### 16.2 Azure OpenAI 연결 방식 차이

리스크:

- 기존 `openai.AsyncAzureOpenAI` 직접 호출 방식과 LangChain model 설정이 다를 수 있다.

대응:

- 별도 model factory를 만든다.
- 환경 변수는 기존 `.env` 이름을 최대한 재사용한다.

### 16.3 Agent 자율성 과다

리스크:

- Agent가 Node/변수/Guideword를 새로 만들거나 위험도 기준을 바꿀 수 있다.

대응:

- Skill과 system prompt에 금지 규칙을 명시한다.
- schema 검증 Tool에서 입력 기준 위반을 잡는다.
- 최종 위험도 계산은 시스템 코드만 수행한다.

### 16.4 Tool 권한 과다

리스크:

- Deepagent에 파일 쓰기, shell 실행 등 불필요한 도구를 주면 통제 범위가 커진다.

대응:

- 1차 구현에서는 초안 생성에 필요한 custom Tool만 제공한다.
- Excel 저장/DB 저장 Tool은 Deepagent에 제공하지 않는다.

### 16.5 사고이력/표준 HAZOP 데이터 부재

리스크:

- 초기 PoC에서는 실제 사고이력 DB나 표준 HAZOP 저장소가 없을 수 있다.

대응:

- Tool은 빈 결과와 `확인 필요` 근거를 반환한다.
- Skill은 데이터 부족을 명시하도록 한다.
- 추후 실제 데이터 연결 지점만 교체한다.

## 17. 구현 보류 사항

이번 1차 구현에서 보류할 수 있는 항목:

- 실제 사고이력 DB 구축
- 실제 표준 HAZOP 문서 검색 인덱스 구축
- LangSmith 운영 모니터링
- Human-in-the-loop 승인 UI
- Deepagent filesystem/shell 도구 사용
- 복잡한 병렬 subagent 실행

이 항목들은 Deepagent 골격이 안정화된 뒤 별도 작업으로 분리한다.

## 18. 1차 구현 결과

2026-07-07 1차 구현에서 완료한 범위:

- `app/hazop_engine/` 패키지 생성
- `HazopDraftContext`, `HazopDraftResult`, `EngineEvent` 추가
- Deep Agents `create_deep_agent()` 래퍼 추가
- `risk-draft-agent`, `risk-review-agent`, `action-plan-agent` sub-agent 정의
- Deepagent에 파일 읽기/쓰기 권한을 주지 않는 `permissions` 설정 추가
- HAZOP Skill `SKILL.md` 7개 추가
- 사고이력 조회, 표준 HAZOP 조회, 위험도 계산, schema 검증 Tool 추가
- `generate_hazop_draft(context)` workflow 추가
- 기존 `app/services/agent.py`에서 #3/#4 초안 생성 구간을 HAZOP Engine 호출로 연결
- Azure OpenAI/Deepagent 실행 불가 시 demo fallback 유지
- 입력 Excel에 없는 Node/변수/Guideword 생성 금지 테스트 추가
- Deepagent 미설정 시 demo fallback 테스트 추가

1차 구현에서 의도적으로 보류한 범위:

- 실제 사고이력 DB/API 연결
- 실제 표준 HAZOP 문서 검색 인덱스 연결
- Deepagent streaming 이벤트를 SSE에 세밀하게 연결
- Deepagent 재작성 루프의 다단계 상세 trace 저장
- Human-in-the-loop 승인 UI

검증 결과:

```bash
.venv/bin/python -m compileall app scripts tests
.venv/bin/python -c "import app.main; import deepagents; print('app/deepagents import ok')"
.venv/bin/python scripts/create_sample_excels.py
python3 -m pytest
```

결과:

- 컴파일 성공
- 앱 import 성공
- `deepagents 0.6.3` import 성공
- Deepagent factory가 `CompiledStateGraph` 생성 성공
- 샘플 Excel 3개 생성 성공
- 테스트 5개 통과

주의:

- `.venv`에는 `pytest`가 설치되어 있지 않아 테스트는 pytest가 있는 시스템 Python으로 실행했다.
- Deep Agents 설치 과정에서 Google provider 의존성이 `cryptography` wheel을 빌드하므로 최초 설치 시간이 길 수 있다.
