from __future__ import annotations


def calculate_risk_score(frequency: int, severity: int) -> int:
    """위험도를 계산합니다.

    중요한 설계 원칙:
    - AI가 위험도 점수를 마음대로 쓰면 기준이 흔들릴 수 있습니다.
    - 그래서 AI는 빈도/강도 "후보"만 제안하고, 점수 계산은 이 함수가 합니다.
    """

    return frequency * severity


def clamp_frequency(value: int) -> int:
    """빈도는 사용자 기준에 따라 1~5 사이로 제한합니다."""

    return max(1, min(5, int(value)))


def clamp_severity(value: int) -> int:
    """강도는 사용자 기준에 따라 1~4 사이로 제한합니다."""

    return max(1, min(4, int(value)))


def risk_level(score: int) -> str:
    """사용자가 제공한 위험도 기준표를 사람이 읽기 쉬운 등급으로 바꿉니다."""

    if 1 <= score <= 3:
        return "무시할 수 있는 위험"
    if 4 <= score <= 6:
        return "미미한 위험"
    if score == 8:
        return "경미한 위험"
    if 9 <= score <= 11:
        return "상당한 위험"
    if 12 <= score <= 15:
        return "중대한 위험"
    if 16 <= score <= 20:
        return "허용불가 위험"
    return "확인 필요"


def action_required(score: int) -> str:
    """위험도 9 이상이면 반드시 감소 대책이 필요하다는 기준을 적용합니다."""

    return "필요" if score >= 9 else "불필요"
