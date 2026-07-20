from app.services.risk import action_required, calculate_risk_score, risk_level
from app.hazop_engine.tools.risk_tools import calculate_hazop_risk


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


def test_agent_risk_tool_rejects_out_of_range_instead_of_clamping():
    for frequency, severity in [(0, 4), (6, 4), (3, 0), (3, 5)]:
        try:
            calculate_hazop_risk(frequency, severity)
        except ValueError:
            pass
        else:
            raise AssertionError("범위 밖 빈도·강도를 조용히 보정하면 안 됩니다.")
