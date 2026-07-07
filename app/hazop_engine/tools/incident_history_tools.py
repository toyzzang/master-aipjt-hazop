from __future__ import annotations


def lookup_incident_history(query: str) -> dict:
    """Node/물질/Guideword 조합과 관련된 사고이력 근거를 조회합니다.

    현재 PoC에는 실제 사고이력 DB가 없으므로 빈 결과를 명시적으로 반환합니다.
    """

    return {
        "query": query,
        "matched_count": 0,
        "frequency_hint": None,
        "evidence": ["현재 PoC에는 사고이력 DB가 연결되어 있지 않아 기존 사고이력 근거는 확인 필요입니다."],
    }
