# Codex 개발 하네스

이 문서는 HAZOP PoC를 수정할 때 Codex가 항상 먼저 확인해야 하는 고정 기준입니다.
대화 문맥이 길어져도 방향을 잃지 않기 위해, 소스 수정 전에는 이 문서 또는 작업별 설계 문서를 먼저 갱신합니다.

## 1. 수정 전 고정 절차

소스 수정이 발생하는 작업은 아래 순서를 지킵니다.

1. 현재 브랜치를 확인하고, `main`에서 직접 수정하지 않는다.
2. 기능 개발은 `feature/작업명`, 버그 수정은 `bug/작업명` 형식의 별도 브랜치를 만든다.
3. 무엇을 왜 바꿀지 설계를 먼저 파일로 남긴다.
4. 설계에 포함된 성공 기준을 확인한다.
5. 설계 범위 안에서만 소스를 수정한다.
6. 샘플 시나리오 기준으로 다시 테스트한다.
7. 테스트 결과와 남은 리스크를 사용자에게 보고한다.

## 2. HAZOP PoC 고정 원칙

- Excel의 `#1 노드리스트`, `#2 가이드워드`는 사용자가 작성한 입력값이다.
- `#3 위험성평가`, `#4 조치계획서`는 AI Agent와 시스템이 채우는 출력값이다.
- 샘플 Excel 생성 시 `#3`, `#4`는 헤더만 있고 데이터 행은 비어 있어야 한다.
- AI는 Node, 변수, Guideword를 새로 만들면 안 된다.
- `#2 가이드워드`에는 하나의 Node/변수에 여러 Guideword가 존재할 수 있다.
  - 예: `Flow / No`, `Flow / Less`, `Flow / More`
  - 이 경우 각각 별도의 위험성평가 Row로 처리한다.
- 위험도는 AI가 계산하지 않는다. 시스템이 `빈도 * 강도`로 계산한다.
- 빈도는 1~5, 강도는 1~4 범위로 제한한다.
- 위험도 9 이상이면 `#4 조치계획서` 생성 대상이다.
- Agent 로그에는 판단뿐 아니라 근거를 함께 남긴다.

## 3. 외부 정보 조회 원칙

- MSDS는 KOSHA 안전보건공단 MSDS 조회를 우선 사용한다.
- KOSHA에서 조회되지 않는 물질은 PoC 내장 요약으로 fallback한다.
- 일반 웹 검색 API는 KOSHA 조회 실패 후 선택적으로만 사용한다.
- 외부 조회 결과는 최종 확정 정보가 아니라 HAZOP 초안 작성 참고자료로 취급한다.
- MSDS 근거가 부족하면 `확인 필요`를 남긴다.

## 4. 검증 시나리오

소스 수정 후 최소한 아래 3개 샘플을 기준으로 검증한다.

| 샘플 | 목적 | 기대 |
|---|---|---|
| `HAZOP_CleanTech_CT-DIW-100.xlsx` | DI Water 저위험 Utility 케이스 | `#3` 생성, 대부분 `#4` 없음 |
| `HAZOP_ASM_Epsilon3200.xlsx` | Silane/Hydrogen/Nitrogen 고위험 Gas 케이스 | KOSHA MSDS 근거, 위험도 9 이상 항목과 `#4` 생성 |
| `HAZOP_ThermoVac_TV-ETCH-200.xlsx` | Vacuum/Etch/Exhaust/HF 계열 케이스 | 복수 Guideword 처리, 위험도 9 이상 항목과 `#4` 생성 |

## 5. 테스트 명령

```bash
python scripts/create_sample_excels.py
python -m compileall app scripts tests
```

Docker 기준:

```bash
docker compose down
docker compose up --build
```

API 확인:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/jobs
```

## 6. 작업별 설계 기록

작업별로 더 상세한 설계가 필요한 경우 `note/worklog-YYYYMMDD-작업명.md` 형태로 추가한다.
그 작업이 진행되는 동안에는 해당 worklog를 기준으로 구현과 검증을 수행한다.
