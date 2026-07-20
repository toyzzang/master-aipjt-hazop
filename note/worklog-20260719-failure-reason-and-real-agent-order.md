# 실패 원인 표시 및 실제 Agent 실행 순서 정리

## 진단 결과

- 사용자가 본 실패 시점에도 DB 작업 상태는 `RUNNING`이었다.
- risk-draft-agent 15개 Row 생성과 시스템 검증은 성공했고 risk-review-agent 응답 대기 중이었다.
- Frontend가 브라우저 EventSource의 일반 연결 `error` 신호를 실제 Agent 실패로 오인해 무조건 `실패` 처리했다.
- `error`는 EventSource의 예약 연결 이벤트이므로 서버 업무 오류와 같은 이름으로 사용하면 구분하기 어렵다.

## 변경

- 서버 업무 오류 이벤트 이름을 `agent_error`로 분리한다.
- `agent_error`에는 title, message, stage를 포함한다.
- Frontend는 `agent_error`일 때만 작업을 `실패`로 표시하고 실제 원인을 Error 로그에 남긴다.
- 일반 SSE 연결 오류는 `연결 끊김`으로 표시하고 Agent 판단 실패가 아닌 통신 문제임을 설명한다.
- 자동 재연결로 같은 job이 중복 실행되지 않도록 연결 오류 시 EventSource를 닫는다.

## 실제 Agent 순서

1. Workflow Excel/MSDS 준비
2. DeepAgent 생성 시 Skill 저장소와 Tool 함수를 실행환경에 등록
3. Excel/MSDS/사고이력/기준표 Context Prompt 구성
4. LLM Agent 실행
5. Agent 실행 안에서 필수 Skill 본문 읽기
6. 필요 시 보완 Tool 선택 호출
7. 구조화 결과 반환
8. Skill/Tool trace와 결과 형식 검증
9. 시스템 위험도 계산

## 화면 순서

- Skill 실행 기준 등록 안내
- Tool 등록 안내
- Context 구성 안내
- 모델 응답 대기
- 실제 Skill 적용 확인 요약
- 실제 Tool 호출 결과
- Agent 결과

## 성공 기준

- 연결 오류를 Agent 실패로 잘못 표시하지 않는다.
- 실제 업무 실패 시 원인이 실시간 Error 로그에 표시된다.
- 실시간 Agent 로그 순서가 실제 실행 구조와 모순되지 않는다.
- 테스트와 Frontend 빌드가 통과한다.
