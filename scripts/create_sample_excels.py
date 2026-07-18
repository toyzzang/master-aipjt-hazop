from __future__ import annotations

import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLE_DIR = BASE_DIR / "samples"

# 스크립트를 `python3 scripts/create_sample_excels.py`처럼 직접 실행하면
# Python이 프로젝트 루트가 아니라 `scripts/` 폴더만 import 경로로 잡습니다.
sys.path.insert(0, str(BASE_DIR))

from app.services.excel import create_sample_excel


def _node(order: int, name: str) -> dict:
    return {"node_order": order, "node_name": name}


def _guide(order: int, name: str, parameter: str, *guidewords: str) -> list[dict]:
    """같은 Node/변수에 여러 Guideword를 읽기 쉽게 정의합니다."""

    return [
        {"node_order": order, "node_name": name, "parameter": parameter, "guideword": guideword}
        for guideword in guidewords
    ]


# 샘플을 추가할 때 이 목록에 정의 하나만 더하면 생성 스크립트와 구조 테스트가 함께 확장됩니다.
# `materials`와 `purpose`는 Excel 셀에 쓰는 값이 아니라 README/테스트용 설명 정보입니다.
SAMPLE_DEFINITIONS = [
    {
        "filename": "HAZOP_CleanTech_CT-DIW-100.xlsx",
        "purpose": "DI Water 저위험 Utility 기본 케이스",
        "materials": "DI Water",
        "nodes": [_node(1, "DI Water 공급 탱크"), _node(2, "DI Water 이송 펌프"), _node(3, "Wet 장비 공급 배관")],
        "guidewords": [
            *_guide(1, "DI Water 공급 탱크", "Level", "Less", "More"),
            *_guide(2, "DI Water 이송 펌프", "Flow", "No", "Less"),
            *_guide(3, "Wet 장비 공급 배관", "Containment", "Leak"),
        ],
    },
    {
        "filename": "HAZOP_ASM_Epsilon3200.xlsx",
        "purpose": "Silane/Hydrogen/Nitrogen 고위험 Gas 기본 케이스",
        "materials": "Silane, Hydrogen, Nitrogen",
        "nodes": [_node(1, "Gas Cabinet"), _node(2, "VMB 및 공급 배관"), _node(3, "MFC 유량 제어 구간"), _node(4, "Purge 및 Scrubber 구간")],
        "guidewords": [
            *_guide(1, "Gas Cabinet", "Containment", "Leak", "Rupture"),
            *_guide(2, "VMB 및 공급 배관", "Flow", "Reverse"),
            *_guide(3, "MFC 유량 제어 구간", "Flow", "More", "Less"),
            *_guide(4, "Purge 및 Scrubber 구간", "Purge", "No"),
        ],
    },
    {
        "filename": "HAZOP_ThermoVac_TV-ETCH-200.xlsx",
        "purpose": "Vacuum/Etch/Exhaust/HF 복수 Guideword 기본 케이스",
        "materials": "HF, Nitrogen",
        "nodes": [_node(1, "Etch Chamber"), _node(2, "Vacuum Pump Line"), _node(3, "Exhaust Scrubber"), _node(4, "HF Chemical Supply")],
        "guidewords": [
            *_guide(1, "Etch Chamber", "Pressure", "High", "Low"),
            *_guide(2, "Vacuum Pump Line", "Flow", "No", "Reverse"),
            *_guide(3, "Exhaust Scrubber", "Treatment", "Less"),
            *_guide(4, "HF Chemical Supply", "Containment", "Leak"),
        ],
    },
    {
        "filename": "HAZOP_ColdChain_NH3-Refrigeration.xlsx",
        "purpose": "독성·가연성 냉매의 압축/응축/팽창/누출 복합 케이스",
        "materials": "Ammonia",
        "nodes": [_node(1, "NH3 Receiver"), _node(2, "NH3 Compressor"), _node(3, "Oil Separator"), _node(4, "Condenser"), _node(5, "Expansion Valve"), _node(6, "Evaporator 및 Machine Room")],
        "guidewords": [
            *_guide(1, "NH3 Receiver", "Level", "More", "Less"),
            *_guide(1, "NH3 Receiver", "Containment", "Leak", "Rupture"),
            *_guide(2, "NH3 Compressor", "Pressure", "High", "Low"),
            *_guide(2, "NH3 Compressor", "Temperature", "High"),
            *_guide(3, "Oil Separator", "Separation", "Less", "No"),
            *_guide(4, "Condenser", "Cooling", "Less", "No"),
            *_guide(5, "Expansion Valve", "Flow", "More", "Less", "No"),
            *_guide(6, "Evaporator 및 Machine Room", "Containment", "Leak"),
        ],
    },
    {
        "filename": "HAZOP_Solvent_IPA-Supply.xlsx",
        "purpose": "인화성 용제의 하역/저장/이송/회수 및 정전기 점화 케이스",
        "materials": "Isopropyl alcohol",
        "nodes": [_node(1, "IPA Drum Unloading"), _node(2, "IPA Day Tank"), _node(3, "Transfer Pump"), _node(4, "Tool Supply Header"), _node(5, "Waste Solvent Return")],
        "guidewords": [
            *_guide(1, "IPA Drum Unloading", "Containment", "Leak"),
            *_guide(1, "IPA Drum Unloading", "Grounding", "No"),
            *_guide(2, "IPA Day Tank", "Level", "More", "Less"),
            *_guide(2, "IPA Day Tank", "Temperature", "High"),
            *_guide(3, "Transfer Pump", "Flow", "No", "More", "Reverse"),
            *_guide(4, "Tool Supply Header", "Pressure", "High", "Low"),
            *_guide(4, "Tool Supply Header", "Containment", "Leak"),
            *_guide(5, "Waste Solvent Return", "Flow", "No", "Reverse"),
        ],
    },
    {
        "filename": "HAZOP_Waterworks_Chlorine-Dosing.xlsx",
        "purpose": "독성가스 저장·기화·주입과 수처리 과다/과소 투입 케이스",
        "materials": "Chlorine",
        "nodes": [_node(1, "Chlorine Ton Container"), _node(2, "Evaporator"), _node(3, "Vacuum Regulator"), _node(4, "Chlorinator"), _node(5, "Injector 및 Contact Basin"), _node(6, "Emergency Scrubber")],
        "guidewords": [
            *_guide(1, "Chlorine Ton Container", "Containment", "Leak", "Rupture"),
            *_guide(2, "Evaporator", "Temperature", "High", "Low"),
            *_guide(2, "Evaporator", "Pressure", "High"),
            *_guide(3, "Vacuum Regulator", "Vacuum", "No", "Less"),
            *_guide(4, "Chlorinator", "Dose", "More", "Less", "No"),
            *_guide(5, "Injector 및 Contact Basin", "Flow", "Reverse", "No"),
            *_guide(6, "Emergency Scrubber", "Treatment", "Less", "No"),
        ],
    },
    {
        "filename": "HAZOP_Battery_Electrolyte-Mixing.xlsx",
        "purpose": "가연성 전해액의 혼합·가열·질소봉입·충전 복합 케이스",
        "materials": "Lithium hexafluorophosphate, Ethylene carbonate, Dimethyl carbonate, Nitrogen",
        "nodes": [_node(1, "Solvent Storage"), _node(2, "LiPF6 Charging Booth"), _node(3, "Mixing Reactor"), _node(4, "Heating/Cooling Jacket"), _node(5, "Nitrogen Blanketing"), _node(6, "Filtration"), _node(7, "Filling Line")],
        "guidewords": [
            *_guide(1, "Solvent Storage", "Containment", "Leak"),
            *_guide(1, "Solvent Storage", "Temperature", "High"),
            *_guide(2, "LiPF6 Charging Booth", "Moisture", "More"),
            *_guide(2, "LiPF6 Charging Booth", "Containment", "Leak"),
            *_guide(3, "Mixing Reactor", "Agitation", "No", "Less", "More"),
            *_guide(3, "Mixing Reactor", "Addition", "More", "Less", "Reverse"),
            *_guide(4, "Heating/Cooling Jacket", "Temperature", "High", "Low"),
            *_guide(5, "Nitrogen Blanketing", "Pressure", "High", "Low"),
            *_guide(5, "Nitrogen Blanketing", "Flow", "No"),
            *_guide(6, "Filtration", "Differential Pressure", "High"),
            *_guide(6, "Filtration", "Flow", "No"),
            *_guide(7, "Filling Line", "Containment", "Leak"),
            *_guide(7, "Filling Line", "Grounding", "No"),
        ],
    },
    {
        "filename": "HAZOP_Integrated_MultiUtility-Complex.xlsx",
        "purpose": "여러 위험물질과 Utility가 상호작용하는 대형 통합 복합 케이스",
        "materials": "Hydrogen, Ammonia, Isopropyl alcohol, Nitrogen, DI Water",
        "nodes": [_node(1, "Hydrogen Gas Cabinet"), _node(2, "Hydrogen VMB"), _node(3, "Ammonia Storage"), _node(4, "Ammonia Vaporizer"), _node(5, "IPA Day Tank"), _node(6, "Solvent Distribution"), _node(7, "Nitrogen Purge Header"), _node(8, "DI Water Cooling Loop"), _node(9, "Process Reactor"), _node(10, "Abatement 및 Exhaust")],
        "guidewords": [
            *_guide(1, "Hydrogen Gas Cabinet", "Containment", "Leak", "Rupture"),
            *_guide(1, "Hydrogen Gas Cabinet", "Pressure", "High", "Low"),
            *_guide(2, "Hydrogen VMB", "Flow", "More", "Less", "No", "Reverse"),
            *_guide(3, "Ammonia Storage", "Level", "More", "Less"),
            *_guide(3, "Ammonia Storage", "Containment", "Leak"),
            *_guide(4, "Ammonia Vaporizer", "Temperature", "High", "Low"),
            *_guide(4, "Ammonia Vaporizer", "Pressure", "High"),
            *_guide(5, "IPA Day Tank", "Level", "More", "Less"),
            *_guide(5, "IPA Day Tank", "Grounding", "No"),
            *_guide(6, "Solvent Distribution", "Flow", "No", "Reverse"),
            *_guide(6, "Solvent Distribution", "Containment", "Leak"),
            *_guide(7, "Nitrogen Purge Header", "Flow", "No", "Less"),
            *_guide(8, "DI Water Cooling Loop", "Cooling", "No", "Less"),
            *_guide(9, "Process Reactor", "Temperature", "High", "Low"),
            *_guide(9, "Process Reactor", "Pressure", "High", "Low"),
            *_guide(9, "Process Reactor", "Sequence", "Early", "Late"),
            *_guide(10, "Abatement 및 Exhaust", "Treatment", "No", "Less"),
            *_guide(10, "Abatement 및 Exhaust", "Flow", "Reverse"),
        ],
    },
]


def main() -> None:
    """다양한 HAZOP 입력 샘플을 만들되 결과 Sheet는 빈 상태로 둡니다."""

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    for sample in SAMPLE_DEFINITIONS:
        create_sample_excel(SAMPLE_DIR / sample["filename"], sample["nodes"], sample["guidewords"])

    print(f"샘플 Excel {len(SAMPLE_DEFINITIONS)}개를 생성했습니다: {SAMPLE_DIR}")


if __name__ == "__main__":
    main()
