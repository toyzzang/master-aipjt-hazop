from __future__ import annotations

from app.services.risk import action_required, calculate_risk_score, risk_level


def calculate_hazop_risk(frequency: int, severity: int) -> dict:
    """범위를 명시적으로 검사한 뒤 위험도를 계산합니다."""

    if not 1 <= frequency <= 5:
        raise ValueError(f"빈도는 1~5 범위여야 합니다: {frequency}")
    if not 1 <= severity <= 4:
        raise ValueError(f"강도는 1~4 범위여야 합니다: {severity}")
    score = calculate_risk_score(frequency, severity)
    return {
        "frequency": frequency,
        "severity": severity,
        "risk_score": score,
        "risk_level": risk_level(score),
        "action_required": action_required(score),
    }
