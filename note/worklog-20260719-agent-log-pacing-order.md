# Agent 로그 랜덤 표시 간격 및 Engine 준비 순서 정리

## 문제

- Sub Agent 내부 진행 이벤트가 같은 순간에 Queue에 들어가 화면에 한꺼번에 표시된다.
- 바깥 서비스가 이미 `Deepagent Engine 시작`을 표시하지만 내부 Workflow가 `Engine 준비 완료`를 다시 표시해 중복되고 순서가 어색해 보인다.

## 변경

- 실제 Workflow 실행은 지연하지 않는다.
- SSE Queue에서 사용자 화면으로 Agent 진행 이벤트를 전달할 때만 랜덤 표시 간격을 적용한다.
- 기본 간격은 0.8~2.0초이며 다음 환경변수로 조절할 수 있다.
  - `AGENT_PROGRESS_LOG_MIN_SECONDS`
  - `AGENT_PROGRESS_LOG_MAX_SECONDS`
- `agent_id`가 있고 phase가 `start` 또는 `progress`인 전문 Agent 로그에만 적용한다.
- Workflow 내부의 중복 `Deepagent HAZOP Engine을 준비했습니다` 이벤트를 제거한다.
- Engine 시작 안내는 `app/services/agent.py`에서 Sub Agent 호출 전에 한 번만 표시한다.

## 성공 기준

- `Deepagent Engine 시작` 다음에 `risk-draft-agent Sub Agent 호출`이 표시된다.
- Sub Agent 호출 뒤에 `Deepagent Engine 준비` 블록이 나타나지 않는다.
- Agent 세부 로그가 0.8~2.0초 사이의 불규칙한 간격으로 표시된다.
- Agent 실행과 위험도 계산 결과에는 영향을 주지 않는다.
- 테스트와 Frontend 빌드가 통과한다.
