# Agent Context·Tool 진행 로그 및 로딩 화면 개선

## 요청

- 각 Sub Agent 블록에서 Skill뿐 아니라 Context 구성, Tool 연결, LLM 요청 과정을 보여준다.
- `모델 응답 대기 중입니다`는 Agent마다 한 번씩 해당 블록 안에 표시한다.
- DeepAgent가 실제 호출한 보완 조회 Tool trace는 기존처럼 결과와 함께 표시한다.
- #3/#4 로딩 영역을 남는 공간에 꽉 채우고 중앙 정렬한다.
- 로딩 중 문구와 표시 요소에 부드러운 페이드 인·아웃 효과를 적용한다.

## 로그 구분

- `Context 구성`: Workflow가 이미 확보한 Excel, 최초 MSDS, 위험도 기준표, 검증본을 묶는 과정
- `Tool 연결`: Agent가 필요할 때 선택 호출할 수 있는 MSDS 상세, 사고이력, 표준 HAZOP Tool
- `Skill 참조`: 판단 기준 적용 안내
- `모델 응답 대기`: 해당 Agent의 Azure OpenAI 요청 1회
- `Tool 호출 성공/실패`: DeepAgents 응답 trace에서 실제 호출이 확인된 경우만 표시

## 성공 기준

- 세 Agent 각각에서 Context → Tool → Skill → 모델 요청 → 결과 흐름을 읽을 수 있다.
- 같은 Agent에 모델 대기 로그가 중복되지 않는다.
- #3/#4 로딩 화면이 결과 패널의 남는 높이를 채우고 중앙에 표시된다.
- 동작 감소 OS 설정에서는 페이드 애니메이션을 끈다.
- 테스트, typecheck, build가 통과한다.
