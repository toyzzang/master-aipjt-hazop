# HAZOP 생성 PoC Agent LLM 명세서

## 1. Agent 페르소나 및 시스템 프롬프트

Agent의 정체성, 역할, 답변 톤앤매너를 정의합니다. 실제 LLM의 System Prompt에 들어갈 핵심 내용입니다.

| 항목 | 정의 내용 |
|---|---|
| **Agent 이름** | HAZOP 초안 생성 Agent |
| **주요 역할** | 사용자가 업로드한 HAZOP Excel의 `#1 노드리스트`, `#2 가이드워드` Sheet와 Maker/Model, 물질/MSDS 정보, 표준공정위험성평가서 Link를 기반으로 `#3 위험성평가`, `#4 조치계획서` 초안을 생성합니다. |
| **핵심 목표** | 원인, 결과 또는 영향, 현재 안전조치, 빈도/강도 후보, 개선조치 초안을 작성하여 HAZOP 작성 시간을 줄이고, 사용자가 검토 가능한 형태로 결과를 제공합니다. |
| **톤앤매너** | 안전 실무 문서에 맞게 간결하고 명확하게 작성합니다. 단정이 어려운 내용은 `확인 필요`로 표시합니다. 추측성 표현을 피하고, 가능한 경우 MSDS/표준 HAZOP 근거를 함께 제시합니다. |
| **제약 사항** | 노드, 가이드워드, 파라미터를 새로 생성하거나 추천하지 않습니다. 사용자가 제공한 `#1 노드리스트`, `#2 가이드워드` 기준으로만 작성합니다. HAZOP 최종 승인, 빈도/강도 최종 확정, 위험도 최종 확정, 안전조치 최종 결정은 수행하지 않습니다. 근거 없는 내용을 사실처럼 작성하지 않습니다. |

### System Prompt 핵심 문구

```text
너는 HAZOP 초안 생성 Agent이다.

너의 역할은 사용자가 제공한 HAZOP Excel의 #1 노드리스트, #2 가이드워드 Sheet와 Maker/Model, 물질/MSDS 정보, 표준공정위험성평가서 참고 문서를 기반으로 #3 위험성평가와 #4 조치계획서 초안을 작성하는 것이다.

너는 노드, 가이드워드, 파라미터를 새로 생성하거나 추천하지 않는다.
노드와 가이드워드는 사용자가 제공한 입력값을 기준으로만 사용한다.

너는 원인, 결과 또는 영향, 현재 안전조치, 빈도 후보, 강도 후보, 개선조치, 조치 후 빈도/강도 후보를 작성할 수 있다.

근거가 부족한 항목은 임의로 확정하지 말고 `확인 필요`로 표시한다.
빈도와 강도는 최종 확정값이 아니라 후보값으로 제안한다.
위험도 계산은 시스템 기준표 또는 계산 로직이 수행한다.
최종 승인과 확정은 반드시 사용자가 수행한다.
```

## 2. 워크플로우 및 오케스트레이션

사용자 입력부터 최종 응답까지 Agent의 사고 과정과 행동 순서를 정의합니다.

1차 PoC에서는 **FastAPI 기반 서비스 흐름 + DeepAgent 생성 블록** 구조로 설계합니다.

전체 업무 흐름은 FastAPI의 Service Layer가 순차적으로 제어합니다.

DeepAgent는 전체 업무를 모두 수행하는 것이 아니라, 생각이 길고 문장 생성이 많으며 여러 자료를 참고해야 하는 LLM 생성 블록만 담당합니다. 본 PoC에서는 `입력자료 분석`, `#3 위험성평가` 초안 생성, `#4 조치계획서` 초안 생성 구간이 이에 해당합니다.

파일 업로드, 검증, Excel 파싱, 기준정보 조회, 위험도 계산, 요청 메타정보 저장, 화면 표시, 문서 다운로드는 일반 Python/FastAPI 로직으로 처리합니다.

LangGraph는 1차 PoC 필수 요소로 보지 않습니다. 향후 분기/재시도/장시간 Job 상태관리/다중 Agent 오케스트레이션이 필요해질 때 도입을 검토합니다.

### 2.1 처리 로직

**Step 1. Input Analysis**

사용자 입력과 업로드 파일을 분석합니다.

- HAZOP Excel에 `#1 노드리스트`, `#2 가이드워드` Sheet가 있는지 확인합니다.
- Maker/Model, 주요 물질, MSDS 기준정보, 표준 HAZOP Link가 있는지 확인합니다.
- Node별 물질 정보가 필요한지 확인합니다.
- AI 생성 대상이 `#3 위험성평가`, `#4 조치계획서`인지 확인합니다.

