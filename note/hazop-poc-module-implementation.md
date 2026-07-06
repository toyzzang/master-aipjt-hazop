# HAZOP 생성 PoC 모듈 구현 정리

## 핵심 구현 내용

이번 PoC 단계에서 구현하는 핵심 기능은 사용자가 작성한 기존 HAZOP Excel의 `#1 노드리스트`, `#2 가이드워드` Sheet와 기본정보, MSDS 기준정보, 표준공정위험성평가서 Link를 기반으로 `#3 위험성평가`, `#4 조치계획서` 초안을 생성하는 것입니다.

본 PoC에서 AI Agent는 Node, Guideword, Parameter를 새로 추천하지 않습니다. 사용자가 업로드한 Excel에 이미 작성된 Node와 Guideword/Parameter를 기준으로만 초안을 생성합니다.

### 1.1 에이전트 워크플로우

* **구현 기능:** HAZOP AI 초안생성 요청 처리 워크플로우

* **동작 원리:**

  사용자가 HAZOP 등록화면에서 `[AI 초안생성]` 버튼을 클릭하면 시스템이 입력 창을 표시합니다.

  사용자는 기존 HAZOP 양식 Excel을 업로드하고 Maker/Model, 주요 물질 또는 Node별 물질정보, MSDS 기준정보, 표준공정위험성평가서 Link를 입력합니다.

  시스템은 업로드 Excel과 입력값을 검증한 뒤 `#1 노드리스트`, `#2 가이드워드` Sheet를 파싱합니다. 이후 MSDS 기준정보와 표준공정위험성평가서 문서를 조회하고, AI가 참고할 수 있는 Context를 구성합니다.

  DeepAgent는 구성된 Context를 기반으로 `#3 위험성평가` 초안을 생성합니다. 여기에는 원인, 결과 또는 영향, 현재 안전조치, 조치 전 빈도 후보, 조치 전 강도 후보가 포함됩니다.

  위험도 계산은 AI가 아니라 시스템이 사내 기준표에 따라 수행합니다. 위험도가 기준 이상인 항목만 `#4 조치계획서` 생성 대상으로 선별하고, DeepAgent가 개선조치와 조치 후 빈도/강도 후보를 생성합니다.

  생성 결과는 `request_id` 기준으로 저장되고 화면에 표시됩니다. 사용자는 결과를 검토 및 수정한 뒤 최종 확정합니다.

* **주요 기술:**

| 기술 | 쉽게 말하면 | 이 PoC에서 쓰는 이유 |
|---|---|---|
| FastAPI Service Layer | 사용자가 버튼을 누른 뒤 실행되는 서버 처리 흐름 | 파일 검증, Excel 파싱, 기준정보 조회, 위험도 계산, 저장 같은 정해진 업무 순서를 제어하기 위해 사용 |
| DeepAgent | 여러 참고자료를 보고 긴 판단과 문장 생성을 수행하는 AI 처리 블록 | MSDS, 표준 HAZOP, Node/Guideword 정보를 함께 보고 위험성평가와 조치계획서 초안을 만들기 위해 사용 |
| System Prompting | AI에게 역할과 금지사항을 미리 알려주는 지시문 | AI가 Node/Guideword를 새로 만들지 않도록 제한하고, 근거 부족 시 `확인 필요`로 표시하게 하기 위해 사용 |
| Structured Prompt | AI에게 답변 형식과 작성 기준을 정해주는 프롬프트 | 원인, 결과, 현재 안전조치, 빈도, 강도 등을 정해진 순서와 기준에 맞춰 생성하게 하기 위해 사용 |
| JSON Schema 기반 Structured Output | AI 답변을 문장이 아니라 정해진 JSON 구조로 받는 방식 | 생성 결과를 화면 표시, JSON 저장, Excel 출력에 그대로 쓰기 위해 사용 |
| Pydantic 입력 검증 | 입력값이 정해진 형식에 맞는지 검사하는 Python 도구 | Maker/Model, 물질정보, Sheet 파싱 결과, AI 생성 결과의 필수값 누락을 막기 위해 사용 |
| Python Excel 파싱 | Excel Sheet의 행/열 데이터를 읽어 구조화하는 기능 | `#1 노드리스트`, `#2 가이드워드` Sheet를 AI가 이해할 수 있는 데이터로 바꾸기 위해 사용 |

