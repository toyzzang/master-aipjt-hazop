# Streamlit Agent 로그 UI 개선 작업 설계

## 배경

Streamlit 화면에서 기본 검정색 상단 헤더가 보여 PoC 화면이 투박하게 보인다.
Node별 물질 정보 영역은 흰 배경 위 흰색 글씨처럼 보여 사용자가 내용을 읽기 어렵다.
Agent 로그는 새 로그가 쌓일 때마다 화면 영역이 계속 늘어나 UX가 불편하다.

사용자는 Claude Code처럼 Agent가 어떤 Sub Agent 역할을 쓰고 어떤 스킬을 쓰는지
화면에서 보기 좋게 알고 싶어 한다.

## 구현 범위

- `app/streamlit_app.py`
  - Streamlit 기본 상단 헤더/툴바를 숨긴다.
  - Node별 물질 입력을 `div` 기반 안내 카드와 진한 텍스트 입력으로 정리한다.
  - 로그 렌더링을 고정 높이 스크롤 카드 타임라인으로 바꾼다.
  - 로그 타입(`system`, `agent`, `skill`, `tool`, `result`, `error`)에 따라 배지와 색을 다르게 보여준다.
- `app/hazop_engine/events.py`
  - Engine 이벤트에 로그 타입을 실을 수 있게 한다.
- `app/hazop_engine/workflow.py`
  - DeepAgent 생성 전후에 Sub Agent 역할과 스킬 사용 계획을 로그로 남긴다.
- `app/services/agent.py`
  - 전체 Agent 흐름에서도 Excel 검증, MSDS 조회, DeepAgent, 위험도 계산, Excel 출력 단계를 타입별 로그로 남긴다.

## 성공 기준

- Streamlit 기본 검정 헤더가 화면 상단에 보이지 않는다.
- Node별 물질 정보가 흰 배경에서도 진한 글씨로 읽힌다.
- Agent 로그 영역은 고정 높이를 유지하고 내부 스크롤로만 이동한다.
- 로그 카드에서 요청/검증/MSDS/DeepAgent/Sub Agent/스킬/위험도 계산/결과 단계를 구분해서 볼 수 있다.
- `python -m compileall app scripts tests`가 통과한다.

## 추가 수정

Streamlit에서 로그 카드 HTML이 화면에 원문으로 노출되는 문제가 확인되었다.
로그 패널은 `st.markdown` 대신 `streamlit.components.v1.html`로 iframe 렌더링한다.

Streamlit 초기 로딩 때 검정 화면이 먼저 보이는 문제는 런타임 CSS가 늦게 적용되기 때문이다.
쉽게 말하면 앱이 옷을 갈아입기 전 기본 검정 옷이 잠깐 보이는 상태다.
이를 줄이기 위해 `.streamlit/config.toml`로 앱 시작 테마 자체를 light로 고정하고,
Docker 이미지에도 해당 설정을 복사한다.

## 추가 수정 2

사용자가 Biings Design System 방향의 더 명확한 제품형 UI를 요청했다.
또한 로그가 너무 빠르게 지나가고, 실행 중 스크롤이 안정적으로 동작하지 않는 문제가 남아 있다.
Node도 단순 입력칸으로만 보여 Excel에서 무엇을 읽었는지 가시적으로 이해하기 어렵다.

- Streamlit 유지 시 단기 조치
  - 로그 iframe 내부에서 최신 로그 위치로 자동 스크롤한다.
  - 로그 표시 간격을 조금 늘려 사용자가 읽을 수 있게 한다.
  - Node 카드 안에 물질 입력과 해당 Node의 변수/Guideword 목록을 함께 보여준다.
- 중장기 권장 조치
  - Biings DS는 CSS/NPM 기반이므로 `Vite + React + TypeScript` 프론트엔드로 분리하는 것이 적합하다.
  - FastAPI는 Excel 업로드, SSE 로그, 결과 다운로드 API를 담당하고 React가 UI를 담당한다.

## 추가 수정 3

스크린샷 기준으로 흰 작업 영역과 회색 배경 사이의 여백이 부족하고,
상단 입력 화면이 2분할이라 정보가 한쪽에 몰려 보인다.
사용자는 상단을 3분할로 나누고, 1/2분할에는 파일 업로드와 입력 정보를,
3분할에는 Agent 로그를 배치하길 요청했다.