**Step 2. Tool Selection**

도구 선택 기준은 아래와 같습니다.

| 조건 | 선택 도구/Skill |
|---|---|
| Excel 파일 업로드 | Excel 파싱 도구 |
| MSDS 기준정보 필요 | MSDS 조회 도구 |
| 표준 HAZOP Link 제공 | 표준 HAZOP 문서 조회 도구 |
| Excel 자료 분석 필요 | Excel 입력 분석 Skill |
| MSDS 분석 필요 | MSDS 분석 Skill |
| 표준 HAZOP 분석 필요 | 표준 HAZOP 분석 Skill |
| 분석 결과 통합 필요 | 참고자료 통합 Skill |
| `#3 위험성평가` 생성 | 위험성평가 초안 생성 Skill |
| 위험도 계산 필요 | 위험도 계산 Function |
| `#4 조치계획서` 생성 | 조치계획서 초안 생성 Skill |
| 결과 저장 필요 | 생성 결과 저장 Function |
| Excel 산출물 필요 | Excel 템플릿 출력 Function |

**Step 3. Execution & Response**

1. 요청을 접수합니다. `FastAPI`
2. 업로드 파일과 입력값을 검증합니다. `FastAPI/System Function`
3. Excel을 파싱하여 `#1 노드리스트`, `#2 가이드워드`를 구조화합니다. `FastAPI/System Function`
4. MSDS, 표준 HAZOP 문서, 기준표 등 기준정보를 조회합니다. `FastAPI/System Function`
5. AI 생성을 위한 입력 Context를 준비합니다. `FastAPI/System Function + 분석 Skill`
6. `#3 위험성평가` 초안을 생성합니다. `DeepAgent`
7. 기준표 기반 위험도를 계산합니다. `FastAPI/System Function`
8. 위험도 기준 이상 항목에 대해 `#4 조치계획서` 초안을 생성합니다. `DeepAgent`
9. 생성 결과의 필수값, 형식, 근거 부족 여부를 검증합니다. `FastAPI/System Function + 검토 Skill`
10. 사용자 검토 대기 상태로 전환합니다. `FastAPI`
11. 사용자 확정 후 요청 상태와 이력을 저장합니다. `FastAPI/System Function`
12. 확정 결과를 지정 Excel 템플릿에 맞춰 다운로드 파일로 생성합니다. `FastAPI/System Function`

### 2.1.1 HAZOP 전체 Workflow 담당 구분

| 단계 | 수행 | 담당 |
|---|---|---|
| 1 | 요청 접수 | FastAPI |
| 2 | 파일 검증 | FastAPI/System Function |
| 3 | Excel 파싱 | FastAPI/System Function |
| 4 | 기준정보 조회 | FastAPI/System Function |
| 5 | AI 생성 준비 | FastAPI/System Function + 분석 Skill |
| 6 | DeepAgent로 위험성평가 초안 생성 | DeepAgent |
| 7 | 위험도 계산 | FastAPI/System Function |
| 8 | DeepAgent로 조치계획서 초안 생성 | DeepAgent |
| 9 | 결과 검증 | FastAPI/System Function + 검토 Skill |
| 10 | 사용자 검토 대기 | FastAPI |
| 11 | 요청 상태 및 생성 결과 저장 | FastAPI/System Function |
| 12 | 문서 다운로드 | FastAPI/System Function |

### 2.2 상태 관리

| 상태 | 설명 |
|---|---|
| INIT | AI 초안생성 요청 시작 |
| FILE_UPLOADED | Excel 업로드 완료 |
| INPUT_VALIDATED | 입력값 및 Sheet 검증 완료 |
| EXCEL_PARSED | `#1 노드리스트`, `#2 가이드워드` 파싱 완료 |
| REFERENCE_LOADED | MSDS 및 표준 HAZOP 문서 조회 완료 |
| REFERENCES_ANALYZED | Excel/MSDS/표준 HAZOP 자료별 분석 완료 |
| CONTEXT_READY | 자료별 분석 결과를 Node/Guideword 단위로 통합 완료 |
| RISK_DRAFT_CREATED | `#3 위험성평가` 초안 생성 완료 |
| RISK_CALCULATED | 위험도 계산 완료 |
| ACTION_PLAN_CREATED | `#4 조치계획서` 초안 생성 완료 |
| SAVED | 생성 결과 저장 완료 |
| REVIEWING | 사용자 검토 중 |
| CONFIRMED | 최종 확정 |
| EXPORTED | 확정 결과 Excel 템플릿 출력 완료 |
| FAILED | 오류 발생 |

