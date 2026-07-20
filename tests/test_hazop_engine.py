import asyncio

from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import _check_fs_permission
from deepagents.middleware.skills import _list_skills
from pydantic import ValidationError

from app.hazop_engine.agents.deepagent_factory import _filesystem_permissions, _skill_paths
from app.hazop_engine.context import AgentTrace, EngineEvent, HazopDraftContext
from app.hazop_engine.planning import build_execution_plan, plan_prompt
from app.hazop_engine.tools.validation_tools import parse_risk_rows, validate_and_calculate_risk_rows
from app.hazop_engine.workflow import _describe_deepagent_exception, generate_hazop_draft
from app.schemas.hazop import (
    ActionPlanRow,
    AgentEvidence,
    GuidewordRow,
    HazopInput,
    NodeRow,
    ReviewFinding,
    RiskAssessmentRow,
    RiskCriteria,
    RiskCriterion,
)
from app.services.msds import MsdsLookupResult, MsdsSummary


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
                "decision_evidence": [{"reason": "test", "source": "test"}],
                "severity_evidence": [{"reason": "test", "source": "test"}],
                "frequency_evidence": [{"reason": "test", "source": "test"}],
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
    titles = [event.title for event in result.events]
    assert "Deepagent HAZOP Engine을 준비했습니다." not in titles
    assert "risk-draft-agent demo fallback을 실행합니다." in titles
    assert "risk-review-agent AI 의미 검토를 실행하지 못했습니다." in titles
    assert "action-plan-agent demo fallback을 실행합니다." in titles


def test_plan_compares_limited_strategies_and_applies_selected_strategy():
    context = HazopDraftContext(
        input_data=HazopInput(
            maker="ASM",
            model="Epsilon3200",
            materials="Silane",
            standard_hazop_link="STD-SILANE-001",
            incident_maintenance_history="최근 1년 누출 경보 1회",
        ),
        nodes=[NodeRow(node_order=1, node_name="Gas Cabinet")],
        guidewords=[GuidewordRow(node_order=1, node_name="Gas Cabinet", parameter="Containment", guideword="Leak")],
        msds_context={
            "silane": MsdsSummary(
                material="Silane",
                hazards=["공기 중 자연발화 가능"],
                handling=["긴급차단밸브"],
                source="test",
            )
        },
    )

    plan = build_execution_plan(context)
    context.execution_plan = plan

    assert len(plan.steps) == 5
    assert [candidate.candidate_id for candidate in plan.candidates] == ["A", "B", "C"]
    assert plan.selected_candidate_id == "A"
    assert "고위험 물질 신호 발견" in plan.selected_candidate().observed_conditions
    assert not hasattr(plan.selected_candidate(), "score")
    prompt = plan_prompt(context)
    assert plan.plan_id in prompt
    assert "MSDS 우선 + 사고이력 보완" in prompt
    assert "근거 우선순위: MSDS → 사용자 사고·정비 이력 → 표준 HAZOP" in prompt
    assert "lookup_incident_history" in prompt


def test_plan_selection_changes_with_available_evidence():
    common = {
        "nodes": [NodeRow(node_order=1, node_name="DI Water 공급 탱크")],
        "guidewords": [GuidewordRow(node_order=1, node_name="DI Water 공급 탱크", parameter="Flow", guideword="No")],
        "msds_context": {
            "water": MsdsSummary(material="DI Water", hazards=["고유해성 낮음"], handling=["누수 관리"], source="test")
        },
    }
    history_context = HazopDraftContext(
        input_data=HazopInput(
            maker="CleanTech",
            model="CT-DIW-100",
            materials="DI Water",
            incident_maintenance_history="최근 1년 펌프 정지 3회",
        ),
        **common,
    )
    standard_context = HazopDraftContext(
        input_data=HazopInput(
            maker="CleanTech",
            model="CT-DIW-100",
            materials="DI Water",
            standard_hazop_link="STD-DIW-001",
        ),
        **common,
    )

    assert build_execution_plan(history_context).selected_candidate_id == "B"
    assert build_execution_plan(standard_context).selected_candidate_id == "C"


