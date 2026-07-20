# HAZOP 샘플별 테스트 입력값 모음

이 문서는 `samples/` 폴더의 HAZOP Excel을 웹 화면에서 하나씩 테스트할 때 사용하는 복사용 입력 모음입니다.

> 중요: 아래 `유사 HAZOP 문서 ID`와 `사고·정비 이력`은 실제 회사 문서나 실제 사고 사실이 아닙니다. PoC 동작을 확인하기 위해 만든 가상 테스트 값입니다.

## 사용 방법

1. 해당 샘플 Excel을 업로드합니다.
2. Maker, Model, 유사 HAZOP 문서 ID, 운전 의도, 사고·정비 이력을 아래 값으로 바꿉니다.
3. Node List 오른쪽의 물질 입력칸에 `Node별 물질 Key-in` 값을 입력합니다.
4. 물질 입력칸의 `예: ...` 문구는 안내용 placeholder이므로, 실제 조회를 위해서는 값을 직접 입력해야 합니다.
5. `AI 초안생성`을 누릅니다.

---

## 1. ColdChain / NH3-Refrigeration

- Excel: `samples/HAZOP_ColdChain_NH3-Refrigeration.xlsx`
- 목적: 독성·가연성 냉매의 압축·응축·팽창·누출 복합 시나리오

### Step 1 입력값

```text
Maker
ColdChain

Model
NH3-Refrigeration

유사 HAZOP 문서 ID
STD-HAZOP-NH3-REFRIGERATION-2026-001

운전 의도
ColdChain NH3-Refrigeration 냉동설비의 정상운전 및 비정상 상태 검토용입니다.
액체 암모니아 저장, 압축, 오일 분리, 응축, 팽창, 증발 과정에서 과압·저압·과열·냉각 상실·누출 시나리오를 검토합니다.

사고·정비 이력
최근 3년간 사망·중대재해 없음.
최근 1년간 Compressor 토출압 High Alarm 2회, Expansion Valve 결빙으로 유량 저하 1회, Machine Room 암모니아 감지기 경보 1회가 있었으며 실제 대량 누출은 확인되지 않음.
정기점검 시 Compressor Mechanical Seal과 Receiver 연결부 미세 누설 여부를 중점 확인함.
```

### Node별 물질 Key-in

```text
NH3 Receiver: Ammonia
NH3 Compressor: Ammonia
Oil Separator: Ammonia
Condenser: Ammonia
Expansion Valve: Ammonia
Evaporator 및 Machine Room: Ammonia
```

---

## 2. CleanTech / CT-DIW-100

- Excel: `samples/HAZOP_CleanTech_CT-DIW-100.xlsx`
- 목적: DI Water 저위험 Utility 기본 시나리오

### Step 1 입력값

```text
Maker
CleanTech

Model
CT-DIW-100

유사 HAZOP 문서 ID
STD-HAZOP-DIW-UTILITY-2026-001

운전 의도
CleanTech CT-DIW-100 설비에서 DI Water를 저장하고 Wet 장비까지 안정적으로 공급하는 운전입니다.
탱크 수위 이상, 펌프 정지·유량 저하, 공급 배관 누수로 인한 생산 영향과 안전조치를 검토합니다.

사고·정비 이력
최근 3년간 인적 재해 및 중대 사고 없음.
최근 1년간 탱크 Low Level Alarm 1회와 이송 펌프 순간 Trip 2회가 있었으며 예비 펌프 전환으로 생산 중단은 없었음.
분기 점검에서 공급 배관 연결부 미세 누수 흔적 1건을 조임 보수함.
```

### Node별 물질 Key-in

```text
DI Water 공급 탱크: DI Water
DI Water 이송 펌프: DI Water
Wet 장비 공급 배관: DI Water
```

---

## 3. ASM / Epsilon3200

- Excel: `samples/HAZOP_ASM_Epsilon3200.xlsx`
- 목적: Silane·Hydrogen·Nitrogen 고위험 Gas 시나리오

### Step 1 입력값

```text
Maker
ASM

Model
Epsilon3200

유사 HAZOP 문서 ID
STD-HAZOP-SPECIALTY-GAS-2026-001

운전 의도
ASM Epsilon3200 공정에 Silane과 Hydrogen을 정해진 유량으로 공급하고 Nitrogen으로 Purge하는 운전입니다.
Gas Cabinet 누출·파열, 배관 역류, MFC 과다·과소 유량, Purge 실패 시 화재·폭발·질식 위험을 검토합니다.

사고·정비 이력
최근 3년간 화재·폭발 및 인적 재해 없음.
최근 1년간 Gas Cabinet 압력 이상 경보 2회, MFC Zero Drift 1회, Purge 완료 신호 지연 1회가 있었음.
실제 Silane 또는 Hydrogen 누출은 확인되지 않았고 정기 누설시험과 MFC 교정을 수행함.
```

### Node별 물질 Key-in