### 2.3 FastAPI Service 흐름

```python
create_hazop_ai_draft(request):
    validate_hazop_input(request)
    parsed_excel = parse_hazop_excel(request.file_id)
    msds_context = fetch_msds_context(request.material_info)
    standard_hazop = fetch_standard_hazop(request.standard_hazop_link)

    integrated_context = prepare_generation_context(
        parsed_excel,
        msds_context,
        standard_hazop,
    )

    risk_rows = deepagent_generate_risk_assessment(integrated_context)
    risk_rows = calculate_risk_scores(risk_rows)
    action_rows = deepagent_generate_action_plan(risk_rows, integrated_context)

    validate_generation_result(risk_rows, action_rows)
    save_hazop_draft(risk_rows, action_rows)
    return get_generation_result()
```

예외 흐름:

```text
입력값 검증 실패 -> 사용자에게 누락/오류 항목 반환
Excel 파싱 실패 -> Sheet/컬럼 오류 반환
MSDS/표준 HAZOP 일부 조회 실패 -> 경고 표시 후 가능한 범위에서 생성
DeepAgent 생성 실패 -> 재시도 또는 생성 실패 반환
저장 실패 -> 생성 결과 보존 후 저장 실패 안내
```

### 2.4 LangGraph 도입 검토 시점

1차 PoC에서는 FastAPI Service 흐름으로 충분합니다.

다만 아래 조건이 생기면 LangGraph 도입을 검토합니다.

| 도입 조건 | 이유 |
|---|---|
| 생성 Job이 장시간 실행됨 | 상태 저장, 재시작, 중단 복구가 필요 |
| 단계별 재시도/분기가 많아짐 | 그래프 기반 분기 관리가 유리 |
| 여러 Agent가 협업함 | Agent 간 상태 전달과 조율 필요 |
| 사용자 중간 승인 후 이어서 실행함 | Human-in-the-loop 상태 관리 필요 |
| Workflow 관찰성과 디버깅이 중요해짐 | 노드 단위 추적이 유리 |

## 3. 도구 및 함수 명세

Agent가 외부 시스템과 상호작용하기 위해 사용할 도구와 시스템 Function을 정의합니다.

| 도구명 | 기능 설명 | 입력 파라미터 | 출력 데이터 |
|---|---|---|---|
| `validate_hazop_input` | AI 초안생성 요청값과 필수 입력값을 검증합니다. | `file_id: string`, `maker: string`, `model: string`, `material_info: object`, `msds_ids: array`, `standard_hazop_link: string` | `validation_result: object` |
| `parse_hazop_excel` | 업로드된 Excel에서 `#1 노드리스트`, `#2 가이드워드` Sheet를 파싱합니다. | `file_id: string`, `sheet_names: array` | `nodes: array`, `guidewords: array`, `parse_warnings: array` |
| `fetch_msds_context` | 주요 물질 또는 Node별 물질 기준으로 MSDS 정보를 조회합니다. | `material_ids: array`, `node_material_map: object` | `msds_context: array` |
| `fetch_standard_hazop` | 사용자가 지정한 표준공정위험성평가서 Link의 문서 정보를 조회합니다. | `standard_hazop_link: string` | `standard_hazop_context: object` |
| `analyze_excel_input` | 노드리스트와 가이드워드 Sheet를 Node/Guideword 작업 단위로 분석합니다. | `nodes: array`, `guidewords: array` | `excel_analysis: object` |
| `analyze_msds_context` | MSDS에서 강도 판단과 안전조치 작성에 필요한 정보를 추출합니다. | `msds_context: array` | `msds_analysis: object` |
| `analyze_standard_hazop` | 표준 HAZOP 문서에서 참고 가능한 원인/결과/현재 안전조치/개선조치 후보를 추출합니다. | `standard_hazop_context: object` | `standard_hazop_analysis: object` |
| `integrate_reference_context` | Excel/MSDS/표준 HAZOP 분석 결과를 Node/Guideword 기준으로 통합합니다. | `excel_analysis: object`, `msds_analysis: object`, `standard_hazop_analysis: object` | `integrated_context: object` |
| `generate_risk_assessment` | `#3 위험성평가` 초안을 생성합니다. | `integrated_context: object` | `risk_assessment_rows: array` |
| `calculate_risk_score` | 빈도/강도 후보와 기준표를 기반으로 위험도를 계산합니다. | `frequency: number`, `severity: number`, `risk_matrix_id: string` | `risk_score: number`, `risk_level: string`, `action_required: boolean` |
| `generate_action_plan` | 위험도 기준 이상 항목에 대해 `#4 조치계획서` 초안을 생성합니다. | `risk_assessment_rows: array`, `msds_context: array`, `standard_hazop_context: object` | `action_plan_rows: array` |
| `save_hazop_draft` | 생성된 위험성평가/조치계획서 결과를 `request_id` 폴더 아래 JSON 파일로 저장하고, DB에는 요청 메타정보와 저장 위치를 기록합니다. | `request_id: string`, `risk_assessment_rows: array`, `action_plan_rows: array` | `save_result: object` |
| `get_generation_result` | 생성 결과 화면 표시용 데이터를 DB 메타정보 또는 `request_id` 기준 JSON 파일에서 조회합니다. | `request_id: string` | `display_rows: object` |
| `export_hazop_excel` | 확정된 `#3 위험성평가`, `#4 조치계획서` 데이터를 특정 Excel 템플릿에 맞춰 출력합니다. | `request_id: string`, `template_id: string` | `file_id: string`, `download_url: string` |

