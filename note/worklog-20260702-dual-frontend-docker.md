# 작업 설계: Docker Compose에서 Streamlit과 기존 Frontend 동시 실행

## 배경

Docker Compose 기본 실행을 Streamlit으로 바꿨지만, 기존 FastAPI 정적 frontend가 더 안정적으로 보이는 상황이다.
사용자는 Streamlit 화면을 유지하면서도 `8000` 포트에서 기존 frontend를 계속 볼 수 있기를 원한다.

## 목표

1. `http://127.0.0.1:8501`에서는 Streamlit 화면을 제공한다.
2. `http://127.0.0.1:8000`에서는 기존 FastAPI 기본 frontend를 제공한다.
3. 두 서비스 모두 동일한 코드 이미지와 `data`, `samples` 볼륨을 사용한다.
4. 두 서비스 모두 Postgres 준비 이후 실행된다.

## 구현 방침

- `app` 서비스는 Streamlit 전용으로 유지한다.
- `api` 서비스를 추가하고 `uvicorn app.main:app --host 0.0.0.0 --port 8000` 명령으로 실행한다.
- 컨테이너 이름은 충돌하지 않도록 `hazop-poc-streamlit`, `hazop-poc-api`로 분리한다.
- README에 두 접속 주소를 함께 적는다.

## 성공 기준

- `docker compose config`가 통과한다.
- `docker compose up --build -d` 후 `8501`, `8000`이 모두 HTTP 200을 반환한다.
- 기존 테스트와 샘플 생성이 통과한다.
