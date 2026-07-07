# Streamlit 밝은 테마 보정 작업 설계

## 배경

사용자는 Node별 물질정보 UI가 Streamlit에도 반영되었는지 확인했고,
Streamlit 화면 테마를 더 밝게 바꾸길 요청했다.

현재 Streamlit에는 Excel 업로드 후 `#1 노드리스트`를 읽어 Node 개수만큼
물질정보 입력칸을 표시하는 로직이 이미 반영되어 있다.

## 구현 범위

- Streamlit 전용 `_inject_styles()` CSS만 수정한다.
- 전체 배경을 밝은 회백색으로 두고, 입력/로그/결과 영역은 흰색 패널처럼 보이게 한다.
- 입력창, 파일 업로더, 버튼, 알림 박스의 대비를 높여 화면을 더 환하게 만든다.
- Agent/Excel 생성 로직은 변경하지 않는다.

## 성공 기준

- Streamlit 코드에서 Node별 물질정보 UI가 유지된다.
- 화면 배경과 컨테이너가 기존보다 밝은 톤으로 보인다.
- Python 컴파일 검사가 통과한다.
- Docker 사용 시 `docker compose up --build`로 변경 사항이 반영될 수 있다.