### 1.2 도구 및 함수 연동

* **구현 기능:** HAZOP 초안 생성을 위한 시스템 Function과 AI Tool 연동

* **동작 원리:**

  PoC에서는 모든 단계를 LLM에게 맡기지 않습니다. 정해진 규칙으로 처리할 수 있는 기능은 일반 시스템 Function으로 구현하고, 판단과 문장 생성이 필요한 구간만 DeepAgent가 담당합니다.

  예를 들어 Excel 업로드, 필수 Sheet 검증, Excel 파싱, MSDS 조회, 표준 HAZOP 문서 조회, 위험도 계산, 저장, 화면 조회, Excel 다운로드는 시스템 Function으로 처리합니다.

  반대로 MSDS/표준 HAZOP 분석, Node/Guideword별 위험성평가 초안 생성, 위험도 기준 이상 항목에 대한 조치계획서 초안 생성은 DeepAgent가 수행합니다.

  LLM이 생성한 결과는 자유문장이 아니라 `#3 위험성평가`, `#4 조치계획서` Row 형태의 JSON 구조로 받습니다. 이렇게 해야 화면 표시, JSON 저장, Excel 템플릿 출력에 동일한 데이터를 사용할 수 있습니다.

* **주요 기술:** FastAPI, Pydantic, Custom Tool Definition, DeepAgent Skill, Structured Output, JSON Schema, Excel Parser, MSDS 조회 API 또는 DB 조회 Function, 표준 HAZOP 문서 조회 Function

| 구분 | Function/Tool | 역할 |
|---|---|---|
| 입력 검증 | `validate_hazop_input` | 파일, Maker/Model, 물질정보, MSDS, 표준 HAZOP Link 필수값 검증 |
| Excel 파싱 | `parse_hazop_excel` | `#1 노드리스트`, `#2 가이드워드` Sheet를 구조화 데이터로 변환 |
| MSDS 조회 | `fetch_msds_context` | 주요 물질 또는 Node별 물질 기준으로 MSDS 정보 조회 |
| 표준 HAZOP 조회 | `fetch_standard_hazop` | 사용자가 지정한 표준공정위험성평가서 Link 기반 문서 조회 |
| Context 구성 | `integrate_reference_context` | Excel, MSDS, 표준 HAZOP 분석 결과를 Node/Guideword 기준으로 통합 |
| 위험성평가 생성 | `generate_risk_assessment` | Node, Guideword, 물질정보, MSDS, 표준 HAZOP 문서를 기준으로 `#3 위험성평가`의 원인, 결과, 현재 안전조치, 빈도/강도 후보 생성 |
| 위험도 계산 | `calculate_risk_score` | 빈도/강도 후보와 기준표를 기반으로 위험도 계산 |
| 조치계획서 생성 | `generate_action_plan` | 위험도 기준 이상 항목에 대해 `#4 조치계획서` 초안 생성 |
| 결과 저장 | `save_hazop_draft` | 생성 결과를 `request_id` 폴더 아래 JSON 파일로 저장하고 DB에는 메타정보 기록 |
| 결과 조회 | `get_generation_result` | 화면 표시용 생성 결과 조회 |
| Excel 출력 | `export_hazop_excel` | 확정된 결과를 기존 HAZOP Excel 템플릿에 맞춰 출력 |

### 1.2.1 `generate_risk_assessment` 상세 생성 기준

`generate_risk_assessment`는 `#3 위험성평가` Sheet 초안을 만드는 기능입니다.

이 기능은 아무 내용이나 새로 상상해서 작성하는 것이 아니라, 사용자가 업로드한 `#1 노드리스트`, `#2 가이드워드`, 물질/MSDS 정보, 표준공정위험성평가서 문서를 근거로 각 항목을 채웁니다.

