# AGENTS.md

## 사용자 설명 원칙

- 사용자는 AI 기본지식이 낮은 상태라고 가정한다.
- AI, Agent, LLM, Tool, RAG, MSDS 조회, 위험도 계산 같은 개념은 가능한 한 쉬운 말로 설명한다.
- 어려운 용어를 쓸 때는 "쉽게 말하면" 형태의 설명을 함께 붙인다.

## Karpathy-Inspired Coding Rules

이 프로젝트의 소스 수정은 `multica-ai/andrej-karpathy-skills`의 핵심 원칙을 프로젝트 상황에 맞게 적용한다.

## Codex 개발 하네스

- 소스 수정 전에는 [note/codex-development-harness.md](note/codex-development-harness.md)를 먼저 확인한다.
- 소스 수정이 발생하는 작업은 먼저 작업 설계를 파일로 남긴 뒤 구현한다.
- 작업별 설계 문서는 `note/worklog-YYYYMMDD-작업명.md` 형태로 작성한다.
- 구현 중 대화 문맥이 길어져도 해당 하네스/작업 설계 문서를 기준점으로 삼는다.

## Git 브랜치 작업 규칙

- 앞으로 무언가 변경점에 대한 소스 변경이 발생하면 `main`에서 직접 작업하지 않는다.
- `main` 브랜치는 항상 프로젝트 루트 `/Users/zzang/Desktop/me/project/master-aipjt`에 둔다.
- 새 작업은 항상 프로젝트 루트의 `.worktrees/작업명` 아래에 별도 worktree를 만들어 진행한다.
- 작업 시작 전에 `.worktrees/작업명`에 별도 브랜치를 생성하고, 그 브랜치에서만 수정한다.
- 새 기능 작업을 시작할 때는 아래 형태를 기본으로 사용한다.
  - `cd /Users/zzang/Desktop/me/project/master-aipjt`
  - `git worktree add .worktrees/작업명 -b feature/작업명`
  - `cd .worktrees/작업명`
- 이미 존재하는 브랜치를 worktree로 열 때는 아래 형태를 사용한다.
  - `cd /Users/zzang/Desktop/me/project/master-aipjt`
  - `git worktree add .worktrees/작업명 feature/작업명`
  - `cd .worktrees/작업명`
- 기능 개발은 `feature/작업명` 형식의 브랜치를 사용한다.
  - 예: `feature/excel-upload-ui`
- 버그 수정은 `bug/작업명` 형식의 브랜치를 사용한다.
  - 예: `bug/risk-score-calculation`
- 쉽게 말하면, 루트의 `main`은 완성본을 보관하는 책장이고 `.worktrees/작업명`은 실제로 고치고 실험하는 작업 책상이다.
- 같은 브랜치를 두 worktree에서 동시에 checkout하지 않는다.
- worktree별 의존성이 달라질 수 있으므로, 필요하면 각 worktree에 별도 `.venv`를 둔다.

## PR 이후 정리 규칙

- 사용자가 "정리해줘"라고 요청하면 먼저 아래를 확인한다.
  - 작업 브랜치가 원격에 push되어 있는지 확인한다.
  - 해당 원격 브랜치로 PR이 생성되어 있는지 확인한다.
  - PR의 대상 브랜치가 사용자가 의도한 대상인지 확인한다. 기본 대상은 `main`이다.
- 위 조건이 모두 충족되면 작업용 worktree를 삭제한다.
  - 예: `git worktree remove .worktrees/작업명`
- worktree 삭제 후 해당 로컬 브랜치도 삭제한다.
  - 예: `git branch -d feature/작업명`
- 원격 브랜치는 PR 상태에 따라 삭제 여부를 판단한다.
  - PR이 아직 열려 있으면 원격 브랜치는 삭제하지 않는다.
  - PR이 merge/close 되었고 사용자가 원격 브랜치 삭제도 원하면 `git push origin --delete feature/작업명`으로 삭제한다.
- push 또는 PR 생성이 확인되지 않으면 worktree와 로컬 브랜치를 삭제하지 않는다.
- 쉽게 말하면, "정리해줘"는 작업물이 GitHub에 안전하게 올라간 것을 확인한 뒤 로컬 작업 책상만 치우는 명령이다.

### 1. Think Before Coding

- 애매한 요구사항은 조용히 추측해서 크게 구현하지 않는다.
- 단, PoC 진행을 막지 않는 범위에서는 합리적인 가정을 명시하고 작게 구현한다.
- 여러 해석이 가능한 경우에는 코드와 문서에 어떤 가정을 택했는지 남긴다.

### 2. Simplicity First

- PoC 목적을 만족하는 최소 구조를 우선한다.
- 한 번만 쓰는 코드를 과도한 추상화로 감싸지 않는다.
- 나중에 필요할 것 같은 기능은 지금 만들지 않는다.
- 200줄로 만든 코드가 50줄로 충분하면 줄인다.

### 3. Surgical Changes

- 요청과 직접 관련 있는 파일만 수정한다.
- 기존 문서나 코드의 주변 형식을 불필요하게 바꾸지 않는다.
- 내가 만든 변경으로 생긴 미사용 코드만 정리한다.

### 4. Goal-Driven Execution

- 작업을 "무엇을 만들지"가 아니라 "무엇이 되면 성공인지"로 검증한다.
- 이번 PoC의 1차 성공 기준은 다음과 같다.
  - 샘플 Excel 3개가 생성된다.
  - `#1 노드리스트`, `#2 가이드워드`만 채워져 있고 `#3`, `#4` 데이터 영역은 비어 있다.
  - 웹 화면에서 Excel을 업로드할 수 있다.
  - Agent 로그가 실시간으로 표시된다.
  - `#3 위험성평가`, `#4 조치계획서` 초안이 생성된다.
  - 결과 Excel을 다운로드할 수 있다.

## HAZOP PoC 개발 규칙

- 위험도 점수는 AI가 계산하지 않는다. 시스템 코드가 `빈도 * 강도`로 계산한다.
- 빈도는 1~5, 강도는 1~4 범위로 제한한다.
- 위험도 9 이상이면 조치계획서 생성 대상이다.
- AI가 Node, 변수, Guideword를 새로 만들면 안 된다. 업로드 Excel의 `#1`, `#2` 기준으로만 생성한다.
- `#2 가이드워드`에는 동일 Node/동일 변수에 여러 Guideword가 존재할 수 있으며, 각각 별도 평가 Row로 처리한다.
- Agent 로그에는 "판단"뿐 아니라 "근거"를 함께 남긴다.
- 한국어 주석을 충분히 작성해서, AI/Agent에 익숙하지 않은 사람도 흐름을 따라갈 수 있게 한다.