```text
Gas Cabinet: Silane, Hydrogen, Nitrogen
VMB 및 공급 배관: Silane, Hydrogen, Nitrogen
MFC 유량 제어 구간: Silane, Hydrogen, Nitrogen
Purge 및 Scrubber 구간: Nitrogen, Silane, Hydrogen
```

---

## 4. ThermoVac / TV-ETCH-200

- Excel: `samples/HAZOP_ThermoVac_TV-ETCH-200.xlsx`
- 목적: Vacuum·Etch·Exhaust·HF 복합 시나리오

### Step 1 입력값

```text
Maker
ThermoVac

Model
TV-ETCH-200

유사 HAZOP 문서 ID
STD-HAZOP-HF-ETCH-2026-001

운전 의도
ThermoVac TV-ETCH-200에서 진공 상태를 유지하며 HF 계열 Etch 공정을 수행하고 배출가스를 Scrubber로 처리하는 운전입니다.
Chamber 압력 이상, Vacuum Line 유량 상실·역류, Scrubber 처리 성능 저하, HF 공급부 누출을 검토합니다.

사고·정비 이력
최근 3년간 HF 노출 재해 및 중대 사고 없음.
최근 1년간 Vacuum Pump Trip 2회, Scrubber 차압 High Alarm 1회, HF 감지기 사전경보 1회가 있었음.
HF 실제 누출은 확인되지 않았으며 Pump Seal과 HF 공급 연결부를 예방 교체함.
```

### Node별 물질 Key-in

```text
Etch Chamber: HF, Nitrogen
Vacuum Pump Line: HF, Nitrogen
Exhaust Scrubber: HF
HF Chemical Supply: HF
```

---

## 5. Solvent / IPA-Supply

- Excel: `samples/HAZOP_Solvent_IPA-Supply.xlsx`
- 목적: 인화성 IPA 하역·저장·이송·회수 및 정전기 점화 시나리오

### Step 1 입력값

```text
Maker
Solvent

Model
IPA-Supply

유사 HAZOP 문서 ID
STD-HAZOP-IPA-SUPPLY-2026-001

운전 의도
IPA Drum에서 Day Tank로 용제를 하역하고 Transfer Pump와 Supply Header를 통해 장비에 공급한 뒤 폐용제를 회수하는 운전입니다.
누출, 접지 상실, 탱크 과충전·고온, 펌프 역류, 공급 압력 이상에 따른 화재·폭발 위험을 검토합니다.

사고·정비 이력
최근 3년간 화재·폭발 및 휴업 재해 없음.
최근 1년간 접지 확인 Interlock 미성립 1회, Transfer Pump Seal 미세 스며나옴 1회, Day Tank High Level 경보 1회가 있었음.
누출 부위를 즉시 보수하고 접지 Clamp와 Level Switch 기능시험을 수행함.
```

### Node별 물질 Key-in

```text
IPA Drum Unloading: Isopropyl alcohol
IPA Day Tank: Isopropyl alcohol
Transfer Pump: Isopropyl alcohol
Tool Supply Header: Isopropyl alcohol
Waste Solvent Return: Isopropyl alcohol
```

---

## 6. Waterworks / Chlorine-Dosing

- Excel: `samples/HAZOP_Waterworks_Chlorine-Dosing.xlsx`
- 목적: 독성 Chlorine 저장·기화·주입 및 과다·과소 투입 시나리오

### Step 1 입력값

```text
Maker
Waterworks

Model
Chlorine-Dosing

유사 HAZOP 문서 ID
STD-HAZOP-CHLORINE-DOSING-2026-001

운전 의도
Chlorine Ton Container의 액화염소를 기화하고 진공 조절 후 Chlorinator와 Injector를 통해 Contact Basin에 정량 주입하는 운전입니다.
염소 누출·용기 파열, 기화기 온도·압력 이상, 진공 상실, 투입량 과다·과소, Emergency Scrubber 성능 저하를 검토합니다.

사고·정비 이력
최근 3년간 염소 중독 및 중대 사고 없음.
최근 1년간 Vacuum Low Alarm 2회, Chlorinator Dose 편차 1회, Emergency Scrubber 시험 중 순환유량 저하 1회가 있었음.
실제 염소 누출은 확인되지 않았으며 Regulator Diaphragm과 Scrubber Pump를 정비함.
```

### Node별 물질 Key-in

```text
Chlorine Ton Container: Chlorine
Evaporator: Chlorine
Vacuum Regulator: Chlorine
Chlorinator: Chlorine
Injector 및 Contact Basin: Chlorine
Emergency Scrubber: Chlorine
```

---

## 7. Battery / Electrolyte-Mixing

- Excel: `samples/HAZOP_Battery_Electrolyte-Mixing.xlsx`
- 목적: 가연성 전해액 혼합·가열·질소봉입·충전 시나리오

### Step 1 입력값