| 생성 항목 | 참고 데이터 | 생성 방식 | 출력 예시 |
|---|---|---|---|
| Node | `#1 노드리스트` Sheet | 사용자가 입력한 Node를 그대로 사용합니다. AI가 Node를 새로 만들지 않습니다. | Gas Cabinet |
| 검토 범위 | `#1 노드리스트` Sheet, 표준 HAZOP 문서 | Node 설명 또는 유사 표준 HAZOP의 검토 범위를 참고해 작성합니다. 없으면 `확인 필요`로 표시합니다. | 실린더, 압력조절밸브, 긴급차단밸브 |
| 운전 의도 | `#1 노드리스트` Sheet, 사용자가 입력한 공정/Node 설명, 표준 HAZOP 문서 | 해당 Node가 정상상태에서 무엇을 해야 하는지 요약합니다. | Silane/Hydrogen을 안전하게 공급 대기 상태로 유지 |
| Parameter | `#2 가이드워드` Sheet | 사용자가 입력한 Parameter를 그대로 사용합니다. | Containment |
| Guideword | `#2 가이드워드` Sheet | 사용자가 입력한 Guideword를 그대로 사용합니다. | Leak |
| Deviation, 일탈 | Parameter + Guideword 조합, 표준 HAZOP 문서 | Parameter와 Guideword를 조합해 정상 운전의도에서 벗어난 상태를 작성합니다. 표준 HAZOP에 유사 문구가 있으면 우선 참고합니다. | Silane 또는 Hydrogen 누출 |
| Cause, 원인 | 표준 HAZOP 문서, Node 장비 특성, Guideword, 사고/정비/이상발생 이력 | 유사 표준 HAZOP의 원인을 우선 참고하고, 해당 Node에서 현실적으로 발생 가능한 고장/오조작/제어 이상을 작성합니다. 이력 데이터가 있으면 빈번한 원인을 우선 반영합니다. | 실린더 연결부 체결 불량, 밸브 패킹 손상, 피팅 누설 |
| Consequence, 결과 또는 영향 | MSDS 유해성, 물질 위험성, Node 역할, 표준 HAZOP 문서 | 원인이 발생했을 때 사람, 설비, 공정, 환경에 생길 수 있는 영향을 작성합니다. 물질이 유해/가연/폭발성이면 MSDS 위험성을 반영합니다. | 가연성 분위기 형성, 화재, 작업자 대피, 설비 손상 |
| Existing Safeguard, 현재 안전조치 | 표준 HAZOP 문서, P&ID, 알람/인터록 정보, 설비 안전장치, 운전/점검 절차, MSDS 취급 기준 | 이미 설치되어 있거나 운영 중인 감지, 차단, 알람, 인터록, 점검, 보호구, 배기/스크러버 등의 안전조치를 작성합니다. 실제 설비 정보가 없으면 `확인 필요`로 표시합니다. | Gas Detector, 긴급차단밸브, Cabinet 배기 |
| 조치 전 빈도 후보 | 사고이력, 정비이력, 이상발생이력, 알람이력, 표준 HAZOP 빈도, Guideword 특성 | 실제 이력 데이터가 있으면 우선 사용합니다. 이력이 없으면 표준 HAZOP 유사사례와 사내 빈도 기준표를 참고해 후보값을 제안합니다. 최종 확정은 사용자가 합니다. | 3 |
| 조치 전 강도 후보 | MSDS 유해성, 물질 위험성, Node 역할, 영향 범위, 표준 HAZOP 강도 | 물질의 독성/가연성/폭발성, 노출 가능성, 설비 영향, 작업자 영향 등을 보고 사내 강도 기준표에 맞는 후보값을 제안합니다. 최종 확정은 사용자가 합니다. | 5 |
| 조치 전 위험도 | 조치 전 빈도 후보, 조치 전 강도 후보, 사내 위험도 기준표 | AI가 계산하지 않고 시스템 Function이 기준표에 따라 계산합니다. | 15 |
| 위험도 판단 | 조치 전 위험도, 사내 위험도 등급 기준 | 시스템이 낮음/중간/높음 등 등급을 산정합니다. | 높음 |
| 조치 필요 여부 | 위험도 판단, 사내 조치 필요 기준 | 위험도가 기준 이상이면 `필요`, 기준 미만이면 `불필요`로 표시합니다. | 필요 |
| 비고 | 근거 부족 여부, 사용자 입력 비고, 참고문서 출처 | 참고 근거가 부족하거나 현업 확인이 필요한 내용은 `확인 필요`로 표시합니다. | 담당자 확인 필요 |

정리하면 `#3 위험성평가`는 아래 순서로 생성합니다.

