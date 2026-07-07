from __future__ import annotations

from app.schemas.hazop import ActionPlanRow, GuidewordRow, RiskAssessmentRow


def validate_risk_rows_against_guidewords(rows: list[RiskAssessmentRow], guidewords: list[GuidewordRow]) -> None:
    """AI가 입력 Excel에 없는 평가 조합을 만들었는지 검사합니다."""

    allowed = {(item.node_order, item.node_name, item.parameter, item.guideword) for item in guidewords}
    invalid = [
        f"{row.node_order}/{row.node_name}/{row.parameter}/{row.guideword}"
        for row in rows
        if (row.node_order, row.node_name, row.parameter, row.guideword) not in allowed
    ]
    if invalid:
        raise ValueError(f"입력 Excel에 없는 Node/변수/Guideword 조합이 생성되었습니다: {', '.join(invalid)}")


def parse_risk_rows(data: object, guidewords: list[GuidewordRow]) -> list[RiskAssessmentRow]:
    rows = [RiskAssessmentRow.model_validate(item) for item in _extract_rows(data, "risk_rows")]
    validate_risk_rows_against_guidewords(rows, guidewords)
    return rows


def parse_action_rows(data: object) -> list[ActionPlanRow]:
    return [ActionPlanRow.model_validate(item) for item in _extract_rows(data, "action_rows")]


def _extract_rows(data: object, expected_key: str) -> list:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        raise TypeError(f"JSON object 또는 array가 필요하지만 {type(data).__name__}를 받았습니다.")
    if expected_key in data and isinstance(data[expected_key], list):
        return data[expected_key]
    if "structured_response" in data:
        return _extract_rows(data["structured_response"], expected_key)
    for fallback_key in ["rows", "data", "items", "results"]:
        if fallback_key in data and isinstance(data[fallback_key], list):
            return data[fallback_key]
    raise KeyError(expected_key)
