# 작업 설계: 샘플 시나리오 재검증 및 다중 Guideword 반영

## 배경

사용자가 `samples/` 폴더의 샘플 Excel 기준으로 실제 테스트를 요청했다.
또한 `#2 가이드워드` Sheet에서 하나의 변수(Parameter)에 여러 Guideword가 들어갈 수 있음을 명시했다.

## 수정 범위

1. `AGENTS.md`에 Codex 개발 하네스 문서를 항상 참고하라는 규칙을 추가한다.
2. 샘플 Excel 생성 스크립트에 다중 Guideword 케이스를 반영한다.
3. 기존 Agent/Excel 파싱 구조가 다중 Guideword를 별도 Row로 처리하는지 검증한다.
4. 세 샘플을 생성하고, 각 샘플을 Agent 흐름으로 돌려 결과 Excel 생성까지 확인한다.
5. 짧은 물질명 검색어가 KOSHA에서 엉뚱한 물질로 매칭되지 않도록 방어한다.

## 비수정 범위

- Node 자동 생성은 하지 않는다.
- Guideword 자동 추천은 하지 않는다.
- 위험도 기준은 변경하지 않는다.
- DB 스키마는 이번 작업에서 변경하지 않는다.

## 성공 기준

- 샘플 Excel 3개가 다시 생성된다.
- 각 샘플의 `#3`, `#4`는 생성 직후 헤더만 있고 데이터 행이 없다.
- `#2 가이드워드`에 동일 Node/동일 변수/다른 Guideword 조합이 존재한다.
- Agent 실행 시 다중 Guideword가 각각 별도 `#3 위험성평가` Row로 생성된다.
- 세 샘플 모두 결과 Excel이 생성된다.
- `HF`처럼 짧은 물질명은 KOSHA exact match가 없으면 잘못된 KOSHA 결과를 쓰지 않고 내장 요약으로 fallback한다.
- Node별 물질정보에 `HF byproduct`처럼 부가 설명이 붙어도 대표 물질 `HF`로 정규화한다.

## 테스트 계획

1. `python scripts/create_sample_excels.py`
2. 샘플 Sheet 구조 확인
3. `python -m compileall app scripts tests`
4. CleanTech, ASM, ThermoVac 샘플 각각 Agent 실행
5. 생성 Row 수와 조치계획서 생성 여부 확인
6. ThermoVac의 HF가 `HfSi2`로 잘못 매칭되지 않는지 확인

## 테스트 결과

2026-07-01 기준 로컬 Agent 흐름으로 아래 결과를 확인했다.

| 샘플 | `#2` 평가 조합 | 생성 `#3` Row | 생성 `#4` Row | MSDS 조회 |
|---|---:|---:|---:|---|
| CleanTech DI Water | 5 | 5 | 0 | DI Water 내장 요약 fallback |
| ASM Epsilon3200 Gas | 6 | 6 | 3 | Silane/Hydrogen/Nitrogen KOSHA 조회 |
| ThermoVac Etch | 6 | 6 | 1 | HF 내장 요약 fallback, Nitrogen KOSHA 조회 |

확인 사항:

- 샘플 생성 직후 `#3`, `#4`는 헤더 1행만 존재한다.
- 동일 Node/동일 변수의 복수 Guideword가 별도 위험성평가 Row로 생성된다.
- `HF`는 KOSHA에서 `HfSi2`로 잘못 매칭되지 않고 내장 HF 요약으로 fallback한다.
- `samples/~$...xlsx` 파일은 Excel이 파일을 열 때 만드는 잠금 파일이며 테스트 대상이 아니다.