1. `#1 노드리스트`에서 평가 대상 Node를 가져옵니다.
2. `#2 가이드워드`에서 해당 Node에 적용할 Parameter/Guideword를 가져옵니다.
3. Parameter와 Guideword 조합으로 일탈을 정의합니다.
4. 표준 HAZOP 문서에서 유사한 Node/Guideword 사례가 있으면 원인, 결과, 현재 안전조치를 우선 참고합니다.
5. MSDS에서 물질의 유해성, 가연성, 폭발성, 취급주의사항을 참고해 결과와 강도 후보를 보강합니다.
6. 사고이력, 정비이력, 이상발생이력, 알람이력이 있으면 빈도 후보 산정에 반영합니다.
7. AI가 빈도/강도 후보와 근거를 제안합니다.
8. 시스템이 사내 기준표로 위험도를 계산합니다.
9. 근거가 부족한 항목은 확정하지 않고 `확인 필요`로 표시합니다.

### 1.2.2 `generate_action_plan` 상세 생성 기준

`generate_action_plan`은 `#3 위험성평가`에서 위험도가 기준 이상으로 나온 항목만 대상으로 `#4 조치계획서` 초안을 만드는 기능입니다.

| 생성 항목 | 참고 데이터 | 생성 방식 |
|---|---|---|
| 개선조치 | 위험 시나리오, 현재 안전조치, 표준 HAZOP 개선조치, MSDS 취급/대응 기준, 알람/인터록/P&ID 정보 | 현재 안전조치로 부족한 부분을 보완하는 추가 조치를 작성합니다. 예: 알람 설정 강화, 인터록 검증, 점검 주기 단축, 누설 확인 절차 강화 |
| 조치 후 빈도 후보 | 개선조치 내용, 기존 빈도 후보, 사내 빈도 기준표 | 개선조치가 발생 가능성을 낮추는 조치라면 빈도 후보를 낮춰 제안합니다. 단, 실제 감소 여부는 사용자 검토가 필요합니다. |
| 조치 후 강도 후보 | 개선조치 내용, 기존 강도 후보, MSDS 위험성, 사내 강도 기준표 | 개선조치가 피해 크기를 줄이는 조치인지 판단합니다. 물질 자체의 위험성이 변하지 않으면 강도는 유지될 수 있습니다. |
| 조치 후 위험도 | 조치 후 빈도 후보, 조치 후 강도 후보, 사내 위험도 기준표 | AI가 계산하지 않고 시스템 Function이 기준표에 따라 계산합니다. |
| 비고 | 근거 부족 여부, 사용자 확인 필요 여부 | 실제 설비 적용 가능성 또는 기준 확인이 필요한 경우 `확인 필요`로 표시합니다. |

| 처리 구분 | 내용 |
|---|---|
| 위험 시나리오 생성 | Node와 Guideword를 기준으로 가능한 Deviation, Cause, Consequence를 생성 |
| 초기 빈도 평가 | Node, Guideword, 운전 의도, 사고 이력, 정비 이력, 이상발생 이력, 알람 이력 등을 참고해 빈도 후보값 제안 |
| 초기 강도 평가 | Node, Guideword, MSDS, P&ID, 물질 위험성, 장비 특성을 참고해 강도 후보값 제안 |
| 안전조치 구성 | MSDS의 개인보호구/취급 기준, P&ID의 밸브/안전장치, 알람, 인터록, 점검 절차 등을 참고해 현재 안전조치 작성 |
| 조치 후 위험도 예측 | 기존 빈도/강도 평가 기준과 동일한 기준으로 조치 후 빈도, 강도 후보를 제안하고 시스템이 위험도 재계산 |
| 표준 양식 반영 | 사내 표준 공정위험성평가 문서 양식에 맞춰 `#3 위험성평가`, `#4 조치계획서` Row로 정리 |
| SHE DB 저장 | 최종 결과를 보고서 문장이 아니라 DB Insert 또는 JSON 저장 가능한 구조화 데이터로 변환 |

### 1.3 데이터 및 메모리

* **구현 기능:** 지정 문서 Context 방식의 RAG와 요청 단위 작업 데이터 관리

