# Deepagent HAZOP Engine 시나리오 검증 기록

## 목적

Deepagent HAZOP Engine 1차 구현이 실제 샘플 Excel 기준으로 동작하는지 검증한다.

이번 검증은 단순 import/compile 테스트가 아니라, 저장된 시나리오 데이터를 기준으로 다음을 확인한다.

- 샘플 Excel의 `#1 노드리스트`, `#2 가이드워드` 파싱
- HAZOP Engine 초안 생성
- 입력 Excel에 없는 Node/변수/Guideword 생성 금지
- 위험도 시스템 계산
- 위험도 9 이상 항목만 조치계획서 대상 선별
- 판단/빈도/강도 근거 존재 여부
- 사고이력/표준 HAZOP 근거 부족 표시 여부
- 결과 Excel export 후 `#3`, `#4` 데이터 행 수 확인

## 재사용 시나리오 파일

시나리오는 아래 JSON 파일에 저장했다.

```text
tests/scenarios/hazop_engine_scenarios.json
```

테스트 코드는 아래 파일에서 해당 JSON을 읽어 반복 검증한다.

```text
tests/test_hazop_engine_scenarios.py
```

## 검증 시나리오

### 1. `cleantech_diw_low_risk`

- 샘플: `samples/HAZOP_CleanTech_CT-DIW-100.xlsx`
- 목적: DI Water 저위험 Utility 케이스 확인
- 기대:
  - Node 3개
  - Guideword 5개
  - `#3 위험성평가` 5건
  - 위험도 9 이상 0건
  - `#4 조치계획서` 0건

### 2. `asm_silane_high_risk`

- 샘플: `samples/HAZOP_ASM_Epsilon3200.xlsx`
- 목적: Silane/Hydrogen/Nitrogen 고위험 Gas 케이스 확인
- 기대:
  - Node 4개
  - Guideword 6개
  - `#3 위험성평가` 6건
  - 위험도 9 이상 2건
  - `#4 조치계획서` 2건

### 3. `thermovac_hf_high_risk`

- 샘플: `samples/HAZOP_ThermoVac_TV-ETCH-200.xlsx`
- 목적: Vacuum/Etch/Exhaust/HF 복수 Guideword 케이스 확인
- 기대:
  - Node 4개
  - Guideword 6개
  - `#3 위험성평가` 6건
  - 위험도 9 이상 1건
  - `#4 조치계획서` 1건

## 실행 명령

```bash
.venv/bin/python -m compileall app scripts tests
.venv/bin/python scripts/create_sample_excels.py
.venv/bin/python -m pytest tests/test_hazop_engine_scenarios.py
.venv/bin/python -m pytest
```

## 비고

- 테스트는 Azure OpenAI 환경 변수를 제거하고 demo fallback 모드로 실행한다.
- 이유는 외부 모델 품질/네트워크 상태와 무관하게 HAZOP Engine의 시스템 경계와 검증 기준을 재현 가능하게 만들기 위해서다.
- 실제 Deepagent 모델 호출 검증은 Azure OpenAI 연결 환경에서 별도 E2E 테스트로 분리한다.

## 2026-07-07 실행 결과

실행한 명령과 결과:

```bash
.venv/bin/python -m compileall app scripts tests
# 성공

.venv/bin/python scripts/create_sample_excels.py
# 샘플 Excel 3개 생성 성공

.venv/bin/python -m pytest tests/test_hazop_engine_scenarios.py
# 1 passed

.venv/bin/python -m pytest
# 6 passed
```

검증된 내용:

- `cleantech_diw_low_risk`: `#3` 5건, 고위험 0건, `#4` 0건
- `asm_silane_high_risk`: `#3` 6건, 고위험 2건, `#4` 2건
- `thermovac_hf_high_risk`: `#3` 6건, 고위험 1건, `#4` 1건
- 모든 시나리오에서 생성된 Node/변수/Guideword 조합이 입력 Excel의 `#2 가이드워드`와 정확히 일치
- 모든 위험도는 `빈도 * 강도`와 일치
- 모든 위험성평가 Row에 판단근거, 강도근거, 빈도근거 존재
- 빈도근거에 사고이력 또는 표준 HAZOP 근거 부족/확인 필요 관점 포함
- 결과 Excel export 후 `#3`, `#4` Sheet 데이터 행 수가 기대값과 일치
