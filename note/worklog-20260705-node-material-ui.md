# Node별 물질정보 UI 개선 작업 설계

## 배경

현재 웹 화면은 `Node별 물질정보`를 하나의 큰 textarea로 입력받는다.
사용자는 Excel 업로드 후 Excel의 `#1 노드리스트`에 들어있는 Node 개수만큼 UI 입력칸이 생기고,
각 Node별로 물질정보를 따로 입력할 수 있기를 원한다.

쉽게 말하면, 사용자가 Node 이름을 다시 손으로 적지 않아도 되게 만드는 작업이다.

## 구현 범위

- FastAPI에 업로드 Excel의 `#1 노드리스트`만 미리 읽는 API를 추가한다.
- 웹 UI에서 Excel 파일 선택 시 해당 API를 호출해 Node 목록을 표시한다.
- Node별 물질 입력칸 값을 기존 `node_materials` 문자열 형식으로 합쳐 Agent에 전달한다.
- Streamlit UI도 업로드된 Excel에서 Node 목록을 읽어 Node별 입력칸을 표시하도록 맞춘다.

## 가정

- Node 목록 기준은 기존 원칙대로 Excel의 `#1 노드리스트`만 사용한다.
- Agent 내부 입력 형식은 기존 `node_materials` 문자열을 유지한다.
  - 예: `DI Water 공급 탱크: DI Water`
- 사용자가 Excel을 선택하기 전에는 기존 예시 입력을 표시한다.

## 성공 기준

- Excel 선택 후 웹 화면에 Excel Node 개수만큼 Node별 물질정보 입력칸이 생긴다.
- 각 입력칸의 Node 이름은 Excel에서 읽은 값으로 표시된다.
- 제출 시 Node별 입력값이 기존 Agent 입력인 `node_materials`로 전달된다.
- 기존 Excel 검증/Agent 실행 규칙은 바뀌지 않는다.
- `python -m compileall app scripts tests`가 통과한다.
