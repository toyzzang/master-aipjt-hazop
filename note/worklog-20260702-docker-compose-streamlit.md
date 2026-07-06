# 작업 설계: Docker Compose 기본 실행을 Streamlit으로 변경

## 배경

현재 Dockerfile과 docker-compose.yml은 FastAPI/uvicorn을 기본 실행 대상으로 사용한다.
사용자는 Docker Compose로 실행했을 때 새로 만든 Streamlit 2분할 화면이 바로 뜨기를 원한다.

## 목표

1. `docker compose up --build` 실행 시 Streamlit 앱이 기본으로 뜬다.
2. 브라우저 접속 포트는 Streamlit 기본 포트인 `8501`을 사용한다.
3. 컨테이너 안에서도 `app/streamlit_app.py`가 `app.schemas`, `app.services`를 안정적으로 import한다.
4. 기존 FastAPI 코드는 삭제하지 않는다. 필요하면 별도 명령으로 계속 실행할 수 있게 둔다.

## 구현 방침

- `Dockerfile`의 `EXPOSE`와 `CMD`를 Streamlit 기준으로 변경한다.
- `docker-compose.yml`의 app 포트 매핑을 `8501:8501`로 변경한다.
- Streamlit 실행 시 서버 주소는 `0.0.0.0`으로 설정해 컨테이너 밖 브라우저에서 접속 가능하게 한다.
- Streamlit 앱 시작 시 프로젝트 루트를 `sys.path`에 추가해 import 경로 문제를 방지한다.

## 성공 기준

- `docker compose config`가 정상 출력된다.
- Python compile 검증을 통과한다.
- 실행 방법은 `docker compose up --build` 후 `http://127.0.0.1:8501` 접속으로 단순화된다.