* **동작 원리:**

  1차 PoC에서는 Vector DB나 임베딩 기반 자동 유사문서 검색을 필수로 사용하지 않습니다.

  사용자가 표준공정위험성평가서 Link를 직접 지정하므로, 시스템은 해당 문서와 MSDS 기준정보를 조회한 뒤 DeepAgent에게 Context로 전달합니다. 이 방식은 사용자가 참조 문서를 지정하고, 시스템이 그 문서를 읽어 AI 입력으로 넣어주는 방식입니다.

  본 Agent는 대화형 챗봇이 아니므로 사용자와 AI 간 멀티턴 Conversation History를 유지하지 않습니다.

  대신 `request_id` 기준으로 요청을 관리합니다. DB에는 요청 메타정보만 저장하고, Excel 파싱 결과, MSDS 분석 결과, 표준 HAZOP 분석 결과, 통합 Context, AI 생성 결과, 사용자 수정값은 `request_id` 폴더 아래 JSON 파일로 저장합니다.

  화면 표시용 최종 생성 결과는 DB에 저장된 JSON 파일 위치를 기준으로 읽거나, 필요 시 DB 메타정보와 JSON 파일을 함께 조회하여 구성합니다.

* **주요 기술:** 지정 문서 Context 방식, JSON 파일 저장, request_id 기반 작업 디렉터리, DB 메타정보 테이블, Structured Output, LangSmith 또는 Langfuse 모니터링

| 데이터 구분 | 저장 위치 | 예시 |
|---|---|---|
| 요청 메타정보 | DB | `request_id`, 업로드 파일 ID, Maker, Model, 물질정보, 표준 HAZOP Link, 실행 상태, JSON 저장 위치 |
| 입력 원본 파일 | 파일 저장소 | 사용자가 업로드한 HAZOP Excel |
| Excel 파싱 결과 | `request_id` 폴더 아래 JSON | `nodes.json`, `guidewords.json` |
| 참고자료 분석 결과 | `request_id` 폴더 아래 JSON | `msds_analysis.json`, `standard_hazop_analysis.json` |
| 통합 Context | `request_id` 폴더 아래 JSON | `integrated_context.json` |
| AI 생성 결과 | `request_id` 폴더 아래 JSON | `risk_assessment_rows.json`, `action_plan_rows.json` |
| 사용자 수정값 | `request_id` 폴더 아래 JSON 또는 확정 이력 테이블 | 수정된 위험성평가 Row, 수정된 조치계획서 Row |
| 최종 확정 이력 | DB | 확정자, 확정일시, 다운로드 파일 ID, 이력 상태 |

## 주요 문제 해결 및 기술 리서치

| 이슈 구분 | 문제 상황 및 원인 | 리서치 및 해결 과정 |
|---|---|---|
| 워크플로우 | 전체 프로세스를 모두 LLM에게 맡기면 파일 검증, 위험도 계산, 저장 같은 정형 업무의 통제가 약해질 수 있음 | **리서치:** LangGraph, DeepAgent, 일반 FastAPI Service 흐름의 역할 구분 검토. **적용:** 1차 PoC는 FastAPI가 전체 순서를 제어하고, DeepAgent는 입력자료 분석과 `#3/#4` 초안 생성 블록만 담당하도록 설계 |
| 프롬프트 | AI가 Node, Guideword, Parameter를 임의로 추가 추천할 가능성이 있음 | **리서치:** System Prompt 제한 규칙과 Structured Prompt 방식 검토. **적용:** 시스템 프롬프트에 "노드, 가이드워드, 파라미터를 새로 생성하거나 추천하지 않는다"는 제약을 명시 |
| 생성 품질 | MSDS, 표준 HAZOP, Excel 입력자료가 서로 다른 형식이라 AI가 근거 없이 내용을 섞어 쓸 가능성이 있음 | **리서치:** 참고자료를 자료별로 분석한 뒤 Node/Guideword 기준으로 통합하는 Context 구성 방식 검토. **적용:** Excel 분석, MSDS 분석, 표준 HAZOP 분석, 통합 Context 구성을 별도 단계로 분리 |
| 위험도 계산 | 빈도/강도를 AI가 문장으로만 제안하면 위험도 계산 기준이 흔들릴 수 있음 | **리서치:** 기준표 기반 Rule 계산 방식 검토. **적용:** AI는 빈도/강도 후보와 근거만 제안하고, 위험도 점수와 등급은 시스템 기준표로 계산 |
| RAG/Context | 1차 PoC에서 Vector DB까지 구축하면 인프라 부담이 커짐 | **리서치:** 지정 문서 Context 방식과 임베딩 기반 RAG의 차이 검토. **적용:** 1차 PoC는 사용자가 지정한 표준 HAZOP Link와 MSDS를 직접 Context로 구성하고, 운영 확장 시 Vector DB 도입 검토 |
| 데이터 저장 | 중간 결과를 모두 DB JSON 컬럼에 저장하면 테이블 구조가 비대해지고 PoC 변경에 취약할 수 있음 | **리서치:** request_id 기반 작업 디렉터리와 JSON 파일 저장 방식 검토. **적용:** DB에는 요청 메타정보만 저장하고, 중간결과와 생성 결과는 `request_id` 폴더 아래 JSON 파일로 저장 |
| 출력 형식 | LLM이 자유문장으로 결과를 반환하면 화면 표시, DB 저장, Excel 출력이 어려움 | **리서치:** JSON Schema, Structured Output 방식 검토. **적용:** `#3 위험성평가`, `#4 조치계획서`의 Row 단위 JSON 구조로 결과를 반환하도록 설계 |
| 검증 | AI 생성 결과가 최종 승인 문서처럼 오해될 수 있음 | **리서치:** Human-in-the-loop 승인 구조 검토. **적용:** AI 생성 결과는 담당자 검토용 초안으로만 표시하고, 최종 확정은 사용자가 수행하도록 설계 |

