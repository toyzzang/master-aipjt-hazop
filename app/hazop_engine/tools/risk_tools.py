from __future__ import annotations

from app.services.risk import action_required, calculate_risk_score, clamp_frequency, clamp_severity, risk_level


def calculate_hazop_risk(frequency: int, severity: int) -> dict:
    """빈도와 강도를 시스템 기준으로 보정하고 위험도를 계산합니다."""

    checked_frequency = clamp_frequency(frequency)
    checked_severity = clamp_severity(severity)
    score = calculate_risk_score(checked_frequency, checked_severity)
    return {
        "frequency": checked_frequency,
        "severity": checked_severity,
        "risk_score": score,
        "risk_level": risk_level(score),
        "action_required": action_required(score),
    }
