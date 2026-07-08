import asyncio

from app.hazop_engine.context import HazopDraftContext
from app.hazop_engine.tools.validation_tools import parse_risk_rows
from app.hazop_engine.workflow import _describe_deepagent_exception, generate_hazop_draft
from app.schemas.hazop import GuidewordRow, HazopInput, NodeRow
from app.services.msds import MsdsSummary


def test_parse_risk_rows_rejects_new_guideword():
    guidewords = [GuidewordRow(node_order=1, node_name="Gas Cabinet", parameter="Containment", guideword="Leak")]
    data = {
        "risk_rows": [
            {
                "no": 1,
                "node_order": 1,
                "node_name": "Gas Cabinet",
                "parameter": "Flow",
                "guideword": "More",
                "deviation": "임의 생성",
                "cause": "임의 생성",
                "consequence": "임의 생성",
                "existing_safeguard": "임의 생성",
                "frequency": 2,
                "severity": 3,
                "risk_score": 0,
                "risk_level": "계산 전",
                "action_required": "계산 전",
            }
        ]
    }

    try:
        parse_risk_rows(data, guidewords)
    except ValueError as exc:
        assert "입력 Excel에 없는" in str(exc)
    else:
        raise AssertionError("입력에 없는 Guideword 조합을 거부해야 합니다.")


def test_generate_hazop_draft_demo_fallback(monkeypatch):
    for name in [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_API_VERSION",
        "AZURE_OPENAI_DEPLOYMENT",
    ]:
        monkeypatch.delenv(name, raising=False)

    context = HazopDraftContext(
        input_data=HazopInput(maker="ASM", model="Epsilon3200", materials="Silane"),
        nodes=[NodeRow(node_order=1, node_name="Gas Cabinet")],
        guidewords=[GuidewordRow(node_order=1, node_name="Gas Cabinet", parameter="Containment", guideword="Leak")],
        msds_context={
            "silane": MsdsSummary(
                material="Silane",
                hazards=["공기 중 자연발화 가능"],
                handling=["Gas Detector", "긴급차단밸브"],
                source="test",
            )
        },
    )

    result = asyncio.run(generate_hazop_draft(context))

    assert result.mode == "demo"
    assert result.risk_rows[0].risk_score == 12
    assert result.risk_rows[0].action_required == "필요"
    assert len(result.action_rows) == 1


def test_describe_deepagent_connection_error(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_VERIFY_SSL", "false")

    reason = _describe_deepagent_exception(RuntimeError("Connection error."))

    assert "Azure OpenAI 연결 단계" in reason
    assert "AZURE_OPENAI_ENDPOINT" in reason
    assert "AZURE_OPENAI_DEPLOYMENT" in reason
    assert "AZURE_OPENAI_VERIFY_SSL=false" in reason