## 핵심 동작 검증

### 검증 시나리오: 위험도가 낮아 추가 조치가 필요 없는 HAZOP 초안 생성

* **입력:**

  - HAZOP Excel: `HAZOP_CleanTech_CT-DIW-100.xlsx`
  - `#1 노드리스트`: DI Water 공급 탱크, 이송 펌프, Wet 장비 공급 배관
  - `#2 가이드워드`: Level/Less, Flow/No, Containment/Leak
  - Maker/Model: CleanTech / CT-DIW-100
  - 주요 물질정보: DI Water
  - 표준공정위험성평가서 Link: 표준 HAZOP-UTILITY-WATER-001
  - MSDS 기준정보: DI Water MSDS

* **에이전트 동작:**

  1. `validate_hazop_input` 호출 → 필수 입력값과 Excel 업로드 여부 검증
  2. `parse_hazop_excel` 호출 → `#1 노드리스트`, `#2 가이드워드` Sheet 파싱
  3. `fetch_msds_context` 호출 → DI Water MSDS 기준정보 조회
  4. `fetch_standard_hazop` 호출 → 표준 HAZOP 문서 조회
  5. `integrate_reference_context` 호출 → Node/Guideword 기준 Context 구성
  6. `generate_risk_assessment` 호출 → `#3 위험성평가` 초안 생성
  7. `calculate_risk_score` 호출 → 기준표 기반 조치 전 위험도 계산
  8. 위험도가 기준 미만인 항목은 `#4 조치계획서` 생성 대상에서 제외
  9. `save_hazop_draft` 호출 → 생성 결과 JSON 저장 및 DB 메타정보 기록
  10. `get_generation_result` 호출 → 화면 표시용 결과 조회

* **최종 결과:**

  `#3 위험성평가` Sheet 초안이 생성됩니다. 모든 항목의 위험도가 사내 기준 미만이면 `#4 조치계획서`는 생성하지 않거나 `현 관리 유지`로 표시합니다.

| Node | Parameter | Guideword | 일탈 | 원인 | 결과 또는 영향 | 현재 안전조치 | 조치 전 강도 | 조치 전 빈도 | 조치 필요 여부 |
|---|---|---|---|---|---|---|---:|---:|---|
| DI Water 공급 탱크 | Level | Less | 탱크 액위 낮음 | 보충수 공급 지연, 액위계 오차 | 일시적 공급 불안정 | 저액위 알람, 운전원 확인 | 2 | 2 | 불필요 |
| DI Water 이송 펌프 | Flow | No | 이송 유량 없음 | 펌프 정지, 전원 이상 | Wet 장비 세정수 공급 중단 | 유량 Low Alarm, 예비 펌프 | 3 | 2 | 불필요 |

### 검증 시나리오: 위험도가 높아 조치계획서까지 생성하는 HAZOP 초안 생성

