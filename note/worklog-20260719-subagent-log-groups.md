# Sub-agent 로그 그룹 및 중복 대기 로그 개선

## 요청

- `모델 응답 대기 중입니다` 로그가 반복해서 쌓이지 않게 한다.
- 위험성 초안, 독립 검토, 조치계획 Agent별로 부모 블록을 만든다.
- 각 Agent가 실행 중일 때 해당 부모 블록의 스피너를 표시한다.
- Skill 읽기, Tool 호출, 검토 결과 등은 해당 Agent 블록 안에 계속 추가한다.

## 원인

1. `app/services/agent.py`가 LLM 응답을 기다리는 동안 일정 주기마다 동일한 화면 로그를 생성했다.
2. 기존 Frontend는 `Sub Agent`라는 제목 문자열을 기준으로만 부모 블록을 만들었다.
3. 새 Workflow 이벤트에는 로그가 어느 Agent 소속인지 나타내는 구조화 필드가 없었다.

## 설계

- Engine 이벤트에 `agent_id`, `phase`, `loading`을 추가한다.
- Workflow는 각 전문 Agent에 대해 `start -> progress -> finish` 이벤트를 보낸다.
- 대기 timeout은 화면용 `log`가 아니라 보이지 않는 SSE `heartbeat`로 보낸다.
- Frontend는 `agent_id`를 기준으로 부모 블록을 찾고 모든 소속 로그를 자식으로 추가한다.
- 같은 Agent 안에서 동일 제목과 내용의 로그가 다시 오면 새 항목을 만들지 않는다.
- Agent 완료 또는 오류 시 부모와 자식 스피너를 종료한다.

## 성공 기준

- 동일한 일반 대기 로그가 화면에 반복되지 않는다.
- `risk-draft-agent`, `risk-review-agent`, `action-plan-agent`가 각각 독립 부모 블록으로 보인다.
- 실행 중인 Agent 부모 블록에만 스피너가 돈다.
- Skill/Tool/검토/완료 로그가 올바른 Agent 부모 아래 표시된다.
- Frontend typecheck/build와 Python 테스트가 통과한다.