- 상단 작업 영역을 `파일 / 입력 정보 / Agent 로그` 3분할로 재구성한다.
- 결과 영역은 세 분할 아래 전체 폭으로 표시한다.
- Node List는 별도 그룹으로 보이게 하고, Excel 업로드 후 1초 동안
  "노드를 불러오는 중입니다." 스피너를 표시한다.
- 로그는 새 항목 추가 시 아래로 강제 스크롤하지 않고 최신 로그를 위에 표시한다.
  쉽게 말하면 화면이 위아래로 튀는 움직임을 없애고, 사용자가 보는 위치를 안정화한다.

## 추가 수정 4

사용자는 Streamlit 제거와 `Vite + React + TypeScript + biings-ds` 전환을 요청했다.
Biings DS는 NPM/CSS 기반 디자인 시스템이므로 React 앱에서 직접 CSS를 import한다.

- `frontend/`에 Vite React TypeScript 앱을 만든다.
- React 빌드 결과를 `app/static/`으로 내보내 FastAPI가 정적 파일로 제공한다.
- Docker는 더 이상 Streamlit을 실행하지 않고 FastAPI/uvicorn을 실행한다.
- 1분할은 파일 업로드, Maker/Model, 유사 HAZOP 문서 ID, 운전 의도, 사고 정비 이력을 담당한다.
- 2분할은 Node List만 담당하며 표 형태로 Node/Guideword/물질 입력을 보여준다.
- 3분할은 Agent 로그만 담당한다.
- 로그는 아래로 쌓되 사용자가 스크롤을 위로 올린 상태면 위치를 유지하고,
  맨 아래에 있을 때만 자동으로 최신 로그를 따라간다.
- Sub Agent 호출은 큰 로그 카드로 표시하고, 그 아래에 Skill/Tool/Result를 자식 로그로 묶는다.

## 추가 수정 5

사용자가 1/2/3분할 높이가 서로 달라 보이고, Node List가 많을 때 전체 화면 레이아웃이 밀리는 문제를 지적했다.
또한 Excel 업로드 전부터 샘플 Node가 표시되어 실제 업로드 결과처럼 오해되는 문제가 있었다.

- 세 패널 높이는 동일하게 고정한다.
- 각 패널의 내용이 많으면 패널 내부에서만 스크롤한다.
- Node List는 Excel 업로드 전에는 빈 안내 상태만 표시한다.
- Node 물질 입력값은 업로드 후 사용자가 key-in하도록 빈칸으로 시작한다.
- Hero/패널/Node/List/로그 글씨 크기를 줄여 PoC 도구 화면처럼 부담을 낮춘다.
- Maker/Model 입력칸은 같은 grid 안에서 label/input 정렬이 맞도록 margin을 보정한다.
- Deepagent fallback은 치명 오류가 아니므로 `Error`가 아니라 `주의` 로그로 표시한다.
  쉽게 말하면 Azure OpenAI가 없어서 앱이 멈춘 것이 아니라, demo 생성기로 계속 진행하는 상태다.

## 추가 수정 6

사용자가 Sub Agent가 3개인데 로그에서는 하나처럼 보인다고 지적했다.
원인은 backend 이벤트가 `risk-draft-agent`, `risk-review-agent`, `action-plan-agent`를 하나의 흐름으로 요약해서 보낸 점이다.

- `risk-draft-agent`, `risk-review-agent`, `action-plan-agent`를 각각 부모 로그로 보낸다.
- 각 부모 로그 아래에 참조 스킬, 시스템 Tool 호출, 생성 결과를 자식 로그로 붙인다.
- Demo 모드에서도 동일하게 3개 Sub Agent 흐름을 표시해 실제 Deepagent 적용 전후 UX 차이를 줄인다.
- Docker Compose 실행 시 루트 `.env`를 읽도록 `env_file: ../../.env`를 추가한다.
- Compose의 `environment`에서 Azure OpenAI 키를 빈 값으로 다시 덮어쓰지 않도록 중복 선언을 제거한다.
- Azure OpenAI 설정이 누락되면 값은 노출하지 않고 비어 있는 환경변수 이름만 로그에 표시한다.
  쉽게 말하면 API Key 자체는 숨기고, 어떤 설정 종이가 컨테이너 안에 안 들어왔는지만 보여준다.

