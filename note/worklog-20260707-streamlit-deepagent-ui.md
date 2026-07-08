# Streamlit 업로드 UI 및 DeepAgent 연결 오류 수정 설계

## 배경

Streamlit 화면에서 Excel 파일 선택이 되지 않는 문제가 보고되었다.
또한 이전 밝은 테마는 너무 단순하게 밝아져서, Notion처럼 따뜻하고 부드러운
작업 도구 느낌으로 다시 정리해야 한다.

DeepAgent 실행 중 `Connection error`가 발생해 PoC 내장 생성기로 fallback되는
문제도 함께 보고되었다. 현재 코드는 실제 연결 실패 원인을 자세히 설명하지 않고
예외 문자열만 표시한다.

## 참고한 디자인 방향

- VoltAgent `awesome-design-md` README는 `DESIGN.md`가 색, 타이포, 컴포넌트 규칙을
  문서화해 AI가 일관된 UI를 만들게 하는 방식이라고 설명한다.
- Notion 디자인 요약은 warm minimalism, serif headings, soft surfaces이다.
- Streamlit 제약 안에서 따뜻한 배경, 잉크색 텍스트, 부드러운 입력 영역, 명확한
  업로드 버튼을 적용한다.

## 구현 범위

- `app/streamlit_app.py`
  - 파일 업로더가 클릭 가능한 기본 구조를 유지하도록 CSS를 보강한다.
  - Notion 느낌의 warm minimal theme로 CSS를 교체한다.
  - 업로드 안내 문구를 더 명확하게 표시한다.
- `app/hazop_engine/agents/deepagent_factory.py`
  - DeepAgent가 문자열 모델명 대신 AzureChatOpenAI 객체를 직접 사용하게 한다.
  - `AZURE_OPENAI_VERIFY_SSL=false`일 때 LangChain/OpenAI 쪽 HTTP client도 SSL 검증을 끄도록 한다.
- `app/hazop_engine/workflow.py`
  - `Connection error`를 그대로 노출하지 않고, 가능한 원인과 확인할 설정을 한국어로 설명한다.
- 테스트는 기존 fallback 동작을 깨지 않는 선에서 원인 설명 함수를 검증한다.

## 성공 기준

- Streamlit 파일 업로더가 보이고 클릭 가능한 스타일을 유지한다.
- 화면이 단순한 흰색이 아니라 Notion풍 warm minimal 작업 화면처럼 보인다.
- DeepAgent 연결 실패 시 endpoint, SSL, API version, deployment 같은 점검 포인트가 로그에 남는다.
- `AZURE_OPENAI_VERIFY_SSL=false` 설정이 DeepAgent 경로에도 반영된다.
- `python3 -m compileall app scripts tests`와 관련 pytest가 통과한다.
