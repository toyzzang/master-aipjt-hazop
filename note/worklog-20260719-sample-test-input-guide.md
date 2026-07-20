# 샘플 테스트 입력 가이드 및 ColdChain 기본값

## 요청

- Step 1 사용자 입력의 최초 예시를 `HAZOP_ColdChain_NH3-Refrigeration.xlsx` 기준으로 변경한다.
- 모든 샘플 Excel에 대해 Maker, Model, 유사 HAZOP ID, 운전 의도, 사고·정비 이력을 복사 가능한 Markdown으로 정리한다.
- 각 샘플의 Node별 물질 Key-in 값을 화면과 문서에 표시한다.

## 확인한 샘플

- CleanTech / CT-DIW-100
- ASM / Epsilon3200
- ThermoVac / TV-ETCH-200
- ColdChain / NH3-Refrigeration
- Solvent / IPA-Supply
- Waterworks / Chlorine-Dosing
- Battery / Electrolyte-Mixing
- Integrated / MultiUtility-Complex

실제 `.xlsx`를 Artifact Tool로 읽어 `#1 노드리스트`, `#2 가이드워드`, 빈 `#3/#4` 구조를 확인한다.

## 구현

- Frontend 최초 state를 ColdChain 값으로 변경한다.
- Node 이름별 권장 물질 매핑을 Frontend에 두고 물질 입력 placeholder로 표시한다.
- `note/sample-test-input-guide.md`에 8개 샘플의 복사용 입력값을 작성한다.
- 문서의 사고이력과 표준 HAZOP ID는 실제 사실/실제 문서가 아닌 PoC 테스트용 가상값이라고 표시한다.

## 성공 기준

- 첫 화면 Maker/Model/운전 의도/사고이력이 ColdChain 예시로 표시된다.
- ColdChain 파일 업로드 시 6개 Node 모두 `Ammonia` 입력 안내가 보인다.
- 나머지 7개 샘플도 Node별 권장 물질이 보인다.
- Markdown 문서에서 샘플별 입력값을 그대로 복사할 수 있다.
- Frontend typecheck/build와 회귀 테스트가 통과한다.