def test_describe_deepagent_connection_error(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_VERIFY_SSL", "false")

    reason = _describe_deepagent_exception(RuntimeError("Connection error."))

    assert "Azure OpenAI 연결 단계" in reason
    assert "AZURE_OPENAI_ENDPOINT" in reason
    assert "AZURE_OPENAI_DEPLOYMENT" in reason
    assert "AZURE_OPENAI_VERIFY_SSL=false" in reason


def test_deepagent_discovers_all_hazop_skills():
    skill_root = _skill_paths()[0]
    backend = FilesystemBackend(root_dir="/", virtual_mode=False)

    skills = _list_skills(backend, skill_root)
    names = {skill["name"] for skill in skills}

    assert names == {
        "frequency-estimation",
        "hazop-action-plan",
        "hazop-risk-draft",
        "hazop-risk-review",
        "incident-history-analysis",
        "severity-estimation",
        "standard-hazop-comparison",
        "standard-hazop-reference",
    }
    permissions = _filesystem_permissions()
    assert permissions[0].operations == ["read"]
    assert permissions[0].paths == [f"{skill_root}/**"]
    assert permissions[0].mode == "allow"
    assert permissions[1].mode == "deny"
    assert permissions[2].operations == ["write"]
    assert _check_fs_permission(permissions, "read", f"{skill_root}/severity-estimation/SKILL.md") == "allow"
    assert _check_fs_permission(permissions, "read", "/project/.env") == "deny"
    assert _check_fs_permission(permissions, "write", f"{skill_root}/severity-estimation/SKILL.md") == "deny"


def test_deepagent_factory_uses_local_filesystem_backend(monkeypatch):
    import deepagents
    import app.hazop_engine.agents.deepagent_factory as factory

    captured = {}

    monkeypatch.setattr(factory, "_azure_chat_model", lambda: object())
    monkeypatch.setattr(factory, "_prepare_azure_langchain_env", lambda: None)
    monkeypatch.setattr(factory, "_apply_filesystem_lockdown", lambda: None)
    monkeypatch.setattr(deepagents, "create_deep_agent", lambda **kwargs: captured.update(kwargs) or "agent")

    result = factory.create_hazop_deep_agent(
        tools=[],
        system_prompt="test",
        response_format=dict,
        agent_name="risk-review-agent",
    )

    assert result == "agent"
    assert isinstance(captured["backend"], FilesystemBackend)
    assert captured["skills"] == _skill_paths()
    assert captured["permissions"] == _filesystem_permissions()
    assert captured["name"] == "risk-review-agent"


def test_system_validation_rejects_missing_row_and_out_of_range():
    guidewords = [
        GuidewordRow(node_order=1, node_name="Gas Cabinet", parameter="Containment", guideword="Leak"),
        GuidewordRow(node_order=1, node_name="Gas Cabinet", parameter="Flow", guideword="No"),
    ]
    row = _risk_row(severity=4)

    try:
        validate_and_calculate_risk_rows([row], guidewords)
    except ValueError as exc:
        assert "Row 개수 불일치" in str(exc)
    else:
        raise AssertionError("입력 Guideword보다 결과 Row가 적으면 거부해야 합니다.")

    try:
        validate_and_calculate_risk_rows([row.model_copy(update={"severity": 5})], guidewords[:1])
    except ValueError as exc:
        assert "강도는 1~4" in str(exc)
    else:
        raise AssertionError("강도 범위를 벗어나면 clamp하지 말고 거부해야 합니다.")

    try:
        _risk_row(severity=5)
    except ValidationError as exc:
        assert "less than or equal to 4" in str(exc)
    else:
        raise AssertionError("Pydantic 스키마도 강도 5를 거부해야 합니다.")

    calculated = validate_and_calculate_risk_rows([row], guidewords[:1], _criteria())
    assert calculated[0].risk_level == "테스트 위험"


def test_risk_schema_rejects_empty_required_evidence():
    data = _risk_row(severity=4).model_dump()
    data["severity_evidence"] = []

    try:
        RiskAssessmentRow.model_validate(data)
    except ValidationError as exc:
        assert "severity_evidence" in str(exc)
        assert "at least 1 item" in str(exc)
    else:
        raise AssertionError("필수 강도근거가 비어 있으면 스키마 검증이 실패해야 합니다.")


def test_independent_review_result_is_reflected_before_action_plan(monkeypatch):
    import app.hazop_engine.workflow as workflow

    context = HazopDraftContext(
        input_data=HazopInput(maker="ASM", model="Epsilon3200", materials="Silane"),
        nodes=[NodeRow(node_order=1, node_name="Gas Cabinet")],
        guidewords=[GuidewordRow(node_order=1, node_name="Gas Cabinet", parameter="Containment", guideword="Leak")],
        msds_context={
            "silane": MsdsSummary(
                material="Silane",
                hazards=["공기 중 자연발화 가능"],
                handling=["긴급차단밸브"],
                source="test",
            )
        },
    )
    calls: list[str] = []

    monkeypatch.setattr(workflow, "azure_openai_configured", lambda: True)

    async def fake_draft(_context, _events=None, _progress=None):
        calls.append("draft")
        assert _context.execution_plan is not None
        assert len(_context.execution_plan.steps) == 5
        return [_risk_row(severity=2)], []

    async def fake_review(_context, checked_rows, _events=None, _progress=None):
        calls.append("review")
        assert checked_rows[0].risk_score == 6
        reviewed = checked_rows[0].model_copy(
            update={
                "severity": 4,
                "risk_score": 0,
                "risk_level": "계산 전",
                "action_required": "계산 전",
                "severity_evidence": [
                    AgentEvidence(
                        reason="Silane 자연발화 누출은 사망 가능 중대재해 영향이므로 강도 4입니다.",
                        source="severity-estimation + MSDS",
                    )
                ],
            }
        )
        return [reviewed], [
            ReviewFinding(
                risk_assessment_no=1,
                category="강도 과소평가",
                message="Silane 누출 강도 2는 낮습니다.",
                resolution="강도 4와 MSDS 근거로 보완했습니다.",
                requires_confirmation=True,
            )
        ], []

    async def fake_action(_context, high_risk_rows, _events=None, _progress=None):
        calls.append("action")
        assert high_risk_rows[0].severity == 4
        assert high_risk_rows[0].risk_score == 12
        return [
            ActionPlanRow(
                no=1,
                risk_assessment_no=1,
                node_name="Gas Cabinet",
                recommendation="누설 감지와 긴급차단 인터록을 검증한다.",
                after_frequency=1,
                after_severity=4,
                after_risk_score=0,
                evidence=[AgentEvidence(reason="누출 발생 가능성을 낮춥니다.", source="review")],
            )
        ], []

    monkeypatch.setattr(workflow, "_generate_risk_rows_with_deepagent", fake_draft)
    monkeypatch.setattr(workflow, "_review_risk_rows_with_deepagent", fake_review)
    monkeypatch.setattr(workflow, "_generate_action_rows_with_deepagent", fake_action)

    result = asyncio.run(generate_hazop_draft(context))

    assert calls == ["draft", "review", "action"]
    assert result.mode == "deepagent"
    assert result.risk_rows[0].severity == 4
    assert result.risk_rows[0].risk_score == 12
    assert result.action_rows[0].after_risk_score == 4
    assert result.review_findings[0].category == "강도 과소평가"
    assert "검토 확인 필요" in result.risk_rows[0].note

    # 화면이 문자열 추측 없이 Agent별 부모 블록과 스피너를 제어할 수 있어야 합니다.
    for agent_id in ("risk-draft-agent", "risk-review-agent", "action-plan-agent"):
        phases = [event.phase for event in result.events if event.agent_id == agent_id]
        assert phases[0] == "start"
        assert "progress" in phases
        assert phases[-1] == "finish"
        assert sum(
            event.title == "Planning: DeepAgent가 실행계획을 수립하는 중입니다."
            and event.agent_id == agent_id
            for event in result.events
        ) == 1

    titles = [event.title for event in result.events]
    assert titles[0] == "risk-draft-agent (위험성평가 초안 작성) Agent를 실행합니다."
    assert result.execution_plan is not None
    assert not any(title.startswith("Plan ") for title in titles)
    assert "Deepagent HAZOP Engine을 준비했습니다." not in titles
    assert not any("스킬을 실행 기준으로 등록합니다." in title for title in titles)
    assert not any("Context를 구성합니다." in title for title in titles)
    assert not any(title.endswith("Tool을 연결합니다.") for title in titles)
    assert not any("read_file" in f"{event.title} {event.detail}" for event in result.events)
    review_summaries = [
        event for event in result.events if event.title == "초안 검토 및 보완 결과 · 담당자 확인 필요 1건"
    ]
    assert len(review_summaries) == 1
    assert review_summaries[0].detail == "총 1건을 보완했습니다. 담당자 확인이 필요한 항목은 1건입니다."
    correction_summary = next(
        event for event in result.events if event.title == "Self-Correction: 독립 검토와 수정 반영을 완료했습니다."
    )
    assert "수정 1건" in correction_summary.detail
    assert "조치계획 대상 변경 1건" in correction_summary.detail
    assert all(finding.risk_assessment_no != "전체" for finding in result.review_findings)
    assert not any("검토 의견:" in event.title for event in result.events)


def test_draft_review_and_action_use_separate_llm_agents_with_lookup_tools(monkeypatch):
    import app.hazop_engine.workflow as workflow

    context = HazopDraftContext(
        input_data=HazopInput(maker="ASM", model="Epsilon3200", materials="Silane"),
        nodes=[NodeRow(node_order=1, node_name="Gas Cabinet")],
        guidewords=[GuidewordRow(node_order=1, node_name="Gas Cabinet", parameter="Containment", guideword="Leak")],
    )
    risk = _risk_row(severity=4)
    action = ActionPlanRow(
        no=1,
        risk_assessment_no=1,
        node_name="Gas Cabinet",
        recommendation="누설 감지와 긴급차단 인터록을 검증한다.",
        after_frequency=1,
        after_severity=4,
        after_risk_score=0,
        evidence=[AgentEvidence(reason="누출 발생 가능성을 낮춥니다.", source="review")],
    )
    created: list[tuple[str, set[str]]] = []

    class FakeAgent:
        def __init__(self, name):
            self.name = name

        def invoke(self, _payload):
            if self.name == "action-plan-agent":
                value = {"action_rows": [action.model_dump()], "review_findings": []}
                skills = ["hazop-action-plan", "severity-estimation"]
            elif self.name == "risk-review-agent":
                value = {
                    "risk_rows": [risk.model_dump()],
                    "review_findings": [
                        {
                            "risk_assessment_no": 1,
                            "category": "검토",
                            "message": "문제를 확인했습니다.",
                            "resolution": "초안에 반영했습니다.",
                            "requires_confirmation": False,
                        }
                    ],
                }
                skills = ["hazop-risk-review", "severity-estimation", "standard-hazop-comparison"]
            else:
                value = {"risk_rows": [risk.model_dump()], "review_findings": []}
                skills = ["hazop-risk-draft", "frequency-estimation", "severity-estimation"]
            return {"structured_response": value, "messages": _successful_skill_messages(skills)}

    def fake_create(**kwargs):
        created.append((kwargs["agent_name"], {tool.__name__ for tool in kwargs["tools"]}))
        return FakeAgent(kwargs["agent_name"])

    monkeypatch.setattr(workflow, "create_hazop_deep_agent", fake_create)

    async def run_stages():
        drafted, draft_traces = await workflow._generate_risk_rows_with_deepagent(context)
        assert any(trace.kind == "planning" and trace.success for trace in draft_traces)
        reviewed, _findings, _review_traces = await workflow._review_risk_rows_with_deepagent(context, drafted)
        await workflow._generate_action_rows_with_deepagent(context, reviewed)

    asyncio.run(run_stages())

    assert [name for name, _tools in created] == ["risk-draft-agent", "risk-review-agent", "action-plan-agent"]
    for _name, tools in created:
        assert {"lookup_msds_detail", "lookup_incident_history", "lookup_standard_hazop"} <= tools


def test_skill_read_trace_is_shown_as_summary_without_internal_path():
    import app.hazop_engine.workflow as workflow

    recorded = []

    async def progress(event):
        recorded.append(event)

    asyncio.run(
        workflow._record_trace_events(
            [],
            [
                AgentTrace(name="severity-estimation", kind="skill", success=True, detail="read_file 성공"),
                AgentTrace(name="lookup_msds_detail", kind="tool", success=True, detail="보완 조회 성공"),
            ],
            progress,
            agent_id="risk-draft-agent",
        )
    )

    assert len(recorded) == 1
    assert recorded[0].title == "Tool 실행 결과를 확인했습니다."
    assert not any("read_file" in f"{event.title} {event.detail}" for event in recorded)


def test_excel_validation_failure_is_sent_as_agent_error(monkeypatch, tmp_path):
    import app.services.agent as service_agent

    async def no_delay():
        return None

    def fail_validation(_path):
        raise ValueError("#2 가이드워드 형식이 올바르지 않습니다.")

    monkeypatch.setattr(service_agent, "_log_delay", no_delay)
    monkeypatch.setattr(service_agent, "validate_and_parse_excel_with_criteria", fail_validation)

    async def consume():
        return [
            event
            async for event in service_agent.run_hazop_agent(
                HazopInput(maker="Test", model="Failure", materials="Ammonia"),
                tmp_path / "invalid.xlsx",
                tmp_path / "requests",
            )
        ]

    events = asyncio.run(consume())

    assert events[-1].event == "agent_error"
    assert events[-1].data["stage"] == "excel_validation"
    assert "가이드워드 형식" in events[-1].data["message"]


def test_workflow_fetches_each_input_material_once_before_agents(monkeypatch, tmp_path):
    import app.services.agent as service_agent

    calls: list[str] = []
    nodes = [NodeRow(node_order=1, node_name="Gas Cabinet")]
    guidewords = [GuidewordRow(node_order=1, node_name="Gas Cabinet", parameter="Containment", guideword="Leak")]

    async def fake_lookup(material):
        calls.append(material)
        return MsdsLookupResult(
            summary=MsdsSummary(material=material, hazards=["test hazard"], handling=["test handling"], source="test"),
            steps=[],
        )

    async def no_delay():
        return None

    monkeypatch.setattr(
        service_agent,
        "validate_and_parse_excel_with_criteria",
        lambda _path: (nodes, guidewords, _criteria()),
    )
    monkeypatch.setattr(service_agent, "fetch_msds_summary_with_trace", fake_lookup)
    monkeypatch.setattr(service_agent, "export_result_excel", lambda *_args: None)
    monkeypatch.setattr(service_agent, "_log_delay", no_delay)
    monkeypatch.setattr(service_agent, "azure_openai_configured", lambda: False)

    async def consume():
        return [
            event
            async for event in service_agent.run_hazop_agent(
                HazopInput(maker="ASM", model="Epsilon3200", materials="Silane, Hydrogen, Silane"),
                tmp_path / "input.xlsx",
                tmp_path / "requests",
            )
        ]

    events = asyncio.run(consume())

    assert calls == ["Silane", "Hydrogen"]
    assert any(event.data.get("title") == "Workflow 필수 MSDS 조회를 시작합니다." for event in events)
    assert not any("위험도를 계산했습니다" in event.data.get("title", "") for event in events)
    assert sum(event.data.get("title") == "최종 결과의 시스템 검증을 완료했습니다." for event in events) == 1


def test_agent_progress_log_delay_uses_configured_random_range(monkeypatch):
    import app.services.agent as service_agent

    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setenv("AGENT_PROGRESS_LOG_MIN_SECONDS", "0.8")
    monkeypatch.setenv("AGENT_PROGRESS_LOG_MAX_SECONDS", "2.0")
    monkeypatch.setattr(service_agent.random, "uniform", lambda minimum, maximum: 1.4)
    monkeypatch.setattr(service_agent.asyncio, "sleep", fake_sleep)

    asyncio.run(
        service_agent._progress_log_delay(
            EngineEvent(
                title="Context 구성",
                detail="test",
                agent_id="risk-draft-agent",
                phase="progress",
            )
        )
    )
    asyncio.run(
        service_agent._progress_log_delay(
            EngineEvent(title="Planning", detail="test", kind="planning")
        )
    )
    asyncio.run(service_agent._progress_log_delay(EngineEvent(title="시스템 검증", detail="test")))

    assert sleeps == [1.4, 1.4]


def _risk_row(*, severity: int) -> RiskAssessmentRow:
    return RiskAssessmentRow(
        no=1,
        node_order=1,
        node_name="Gas Cabinet",
        parameter="Containment",
        guideword="Leak",
        deviation="Silane 누출",
        cause="배관 연결부 누설",
        consequence="자연발화와 화재로 작업자 중대재해 가능",
        existing_safeguard="가스감지기와 긴급차단밸브",
        frequency=3,
        severity=severity,
        risk_score=0,
        risk_level="계산 전",
        action_required="계산 전",
        decision_evidence=[AgentEvidence(reason="누출 시나리오", source="HAZOP")],
        severity_evidence=[AgentEvidence(reason="MSDS 위험성과 영향 범위", source="MSDS")],
        frequency_evidence=[AgentEvidence(reason="사고이력 확인 필요", source="사고이력")],
    )


def _criteria() -> RiskCriteria:
    return RiskCriteria(
        items=[
            RiskCriterion(category="빈도", score=str(score), description=f"빈도 {score} 기준")
            for score in range(1, 6)
        ]
        + [
            RiskCriterion(category="강도", score=str(score), description=f"강도 {score} 기준")
            for score in range(1, 5)
        ]
        + [RiskCriterion(category="위험도", score="1~20", description="테스트 위험 - 테스트 조치")],
        source="test 위험도기준",
    )


def _successful_skill_messages(skills: list[str]) -> list[dict]:
    calls = [
        {
            "id": f"call-{index}",
            "name": "read_file",
            "args": {"file_path": f"/project/app/hazop_engine/skills/{skill}/SKILL.md"},
        }
        for index, skill in enumerate(skills)
    ]
    planning_call = {
        "id": "call-planning",
        "name": "write_todos",
        "args": {
            "todos": [
                {"content": "입력 조합을 확인한다", "status": "completed"},
                {"content": "근거 우선순위를 적용한다", "status": "completed"},
                {"content": "위험성평가 초안을 작성한다", "status": "completed"},
            ]
        },
    }
    return [
        {"tool_calls": [planning_call, *calls]},
        {"tool_call_id": planning_call["id"], "status": "success", "content": "todo list updated"},
        *[
            {"tool_call_id": call["id"], "status": "success", "content": "skill content"}
            for call in calls
        ],
    ]
