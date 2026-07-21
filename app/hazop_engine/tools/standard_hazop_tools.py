from __future__ import annotations

import json
import re
from pathlib import Path


STANDARD_HAZOP_DIR = Path(__file__).resolve().parents[2] / "data" / "standard_hazop"


def _search_tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[0-9a-zA-Z가-힣]+", value.lower()) if len(token) > 1}


def _row_text(row: dict) -> str:
    return " ".join(
        str(value) if not isinstance(value, list) else " ".join(str(item) for item in value)
        for value in row.values()
    )


def lookup_standard_hazop(reference_id: str, query: str) -> dict:
    """표준공정위험성평가서에서 유사 항목을 조회합니다.

    PoC에 포함된 JSON 표준문서를 reference_id로 찾고 query와 가까운 Row를 반환합니다.
    파일 기반이라 별도 DB 설치 없이도 실제 조회·Context 전달 과정을 재현할 수 있습니다.
    """

    if not reference_id:
        return {
            "reference_id": "",
            "query": query,
            "matched_count": 0,
            "evidence": ["사용자가 표준공정위험성평가서 Link 또는 ID를 제공하지 않았습니다."],
        }
    document_path = STANDARD_HAZOP_DIR / f"{reference_id}.json"
    if not document_path.is_file():
        return {
            "reference_id": reference_id,
            "query": query,
            "matched_count": 0,
            "evidence": [f"로컬 표준 HAZOP 저장소에서 reference_id={reference_id} 문서를 찾지 못했습니다."],
            "source": str(document_path),
        }

    document = json.loads(document_path.read_text(encoding="utf-8"))
    query_tokens = _search_tokens(query)
    ranked: list[tuple[int, dict]] = []
    for row in document.get("rows", []):
        score = len(query_tokens & _search_tokens(_row_text(row)))
        ranked.append((score, row))
    positive = [item for item in sorted(ranked, key=lambda item: item[0], reverse=True) if item[0] > 0]
    selected = [row for _, row in (positive[:5] if positive else ranked[:3])]
    evidence = [
        f"{row.get('node')} · {row.get('parameter')}/{row.get('guideword')}: "
        f"원인={row.get('cause')} / 결과={row.get('consequence')} / "
        f"안전조치={', '.join(row.get('safeguards', []))} / "
        f"참조 빈도={row.get('frequency_reference')}, 강도={row.get('severity_reference')}"
        for row in selected
    ]
    return {
        "reference_id": reference_id,
        "query": query,
        "document_title": document.get("title", reference_id),
        "revision": document.get("revision", "확인 필요"),
        "matched_count": len(selected),
        "matched_rows": selected,
        "evidence": evidence,
        "source": str(document_path),
    }