* **입력:**

  - HAZOP Excel: `HAZOP_ASM_Epsilon3200.xlsx`
  - `#1 노드리스트`: Gas Cabinet, VMB 및 공급 배관, MFC 유량 제어 구간, Purge 및 Scrubber 구간
  - `#2 가이드워드`: Containment/Leak, Flow/Reverse, Flow/More, Purge/No
  - Maker/Model: ASM / Epsilon 3200
  - 주요 물질정보: Silane, Hydrogen, Nitrogen
  - Node별 물질정보: Gas Cabinet은 Silane/Hydrogen, Purge 구간은 Nitrogen
  - 표준공정위험성평가서 Link: 표준 HAZOP-CVD-GAS-001
  - 비고: 최근 1년 Gas Detector Alarm 2회, MFC 유량 편차 1회

* **에이전트 동작:**

  1. `validate_hazop_input` 호출 → Excel, Maker/Model, 물질정보, 표준 HAZOP Link 검증
  2. `parse_hazop_excel` 호출 → Node와 Guideword/Parameter 구조화
  3. `fetch_msds_context` 호출 → Silane, Hydrogen, Nitrogen MSDS 조회
  4. `fetch_standard_hazop` 호출 → 표준 HAZOP-CVD-GAS-001 문서 조회
  5. `generate_risk_assessment` 호출 → `#3 위험성평가` 초안 생성
  6. `calculate_risk_score` 호출 → 조치 전 위험도 계산
  7. 시스템이 위험도 기준 이상 항목 식별
  8. `generate_action_plan` 호출 → 기준 이상 항목에 대해 `#4 조치계획서` 초안 생성
  9. 시스템이 조치 후 빈도/강도 후보를 기준으로 조치 후 위험도 계산
  10. `save_hazop_draft` 호출 → 생성 결과 JSON 저장 및 DB 메타정보 기록
  11. `get_generation_result` 호출 → 화면 표시용 `#3/#4` 결과 조회

* **최종 결과:**

  `#3 위험성평가` Sheet에는 원인, 결과 또는 영향, 현재 안전조치, 조치 전 빈도/강도 후보가 생성됩니다. 위험도 기준 이상 항목에 대해서만 `#4 조치계획서` Sheet 초안이 생성됩니다.

| 위험성평가 No | Node | 위험 시나리오 | 조치 전 위험도 | 개선조치 | 조치 후 빈도 후보 | 조치 후 강도 후보 |
|---:|---|---|---:|---|---:|---:|
| 1 | Gas Cabinet | Silane 또는 Hydrogen 누출 | 15 | Gas Detector 알람 시 긴급차단밸브 자동 차단 로직 검증, 실린더 교체 후 누설 확인 절차 강화 | 1 | 5 |
| 3 | MFC 유량 제어 구간 | Silane 공급 유량 과다 | 15 | High-High Flow Trip 설정 검토, Recipe 변경 이중 승인, MFC 교정 주기 단축 검토 | 1 | 5 |
| 4 | Purge 및 Scrubber 구간 | Purge 미수행 또는 불충분 | 10 | Purge 완료 신호 없이는 공정가스 공급이 불가하도록 인터록 검증 | 1 | 5 |

### 검증 성공 기준

| 검증 항목 | 성공 기준 |
|---|---|
| Excel 검증 | `#1 노드리스트`, `#2 가이드워드` Sheet가 없거나 필수 컬럼이 없으면 오류를 반환 |
| Node/Guideword 사용 | AI가 Node, Guideword, Parameter를 새로 생성하지 않고 업로드 Excel 기준으로만 사용 |
| 위험성평가 생성 | `#3 위험성평가`에 원인, 결과 또는 영향, 현재 안전조치, 빈도/강도 후보가 생성 |
| 위험도 계산 | 위험도는 AI가 임의 확정하지 않고 시스템 기준표로 계산 |
| 조치계획서 생성 | 위험도 기준 이상 항목만 `#4 조치계획서` 생성 대상 |
| 저장 | DB에는 요청 메타정보가 저장되고, 중간결과와 생성 결과는 `request_id` 폴더 아래 JSON 파일로 저장 |
| 화면 표시 | 생성된 `#3/#4` 결과를 화면에서 검토 가능 |
| 최종 확정 | 사용자가 검토 및 수정 후 최종 확정 가능 |
| Excel 출력 | 확정 결과를 기존 HAZOP Excel 템플릿에 맞춰 다운로드 가능 |
