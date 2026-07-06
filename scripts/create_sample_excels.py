from __future__ import annotations

import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLE_DIR = BASE_DIR / "samples"

# 스크립트를 `python scripts/create_sample_excels.py`처럼 직접 실행하면
# Python이 프로젝트 루트가 아니라 `scripts/` 폴더만 import 경로로 잡습니다.
# 그래서 `app.services...`를 찾을 수 있게 프로젝트 루트를 한 번 추가합니다.
sys.path.insert(0, str(BASE_DIR))

from app.services.excel import create_sample_excel


def main() -> None:
    """요구사항에 맞는 샘플 Excel 3개를 생성합니다.

    모든 샘플은 `#1 노드리스트`, `#2 가이드워드`만 데이터가 있고,
    `#3 위험성평가`, `#4 조치계획서`는 헤더만 둔 빈 상태입니다.
    """

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

    create_sample_excel(
        SAMPLE_DIR / "HAZOP_CleanTech_CT-DIW-100.xlsx",
        nodes=[
            {"node_order": 1, "node_name": "DI Water 공급 탱크"},
            {"node_order": 2, "node_name": "DI Water 이송 펌프"},
            {"node_order": 3, "node_name": "Wet 장비 공급 배관"},
        ],
        guidewords=[
            {"node_order": 1, "node_name": "DI Water 공급 탱크", "parameter": "Level", "guideword": "Less"},
            {"node_order": 1, "node_name": "DI Water 공급 탱크", "parameter": "Level", "guideword": "More"},
            {"node_order": 2, "node_name": "DI Water 이송 펌프", "parameter": "Flow", "guideword": "No"},
            {"node_order": 2, "node_name": "DI Water 이송 펌프", "parameter": "Flow", "guideword": "Less"},
            {"node_order": 3, "node_name": "Wet 장비 공급 배관", "parameter": "Containment", "guideword": "Leak"},
        ],
    )

    create_sample_excel(
        SAMPLE_DIR / "HAZOP_ASM_Epsilon3200.xlsx",
        nodes=[
            {"node_order": 1, "node_name": "Gas Cabinet"},
            {"node_order": 2, "node_name": "VMB 및 공급 배관"},
            {"node_order": 3, "node_name": "MFC 유량 제어 구간"},
            {"node_order": 4, "node_name": "Purge 및 Scrubber 구간"},
        ],
        guidewords=[
            {"node_order": 1, "node_name": "Gas Cabinet", "parameter": "Containment", "guideword": "Leak"},
            {"node_order": 1, "node_name": "Gas Cabinet", "parameter": "Containment", "guideword": "Rupture"},
            {"node_order": 2, "node_name": "VMB 및 공급 배관", "parameter": "Flow", "guideword": "Reverse"},
            {"node_order": 3, "node_name": "MFC 유량 제어 구간", "parameter": "Flow", "guideword": "More"},
            {"node_order": 3, "node_name": "MFC 유량 제어 구간", "parameter": "Flow", "guideword": "Less"},
            {"node_order": 4, "node_name": "Purge 및 Scrubber 구간", "parameter": "Purge", "guideword": "No"},
        ],
    )

    create_sample_excel(
        SAMPLE_DIR / "HAZOP_ThermoVac_TV-ETCH-200.xlsx",
        nodes=[
            {"node_order": 1, "node_name": "Etch Chamber"},
            {"node_order": 2, "node_name": "Vacuum Pump Line"},
            {"node_order": 3, "node_name": "Exhaust Scrubber"},
            {"node_order": 4, "node_name": "HF Chemical Supply"},
        ],
        guidewords=[
            {"node_order": 1, "node_name": "Etch Chamber", "parameter": "Pressure", "guideword": "High"},
            {"node_order": 1, "node_name": "Etch Chamber", "parameter": "Pressure", "guideword": "Low"},
            {"node_order": 2, "node_name": "Vacuum Pump Line", "parameter": "Flow", "guideword": "No"},
            {"node_order": 2, "node_name": "Vacuum Pump Line", "parameter": "Flow", "guideword": "Reverse"},
            {"node_order": 3, "node_name": "Exhaust Scrubber", "parameter": "Treatment", "guideword": "Less"},
            {"node_order": 4, "node_name": "HF Chemical Supply", "parameter": "Containment", "guideword": "Leak"},
        ],
    )

    print(f"샘플 Excel 3개를 생성했습니다: {SAMPLE_DIR}")


if __name__ == "__main__":
    main()
