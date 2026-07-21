from __future__ import annotations

import asyncio

from app.services.msds import fetch_msds_summary_with_trace


def lookup_msds_detail(
    material: str,
    cas_number: str | None = None,
    requested_sections: list[str] | None = None,
) -> dict:
    """초안 작성 중 부족한 물질 정보를 MSDS에서 보완 조회합니다.

    Workflow가 입력 물질 전체를 최초 1회 조회한 뒤에도 상세 유해성, 취급 또는 누출
    대응 정보가 부족할 때 Agent가 선택적으로 호출하는 Tool입니다. 쉽게 말하면 최초
    조회를 대신하는 기능이 아니라, 작성 도중 생긴 추가 질문을 확인하는 기능입니다.
    """

    # DeepAgent는 별도 worker thread에서 동기 `invoke`로 실행됩니다.
    # 따라서 Tool도 동기 진입점을 제공하고 내부의 비동기 MSDS 조회만 여기서 완료합니다.
    lookup = asyncio.run(fetch_msds_summary_with_trace(material))
    summary = lookup.summary
    requested = requested_sections or ["hazards", "handling_storage", "leak_fire_emergency"]
    fallback_used = "내장" in summary.source or "fallback" in summary.source.lower()
    lookup_succeeded = bool(summary.hazards) and not all("확인 필요" in value for value in summary.hazards)
    return {
        "material": summary.material,
        "cas_number": cas_number or "확인 필요",
        "requested_sections": requested,
        "hazards": summary.hazards,
        "handling_storage": summary.handling,
        "leak_fire_emergency": summary.handling,
        "source": summary.source,
        "is_high_hazard": summary.is_high_hazard,
        "hazard_signals": summary.hazard_signals,
        "lookup_succeeded": lookup_succeeded,
        "fallback_used": fallback_used,
        "section_limitations": (
            "현재 PoC MSDS 요약은 취급·저장과 누출·화재·응급조치를 하나의 handling 요약에서 제공합니다. "
            "세부 Section 원문과 CAS 검증은 확인 필요입니다."
        ),
        "lookup_trace": [
            {"title": step.title, "detail": step.detail}
            for step in lookup.steps
        ],
        "usage": "Workflow 최초 조회 이후 Agent 보완 조회",
    }