## 4. 지식 베이스 및 작업 데이터 관리 전략

LLM이 참조해야 할 Context와, 초안 생성 요청 중 발생하는 작업 데이터를 어떻게 관리할지 정의합니다.

### 4.1 RAG 전략

| 항목 | 정의 내용 |
|---|---|
| **참조 데이터 소스** | 업로드 Excel, MSDS 기준정보, 사용자가 지정한 표준공정위험성평가서 문서, 빈도/강도 기준표, 위험도 매트릭스 |
| **청킹 방식** | Sheet/표 기준 청킹. HAZOP 문서는 Node 단위 또는 위험성평가 Row 단위로 분리. MSDS는 유해성, 취급/저장, 누출대응, 화재대응, 응급조치 섹션 단위로 분리 |
| **임베딩 모델** | 1차 PoC에서는 필수 아님. 사용자가 지정한 표준 HAZOP 문서와 MSDS를 직접 Context로 넣는 방식으로 수행 |
| **Vector DB** | 1차 PoC에서는 필수 아님. 운영 확장 시 유사 표준 HAZOP 자동 검색이 필요해지면 pgvector, OpenSearch Vector, Milvus 등을 검토 |

### 4.1.1 RAG와 Vector DB 관계

RAG는 "검색하거나 조회한 자료를 LLM에게 넣어 답변 품질을 높이는 방식"입니다.

Vector DB는 RAG를 구현하는 방법 중 하나일 뿐입니다. 따라서 RAG를 쓴다고 해서 반드시 Vector DB가 필요한 것은 아닙니다.

| 방식 | 설명 | Vector DB 필요 여부 |
|---|---|---|
| 지정 문서 Context 방식 | 사용자가 지정한 표준 HAZOP Link와 MSDS를 조회해 LLM에 전달 | 불필요 |
| 키워드/필터 검색 방식 | Maker, 물질, Node, Guideword 같은 컬럼/키워드로 관련 자료 조회 | 불필요 |
| 임베딩 기반 의미 검색 | 표현이 달라도 의미가 비슷한 문서를 찾음 | 보통 필요 |

1차 PoC는 사용자가 표준 HAZOP 문서를 지정하므로 `지정 문서 Context 방식`으로 충분합니다.

운영 단계에서 사용자가 문서를 지정하지 않아도 수많은 표준 HAZOP 중 유사 문서를 자동으로 찾아야 한다면, 그때 임베딩 모델과 Vector DB 도입을 검토합니다.

### 4.2 Context, 메모리, 데이터 구분

| 구분 | 의미 | 예시 | 관리 방식 |
|---|---|---|---|
| Context | LLM이 분석/생성을 위해 입력으로 받는 참고자료 묶음 | Excel 파싱 결과, MSDS 요약, 표준 HAZOP 참고 Row, 기준표 | 생성 시점에 구성하고, 필요 시 `request_id` 폴더 아래 JSON 파일로 저장 |
| 중간 분석 데이터 | AI 또는 시스템이 Context를 분석해서 만든 중간 결과 | MSDS 분석 결과, 표준 HAZOP 분석 결과, Node별 통합 근거 | `request_id` 폴더 아래 JSON 파일 저장 |
| 최종 생성 데이터 | 사용자가 화면에서 검토할 AI 생성 결과 | `#3 위험성평가` Row, `#4 조치계획서` Row | `request_id` 폴더 아래 JSON 파일 저장. 화면은 DB 메타정보 또는 JSON 파일에서 조회 |
| 실행 상태 | 현재 요청이 어느 단계인지 나타내는 상태값 | EXCEL_PARSED, RISK_DRAFT_CREATED, SAVED, FAILED | request_id 기준 DB 메타정보로 저장 |
| 대화 메모리 | 사용자와 AI가 여러 턴에 걸쳐 대화한 맥락 | 해당 없음 | 본 Agent는 버튼 기반 AI 초안생성 기능이므로 멀티턴 대화 메모리를 유지하지 않음 |

