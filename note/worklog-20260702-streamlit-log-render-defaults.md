# 작업 설계: Streamlit 로그 렌더링 오류와 기본 입력값 보완

## 배경

Streamlit 화면의 Agent 로그 영역에 `<div class="log-item">` 같은 HTML 코드가 그대로 노출된다.
이는 로그를 HTML 문자열로 조립한 뒤 Markdown에 넣는 과정에서 일부 문자열이 코드 블록처럼 해석되기 때문이다.
또한 사용자는 Node별 물질정보, 표준공정위험성평가서 Link/ID, 추가 메모 입력칸에 기본값이 들어가 있기를 원한다.

## 목표

1. Agent 로그 화면에 HTML 코드가 보이지 않게 한다.
2. 로그는 Streamlit 기본 컴포넌트로 표시해 렌더링 오류 가능성을 줄인다.
3. 진행 중인 최신 로그는 Streamlit spinner로 표시한다.
4. Node별 물질정보, 표준공정위험성평가서 Link/ID, 추가 메모에 PoC용 기본값을 넣는다.
5. 수정 후 Docker로 실제 앱을 띄우고 브라우저에서 화면을 확인한다.

## 구현 방침

- `_render_logs`에서 HTML 문자열 조립을 제거한다.
- 과거 로그는 `st.markdown`, `st.caption`, 구분선으로 표시한다.
- 최신 진행 로그는 `st.spinner`를 사용한다.
- `_inject_styles`는 화면 폭 등 안전한 전역 스타일만 남기고 로그 HTML 스타일은 제거한다.
- 기본 입력값은 CleanTech 샘플 기준으로 보수적으로 작성한다.

## 성공 기준

- `compileall`, 테스트, 샘플 Excel 생성이 통과한다.
- Docker 이미지가 빌드된다.
- Docker Compose로 Streamlit 앱을 실행했을 때 `http://127.0.0.1:8501`이 응답한다.
- 브라우저 화면에서 `<div class="log-item">` 같은 HTML 코드가 보이지 않는다.
