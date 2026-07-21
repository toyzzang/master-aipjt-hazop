from __future__ import annotations

import json
import math
import re
from pathlib import Path


INCIDENT_HISTORY_PATH = Path(__file__).resolve().parents[2] / "data" / "incident_history" / "incident_history_samples.json"
_STOP_WORDS = {
    "and", "history", "incident", "maintenance", "reference", "the", "with",
    "이력", "사고", "정비", "조회", "참조",
}


def _search_tokens(value: str) -> set[str]:
    """검색에 의미가 있는 영문·숫자·한글 단어만 뽑습니다."""

    return {
        token
        for token in re.findall(r"[0-9a-zA-Z가-힣]+", value.lower())
        if len(token) > 1 and token not in _STOP_WORDS
    }


def _record_text(record: dict) -> str:
    return " ".join(
        str(value) if not isinstance(value, list) else " ".join(str(item) for item in value)
        for value in record.values()
    )


def lookup_incident_history(query: str) -> dict:
    """Node/물질/Guideword 조합과 관련된 사고이력 근거를 조회합니다.

    별도 DB 대신 PoC에 포함된 JSON 샘플을 실제로 읽어 유사 이력을 찾습니다.
    샘플은 시연용 합성 데이터이며 실제 사업장 사고 통계가 아닙니다.
    """

    if not INCIDENT_HISTORY_PATH.is_file():
        return {
            "query": query,
            "matched_count": 0,
            "frequency_hint": None,
            "evidence": ["로컬 사고·정비 이력 JSON 파일을 찾지 못해 확인 필요입니다."],
            "source": str(INCIDENT_HISTORY_PATH),
        }

    dataset = json.loads(INCIDENT_HISTORY_PATH.read_text(encoding="utf-8"))
    query_tokens = _search_tokens(query)
    ranked: list[tuple[int, dict]] = []
    for record in dataset.get("records", []):
        score = len(query_tokens & _search_tokens(_record_text(record)))
        if score > 0:
            ranked.append((score, record))

    ranked.sort(key=lambda item: item[0], reverse=True)
    # "Leak"처럼 흔한 단어 하나만 겹친 다른 공정 이력이 섞이지 않도록
    # 최고 점수와 비슷한 레코드만 남깁니다.
    highest_score = ranked[0][0] if ranked else 0
    minimum_score = 1 if len(query_tokens) <= 1 else max(2, math.ceil(highest_score * 0.6))
    selected = [record for score, record in ranked if score >= minimum_score][:5]
    if not selected:
        return {
            "query": query,
            "dataset_title": dataset.get("title", "로컬 사고·정비 이력"),
            "data_notice": dataset.get("data_notice", "PoC 합성 샘플"),
            "matched_count": 0,
            "frequency_hint": None,
            "matched_records": [],
            "evidence": ["로컬 사고·정비 이력 저장소에서 검색 조건과 일치하는 샘플을 찾지 못해 확인 필요입니다."],
            "source": str(INCIDENT_HISTORY_PATH),
        }

    frequency_values = [int(record["frequency_hint"]) for record in selected if record.get("frequency_hint") is not None]
    evidence = [
        f"{record.get('record_id')} · {record.get('event_date')} · {record.get('event_type')}: "
        f"{record.get('node')} / {record.get('parameter')} {record.get('guideword')} · "
        f"{record.get('summary')} · 원인={record.get('cause')} · "
        f"영향={record.get('impact')} · 빈도 참고={record.get('frequency_hint')}"
        for record in selected
    ]
    return {
        "query": query,
        "dataset_title": dataset.get("title", "로컬 사고·정비 이력"),
        "data_notice": dataset.get("data_notice", "PoC 합성 샘플"),
        "matched_count": len(selected),
        "frequency_hint": max(frequency_values) if frequency_values else None,
        "matched_records": selected,
        "evidence": evidence,
        "source": str(INCIDENT_HISTORY_PATH),
    }
