# GitHub Repository Setup Worklog

## Goal

- 현재 HAZOP PoC 프로젝트를 Git 저장소로 초기화한다.
- GitHub 원격 저장소 이름은 `master-aipjt-hazop`으로 연결하는 것을 목표로 한다.
- `.env` 등 실제 환경변수 파일은 절대 Git에 올라가지 않도록 막는다.

## Scope

- Git 추적 제외 규칙을 추가한다.
- 로컬 Git 저장소를 초기화하고 안전한 파일만 첫 커밋에 포함한다.
- GitHub 저장소 생성/연결 가능 여부를 확인한다.

## Assumptions

- `.env.example`은 실제 비밀값이 아니라 예시값만 담은 템플릿이므로 커밋 가능하다.
- `.env`, `.env.*`는 실제 API 키나 DB 주소를 포함할 수 있으므로 커밋하지 않는다.
- `.venv`, `.pytest_cache`, `.DS_Store`, 로컬 DB 파일은 개발자 PC에서만 쓰는 파일이므로 커밋하지 않는다.

## Success Criteria

- `git status --ignored` 기준으로 `.env`가 ignored 상태임을 확인한다.
- 첫 커밋에 `.env`가 포함되지 않음을 확인한다.
- 가능하면 GitHub 원격 저장소 `master-aipjt-hazop`을 생성하고 `origin`으로 연결한다.
- GitHub 저장소 생성 도구가 없거나 인증 도구가 없으면, 로컬 커밋까지 완료하고 남은 연결 절차를 명확히 남긴다.