여기서 말하는 메모리는 서버 RAM에 모든 데이터를 들고 있다는 뜻이 아닙니다.

본 Agent는 대화형 챗봇이 아니라 버튼 기반 AI 초안생성 기능이므로, 사용자와 AI 간 멀티턴 대화 메모리를 유지하지 않습니다.

1차 PoC에서는 DB에 요청 메타정보만 저장하고, 중간결과와 생성 결과는 `request_id` 폴더 아래 JSON 파일로 저장합니다. DeepAgent 호출 시에는 해당 요청의 입력값, 파싱 결과, 참고문서 분석 결과를 다시 읽어 Context를 구성해서 전달합니다.

### 4.3 요청 단위 작업 데이터 관리

| 항목 | 정의 내용 |
|---|---|
| **관리 단위** | AI 초안생성 요청 1건. 예: `request_id` |
| **저장 위치** | DB에는 요청 메타정보만 저장하고, 중간결과는 `request_id` 폴더 아래 JSON 파일로 저장합니다. |
| **저장 대상** | DB: `request_id`, 업로드 파일 ID, Maker/Model, 물질/MSDS 선택값, 표준 HAZOP Link, 실행 상태, JSON 저장 위치. JSON: Excel 파싱 결과, 자료 분석 결과, 통합 Context, AI 생성 결과, 사용자 수정값 |
| **저장 형식** | DB는 요청 추적과 화면 조회를 위한 메타정보 중심으로 저장합니다. 중간 산출물과 생성 결과는 JSON 파일로 저장합니다. |
| **초기화 기준** | 사용자가 새 Excel을 업로드하거나 AI 초안생성을 다시 시작하면 새 `request_id`를 생성합니다. |
| **보관 전략** | 최종 확정 전에는 Draft 데이터로 관리하고, 최종 확정 후에는 확정 결과와 생성/수정 이력으로 보관합니다. |

## 5. 핵심 에이전트 기술 스택

일반적인 웹 개발 스택이 아니라, LLM의 답변 품질과 구조를 제어하기 위한 기술적 의사결정입니다.

| 구분 | 선정 전략/기술 | 선정 사유 |
|---|---|---|
| **LLM Model** | GPT-4.1 계열 또는 동급 이상의 한국어/문서추론 성능 모델 | HAZOP 문서, MSDS, 표준공정위험성평가서처럼 긴 한국어 업무 문서를 이해하고 구조화된 초안을 생성해야 하기 때문 |
| **Agent Framework** | 1차 PoC는 FastAPI Service + DeepAgent, 고도화 시 LangGraph 검토 | 현재 흐름은 대부분 일반 시스템 로직이며, LLM이 필요한 구간은 입력자료 분석과 `#3/#4` 초안 생성 블록에 한정되기 때문. LangGraph는 분기/재시도/장시간 상태관리가 필요해질 때 도입 |
| **Prompt Strategy** | ReAct + Structured Prompt + 제한 규칙 | 도구 호출과 중간 판단이 필요하며, 노드/가이드워드 신규 생성 금지 같은 업무 제약을 강하게 유지해야 하기 때문 |
| **Output Parsing** | Structured Output / JSON Schema | `#3 위험성평가`, `#4 조치계획서`를 화면 표시, JSON 저장, Excel 출력에 사용할 수 있는 정형 Row 데이터로 받아야 하기 때문 |
| **Monitoring** | LangSmith 또는 Langfuse | 프롬프트 버전, 입력 문서, 생성 결과, 오류, 토큰 사용량, 사용자 수정률 추적이 필요하기 때문 |
| **Guardrail** | 금지 규칙 + 확인 필요 플래그 + Human-in-the-loop | 안전 문서이므로 근거 없는 확정, 최종 승인 표현, 빈도/강도 확정 표현을 방지해야 하기 때문 |
| **Excel Export** | 템플릿 기반 Excel 생성 Function | 최종 확정된 `#3 위험성평가`, `#4 조치계획서`를 사용자가 요구하는 기존 양식으로 다운로드해야 하기 때문 |
