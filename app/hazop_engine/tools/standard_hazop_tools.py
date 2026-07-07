from __future__ import annotations


def lookup_standard_hazop(reference_id: str, query: str) -> dict:
    """표준공정위험성평가서에서 유사 항목을 조회합니다.

    1차 구현에서는 실제 문서 저장소가 없으므로 참조 ID와 데이터 부족 근거를 반환합니다.
    """

    if not reference_id:
        return {
            "reference_id": "",
            "query": query,
            "matched_count": 0,
            "evidence": ["사용자가 표준공정위험성평가서 Link 또는 ID를 제공하지 않았습니다."],
        }
    return {
        "reference_id": reference_id,
        "query": query,
        "matched_count": 0,
        "evidence": [
            f"표준공정위험성평가서 참조값({reference_id})은 입력되었지만, 현재 PoC에는 실제 문서 조회 인덱스가 없어 확인 필요입니다."
        ],
    }