## 추가 수정 7

사용자가 `Deepagent HAZOP Engine을 시작합니다.` 이후 화면이 멈춘 것처럼 보인다고 지적했다.
실제 원인은 Deepagent 호출을 `await`하는 동안 SSE 로그를 추가로 보내지 못하는 구조다.

- Deepagent 초안 생성은 background task로 실행한다.
- task가 끝날 때까지 `AGENT_LLM_HEARTBEAT_SECONDS` 간격으로 "생성 중" 로그를 보낸다.
- 화면의 Agent 로그 헤더에도 실행 중 spinner를 표시한다.
- `#3/#4` 결과 테이블은 카드 내부에서 가로/세로 스크롤되게 한다.
- 긴 셀 내용은 표 영역 안에서 줄바꿈되게 해 결과 영역 밖으로 튀지 않도록 한다.

## 추가 수정 8

사용자가 heartbeat 로그가 같은 내용의 카드로 계속 쌓이는 문제를 지적했다.

- `Deepagent가 초안을 생성 중입니다.` 이벤트는 새 카드를 계속 만들지 않는다.
- 하나의 진행 카드 안에서 detail만 갱신한다.
- 진행 카드 내부에 spinner를 표시한다.
- 다음 실제 단계 로그가 도착하면 진행 카드는 loading 상태를 종료한다.
- 진행 카드의 `경과 확인 #n` 숫자는 UX상 의미가 작으므로 제거한다.

## 추가 수정 9

사용자는 전체 Deepagent 대기 카드 하나보다 Sub Agent별 시간 분배와 진행 상태를 보고 싶어 한다.
기존 구조는 `generate_hazop_draft`가 끝난 뒤 내부 이벤트를 한꺼번에 반환해서,
실제 모델 호출 중에는 Sub Agent 단계가 보이지 않았다.

- `generate_hazop_draft`에 progress callback을 추가해 내부 이벤트를 즉시 SSE로 보낼 수 있게 한다.
- `risk-draft-agent`, `risk-review-agent`, `action-plan-agent` 시작 로그를 먼저 보여준다.
- 모델 응답 대기 heartbeat는 현재 Sub Agent 카드의 자식 로그로 갱신한다.
- 동일한 대기 로그는 새 항목을 계속 추가하지 않고 기존 자식 로그만 업데이트한다.
- 모델 호출 완료 시 `#3`, `#4` 각각의 소요 시간을 로그에 표시한다.
- 로그 카드 UI는 컬러 바가 강한 카드형에서 더 차분한 작업 로그 리스트 스타일로 낮춘다.

## 추가 수정 10

사용자가 모델 응답이 완료되었는데도 대기 child 로그의 spinner가 계속 도는 문제를 지적했다.
쉽게 말하면, "기다리는 중" 표시가 "끝났다"는 다음 로그를 보고도 꺼지지 않는 상태다.

- Sub Agent 자식 로그에 완료/결과 로그가 도착하면 같은 Sub Agent 안의 기존 loading child를 모두 종료한다.
- 상단 입력 영역은 `파일 및 입력`과 `Node List` 2분할로 줄인다.
- Agent 로그는 결과 영역 옆으로 이동한다.
- 하단 영역은 `#3/#4 결과`와 `Agent 로그` 2분할로 구성하되 결과 영역을 더 넓게 둔다.
- 결과가 아직 없고 Agent가 실행 중이면 `#3/#4` 영역에 현재 생성 단계를 spinner와 함께 표시한다.
  예: 원인/결과 분석, 빈도/강도 근거 정리, 안전조치/조치계획서 작성.

## 추가 수정 11

사용자가 `#3 위험성평가`, `#4 조치계획서` 결과 테이블의 컬럼 헤더를 한국어로 표시하길 요청했다.
또한 `no`, `node_order`처럼 숫자만 들어가는 컬럼은 넓은 폭을 차지하지 않도록 줄이길 요청했다.

- 백엔드/Excel 데이터 키는 그대로 유지하고, React 표에서 보이는 헤더만 한국어 라벨로 변환한다.
- `no`, `node_order`, `frequency`, `severity`, `risk_score` 같은 숫자 컬럼은 `numeric-column` 스타일을 적용해 폭을 작게 잡는다.
