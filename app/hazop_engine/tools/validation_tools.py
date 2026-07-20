from __future__ import annotations

from collections import Counter

from app.schemas.hazop import ActionPlanRow, GuidewordRow, RiskAssessmentRow, RiskCriteria
from app.services.risk import action_required, calculate_risk_score, risk_level


def validate_risk_rows_against_guidewords(rows: list[RiskAssessmentRow], guidewords: list[GuidewordRow]) -> None:
    """AI 결과가 입력 평가 조합과 개수까지 정확히 일치하는지 검사합니다."""

    expected = Counter(_guideword_key(item) for item in guidewords)
    actual = Counter(_risk_key(row) for row in rows)
    if expected == actual:
        return

    missing = list((expected - actual).elements())
    unexpected = list((actual - expected).elements())
    details: list[str] = []
    if len(rows) != len(guidewords):
        details.append(f"Row 개수 불일치(입력 {len(guidewords)}건, 결과 {len(rows)}건)")
    if missing:
        details.append("누락: " + ", ".join(_format_key(key) for key in missing))
    if unexpected:
        details.append("입력 Excel에 없는 조합: " + ", ".join(_format_key(key) for key in unexpected))
    raise ValueError("입력 Excel의 Node/변수/Guideword와 결과가 일치하지 않습니다. " + "; ".join(details))


def validate_and_calculate_risk_rows(
    rows: list[RiskAssessmentRow],
    guidewords: list[GuidewordRow],
    criteria: RiskCriteria | None = None,
) -> list[RiskAssessmentRow]:
    """정답이 분명한 검증과 위험도 계산을 AI 대신 시스템 코드가 수행합니다."""

    validate_risk_rows_against_guidewords(rows, guidewords)
    row_numbers = [row.no for row in rows]
    if len(set(row_numbers)) != len(row_numbers):
        raise ValueError("위험성평가 Row의 no가 중복되었습니다.")

    calculated: list[RiskAssessmentRow] = []
    for row in rows:
        if not 1 <= row.frequency <= 5:
            raise ValueError(f"위험성평가 {row.no}번 빈도는 1~5 범위여야 합니다: {row.frequency}")
        if not 1 <= row.severity <= 4:
            raise ValueError(f"위험성평가 {row.no}번 강도는 1~4 범위여야 합니다: {row.severity}")
        _require_evidence(row.no, "판단근거", row.decision_evidence)
        _require_evidence(row.no, "빈도근거", row.frequency_evidence)
        _require_evidence(row.no, "강도근거", row.severity_evidence)

        score = calculate_risk_score(row.frequency, row.severity)
        calculated.append(
            row.model_copy(
                update={
                    "risk_score": score,
                    "risk_level": _risk_level_from_criteria(score, criteria),
                    "action_required": action_required(score),
                }
            )
        )
    return calculated


def validate_and_calculate_action_rows(
    rows: list[ActionPlanRow],
    high_risk_rows: list[RiskAssessmentRow],
) -> list[ActionPlanRow]:
    """조치계획이 시스템이 선별한 고위험 Row와 정확히 연결되는지 확인합니다."""

    expected = Counter(row.no for row in high_risk_rows)
    actual = Counter(row.risk_assessment_no for row in rows)
    if expected != actual:
        missing = list((expected - actual).elements())
        unexpected = list((actual - expected).elements())
        raise ValueError(
            "조치계획 대상이 위험도 9 이상 선별 결과와 일치하지 않습니다. "
            f"누락={missing}, 잘못된 참조={unexpected}"
        )

    calculated: list[ActionPlanRow] = []
    for row in rows:
        if not 1 <= row.after_frequency <= 5:
            raise ValueError(f"조치계획 {row.no}번 조치 후 빈도는 1~5 범위여야 합니다.")
        if not 1 <= row.after_severity <= 4:
            raise ValueError(f"조치계획 {row.no}번 조치 후 강도는 1~4 범위여야 합니다.")
        _require_evidence(row.no, "조치계획 근거", row.evidence)
        calculated.append(
            row.model_copy(
                update={
                    "after_risk_score": calculate_risk_score(row.after_frequency, row.after_severity),
                }
            )
        )
    return calculated


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


def _guideword_key(item: GuidewordRow) -> tuple[int, str, str, str]:
    return item.node_order, item.node_name, item.parameter, item.guideword


def _risk_key(row: RiskAssessmentRow) -> tuple[int, str, str, str]:
    return row.node_order, row.node_name, row.parameter, row.guideword


def _format_key(key: tuple[int, str, str, str]) -> str:
    return "/".join(str(value) for value in key)


def _require_evidence(row_no: int, label: str, evidence: list) -> None:
    if not evidence or not any(getattr(item, "reason", "").strip() for item in evidence):
        raise ValueError(f"위험성평가/조치계획 {row_no}번의 {label}가 비어 있습니다.")


def _risk_level_from_criteria(score: int, criteria: RiskCriteria | None) -> str:
    if criteria is not None:
        for item in criteria.items:
            if item.category == "위험도" and _score_matches(score, item.score):
                return item.description.split(" - ", 1)[0].strip()
    return risk_level(score)


def _score_matches(score: int, criterion_score: str) -> bool:
    normalized = criterion_score.strip().replace("～", "~")
    if "~" in normalized:
        start, end = normalized.split("~", 1)
        return int(start) <= score <= int(end)
    return score == int(normalized)
