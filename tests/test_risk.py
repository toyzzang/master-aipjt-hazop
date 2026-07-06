from app.services.risk import action_required, calculate_risk_score, risk_level


def test_calculate_risk_score():
    assert calculate_risk_score(3, 4) == 12


def test_action_required_from_9():
    assert action_required(8) == "불필요"
    assert action_required(9) == "필요"


def test_risk_level():
    assert risk_level(3) == "무시할 수 있는 위험"
    assert risk_level(6) == "미미한 위험"
    assert risk_level(8) == "경미한 위험"
    assert risk_level(10) == "상당한 위험"
    assert risk_level(12) == "중대한 위험"
    assert risk_level(16) == "허용불가 위험"