```text
Maker
Battery

Model
Electrolyte-Mixing

유사 HAZOP 문서 ID
STD-HAZOP-BATTERY-ELECTROLYTE-2026-001

운전 의도
Ethylene carbonate와 Dimethyl carbonate 용매에 Lithium hexafluorophosphate를 투입·혼합하고 Nitrogen Blanketing 상태에서 여과·충전하는 운전입니다.
용매 누출·고온, LiPF6 수분 접촉, 교반·투입 순서 이상, 질소 압력·유량 상실, 충전부 정전기 위험을 검토합니다.

사고·정비 이력
최근 3년간 화재 및 전해액 노출 휴업 재해 없음.
최근 1년간 Agitator Trip 1회, Nitrogen Low Pressure Alarm 2회, LiPF6 투입 Booth 습도 경보 1회가 있었음.
혼합기 Motor와 질소 Regulator를 정비하고 Booth 제습기 성능을 확인함.
```

### Node별 물질 Key-in

```text
Solvent Storage: Ethylene carbonate, Dimethyl carbonate
LiPF6 Charging Booth: Lithium hexafluorophosphate
Mixing Reactor: Lithium hexafluorophosphate, Ethylene carbonate, Dimethyl carbonate
Heating/Cooling Jacket: Lithium hexafluorophosphate, Ethylene carbonate, Dimethyl carbonate
Nitrogen Blanketing: Nitrogen
Filtration: Lithium hexafluorophosphate, Ethylene carbonate, Dimethyl carbonate
Filling Line: Lithium hexafluorophosphate, Ethylene carbonate, Dimethyl carbonate
```

---

## 8. Integrated / MultiUtility-Complex

- Excel: `samples/HAZOP_Integrated_MultiUtility-Complex.xlsx`
- 목적: Hydrogen·Ammonia·IPA·Nitrogen·DI Water가 상호작용하는 통합 복합 시나리오

### Step 1 입력값

```text
Maker
Integrated

Model
MultiUtility-Complex

유사 HAZOP 문서 ID
STD-HAZOP-MULTI-UTILITY-2026-001

운전 의도
Hydrogen과 Ammonia를 Process Reactor에 공급하고 IPA 계열 용제, Nitrogen Purge, DI Water Cooling, Abatement·Exhaust를 연계 운전하는 통합 공정입니다.
가스 누출·압력·유량 이상, Ammonia 기화 이상, IPA 접지·이송 문제, Purge·Cooling 상실, Reactor 온도·압력·순서 이상을 종합 검토합니다.

사고·정비 이력
최근 3년간 사망·중대재해 및 대형 화재 없음.
최근 1년간 Hydrogen 공급 Low Pressure 1회, Ammonia Vaporizer High Temperature 1회, IPA Pump Trip 2회, Nitrogen Purge Low Flow 1회, Cooling Loop 유량 저하 1회가 있었음.
공정 정지는 Interlock으로 안전하게 수행되었으며 관련 Sensor, Valve, Pump와 Abatement Fan을 점검함.
```

### Node별 물질 Key-in

```text
Hydrogen Gas Cabinet: Hydrogen, Nitrogen
Hydrogen VMB: Hydrogen, Nitrogen
Ammonia Storage: Ammonia
Ammonia Vaporizer: Ammonia
IPA Day Tank: Isopropyl alcohol
Solvent Distribution: Isopropyl alcohol
Nitrogen Purge Header: Nitrogen
DI Water Cooling Loop: DI Water
Process Reactor: Hydrogen, Ammonia, Isopropyl alcohol, Nitrogen
Abatement 및 Exhaust: Hydrogen, Ammonia, Isopropyl alcohol, Nitrogen
```

---

## 빠른 확인표

| Excel | Maker | Model | 주요 물질 |
|---|---|---|---|
| HAZOP_ColdChain_NH3-Refrigeration.xlsx | ColdChain | NH3-Refrigeration | Ammonia |
| HAZOP_CleanTech_CT-DIW-100.xlsx | CleanTech | CT-DIW-100 | DI Water |
| HAZOP_ASM_Epsilon3200.xlsx | ASM | Epsilon3200 | Silane, Hydrogen, Nitrogen |
| HAZOP_ThermoVac_TV-ETCH-200.xlsx | ThermoVac | TV-ETCH-200 | HF, Nitrogen |
| HAZOP_Solvent_IPA-Supply.xlsx | Solvent | IPA-Supply | Isopropyl alcohol |
| HAZOP_Waterworks_Chlorine-Dosing.xlsx | Waterworks | Chlorine-Dosing | Chlorine |
| HAZOP_Battery_Electrolyte-Mixing.xlsx | Battery | Electrolyte-Mixing | Lithium hexafluorophosphate, Ethylene carbonate, Dimethyl carbonate, Nitrogen |
| HAZOP_Integrated_MultiUtility-Complex.xlsx | Integrated | MultiUtility-Complex | Hydrogen, Ammonia, Isopropyl alcohol, Nitrogen, DI Water |
