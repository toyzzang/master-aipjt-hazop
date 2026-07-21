import asyncio

from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import _check_fs_permission
from deepagents.middleware.skills import _list_skills
from pydantic import ValidationError

from app.hazop_engine.agents.deepagent_factory import _filesystem_permissions, _skill_paths
from app.hazop_engine.context import (
    AgentTrace,
    EngineEvent,
    HazopDraftContext,
    IncidentHistoryContext,
    StandardHazopContext,
)
from app.hazop_engine.planning import build_execution_plan, plan_prompt
from app.hazop_engine.tools.incident_history_tools import lookup_incident_history
from app.hazop_engine.tools.validation_tools import parse_risk_rows, validate_and_calculate_risk_rows
from app.hazop_engine.tools.standard_hazop_tools import lookup_standard_hazop
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


def test_execution_plan_contains_only_fixed_workflow_and_tool_rules():
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
    assert not hasattr(plan, "candidates")
    assert not hasattr(plan, "selected_candidate_id")
    prompt = plan_prompt(context)
    assert plan.plan_id in prompt
    assert "고정 Workflow" in prompt
    assert "입력 검증" in prompt
    assert "독립 검토 및 수정" in prompt
    assert "사고이력 조회" in prompt


def test_local_standard_hazop_document_returns_real_reference_rows():
    result = lookup_standard_hazop(
        "STD-HAZOP-NH3-REFRIGERATION-2026-001",
        "NH3 Receiver containment leak compressor high pressure machine room ammonia",
    )

    assert result["document_title"] == "암모니아 냉동설비 표준 HAZOP"
    assert result["revision"] == "2026-01"
    assert result["matched_count"] >= 2
    assert any(row["node"] == "NH3 Receiver" for row in result["matched_rows"])
    assert any("참조 빈도=" in evidence and "강도=" in evidence for evidence in result["evidence"])


def test_local_incident_history_returns_relevant_ammonia_records():
    result = lookup_incident_history(
        "ColdChain NH3 Refrigeration ammonia receiver compressor condenser leak pressure high"
    )

    assert result["dataset_title"] == "HAZOP PoC 사고·정비 이력 샘플"
    assert "합성 샘플" in result["data_notice"]
    assert result["matched_count"] >= 3
    assert result["frequency_hint"] == 3
    assert {record["record_id"] for record in result["matched_records"]} >= {
        "INC-NH3-001",
        "MNT-NH3-002",
        "ALM-NH3-003",
    }
    assert all("PoC 합성 사고·정비 이력" == record["source"] for record in result["matched_records"])


def test_local_incident_history_returns_confirmation_when_no_record_matches():
    result = lookup_incident_history("lithium battery thermal runaway cell venting")

    assert result["matched_count"] == 0
    assert result["frequency_hint"] is None
    assert "확인 필요" in result["evidence"][0]


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
    assert result.execution_plan is not None
    assert not any("Workflow Planner" in title for title in titles)
    assert not any(event.kind in {"plan-candidate", "plan-evaluation", "plan-selected"} for event in result.events)
    assert "Deepagent HAZOP Engine을 준비했습니다." not in titles
    assert not any("스킬을 실행 기준으로 등록합니다." in title for title in titles)
    assert not any("Context를 구성합니다." in title for title in titles)
    assert not any(title.endswith("Tool을 연결합니다.") for title in titles)
    assert not any("read_file" in f"{event.title} {event.detail}" for event in result.events)
    assert not any(event.title.startswith("초안 검토 및 보완 결과") for event in result.events)
    correction_summary = next(
        event for event in result.events if event.title == "Self-Correction: 독립 검토와 수정 반영을 완료했습니다."
    )
    assert "검토 의견 1건" in correction_summary.detail
    assert "실제 수정 1개" in correction_summary.detail
    assert "조치계획 대상 변경 1개" in correction_summary.detail
    assert "① 조치계획 대상 변경" in correction_summary.detail
    assert correction_summary.event_key == "risk-review-agent:self-correction-summary"
    correction_detail = next(event for event in result.events if event.title.startswith("Self-Correction 대표 변경"))
    assert "위험도: 3×2=6 → 3×4=12 (시스템 재계산)" in correction_detail.detail
    assert "조치계획 대상: 아니오 → 예" in correction_detail.detail
    assert correction_detail.emphasis
    assert correction_detail.parent_event_key == correction_summary.event_key
    assert all(finding.risk_assessment_no != "전체" for finding in result.review_findings)
    assert not any("검토 의견:" in event.title for event in result.events)


def test_review_applies_only_rows_named_by_findings_and_global_confirmation_changes_no_row():
    import app.hazop_engine.workflow as workflow

    first = _risk_row(severity=2)
    second = _risk_row(severity=2).model_copy(update={"no": 2, "cause": "초안 원인 2"})
    rewritten_first = first.model_copy(update={"severity": 4, "cause": "실제 지적에 따른 수정"})
    rewritten_second = second.model_copy(update={"cause": "지적 없이 문장만 다시 작성"})
    row_finding = ReviewFinding(
        risk_assessment_no=1,
        category="강도 과소평가",
        message="평가 1의 강도 근거가 낮습니다.",
        resolution="강도와 원인을 보완했습니다.",
    )
    global_confirmation = ReviewFinding(
        risk_assessment_no="전체",
        category="공통 확인",
        message="현장 담당자가 최종 확인해야 합니다.",
        resolution="검토표에 확인사항을 남깁니다.",
        requires_confirmation=True,
    )

    scoped = workflow._apply_reviewed_rows_for_findings(
        [first, second],
        [rewritten_first, rewritten_second],
        [row_finding, global_confirmation],
    )
    confirmed = workflow._apply_confirmation_findings(scoped, [global_confirmation])

    assert scoped[0].cause == "실제 지적에 따른 수정"
    assert scoped[1].cause == "초안 원인 2"
    assert confirmed == scoped


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
        assert tools == {"lookup_msds_detail", "lookup_incident_history"}


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


def test_live_tool_trace_shows_purpose_input_and_result(monkeypatch):
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
    context.execution_plan = build_execution_plan(context)
    planning_call = {
        "id": "plan-1",
        "name": "write_todos",
        "args": {"todos": [{"content": "근거 확인", "status": "completed"}]},
    }
    tool_call = {
        "id": "tool-1",
        "name": "lookup_msds_detail",
        "args": {"material": "Silane", "requested_sections": ["hazards"]},
    }

    class FakeAgent:
        def invoke(self, _payload):
            return {
                "messages": [
                    {"tool_calls": [planning_call, tool_call]},
                    {"tool_call_id": "plan-1", "status": "success", "content": "updated"},
                    {
                        "tool_call_id": "tool-1",
                        "status": "success",
                        "content": '{"source":"KOSHA MSDS chem_id=1","hazards":["H220"]}',
                    },
                ]
            }

    recorded = []

    async def progress(event):
        recorded.append(event)

    asyncio.run(
        workflow._invoke_agent_with_live_stage(
            FakeAgent(),
            {"messages": []},
            context=context,
            events=[],
            progress=progress,
            agent_id="risk-draft-agent",
            required_skills=set(),
            skill_detail="없음",
            tool_detail="MSDS 조회",
            context_title="Context 준비",
            context_detail="테스트 Context",
            activity_title="Agent 실행",
            activity_detail="테스트 실행",
            activity_kind="agent",
        )
    )

    started = next(event for event in recorded if event.kind == "tool" and "호출 목적:" in event.detail)
    completed = next(event for event in recorded if event.kind == "tool" and "실행 결과:" in event.detail)
    assert started.title == "MSDS 상세 위험성 조회"
    assert started.parent_kind == "agent"
    assert started.parent_event_key == "risk-draft-agent:activity"
    assert started.event_key == "tool-1"
    assert "호출 목적:" in started.detail
    assert '"material": "Silane"' in started.detail
    assert started.emphasis
    assert "KOSHA MSDS" in completed.detail
    assert "판단 반영 위치:" in completed.detail


def test_self_correction_groups_parallel_tools_and_updates_progress():
    import app.hazop_engine.workflow as workflow

    context = HazopDraftContext(
        input_data=HazopInput(maker="ColdChain", model="NH3", materials="Ammonia"),
        nodes=[NodeRow(node_order=1, node_name="NH3 Receiver")],
        guidewords=[GuidewordRow(node_order=1, node_name="NH3 Receiver", parameter="Containment", guideword="Leak")],
        msds_context={
            "ammonia": MsdsSummary(material="Ammonia", hazards=["급성 독성"], handling=["누출 감지"], source="test")
        },
    )
    context.execution_plan = build_execution_plan(context)
    planning_call = {
        "id": "plan-1",
        "name": "write_todos",
        "args": {"todos": [{"content": "전체 Row 검토", "status": "completed"}]},
    }
    incident_call = {"id": "tool-incident", "name": "lookup_incident_history", "args": {"query": "NH3 leak"}}
    msds_call = {
        "id": "tool-msds",
        "name": "lookup_msds_detail",
        "args": {"material": "Ammonia", "requested_sections": ["hazards"]},
    }
    first = {"messages": [{"tool_calls": [planning_call, incident_call, msds_call]}]}
    second = {
        "messages": [
            *first["messages"],
            {"tool_call_id": "tool-incident", "status": "success", "content": '{"matched_count":1}'},
        ]
    }
    third = {
        "messages": [
            *second["messages"],
            {"tool_call_id": "tool-msds", "status": "success", "content": '{"material":"Ammonia"}'},
        ]
    }

    class FakeStreamingAgent:
        def stream(self, _payload, stream_mode):
            assert stream_mode == "values"
            yield first
            yield second
            yield third

    recorded = []

    async def progress(event):
        recorded.append(event)

    asyncio.run(
        workflow._invoke_agent_with_live_stage(
            FakeStreamingAgent(),
            {"messages": []},
            context=context,
            events=[],
            progress=progress,
            agent_id="risk-review-agent",
            required_skills=set(),
            skill_detail="없음",
            tool_detail="근거 조회",
            context_title="Context 준비",
            context_detail="테스트 Context",
            activity_title="Self-Correction · 전체 15건 비교 검토 중",
            activity_detail="전체 Row를 비교합니다.",
            activity_kind="self-correction",
        )
    )

    progress_details = [event.detail for event in recorded if event.event_key == "risk-review-agent:activity"]
    assert any("병렬 근거 조회 · 0/2 완료" in detail for detail in progress_details)
    assert any("병렬 근거 조회 · 1/2 완료" in detail for detail in progress_details)
    assert any("병렬 근거 조회 · 2/2 완료" in detail for detail in progress_details)
    tool_events = [event for event in recorded if event.parent_kind == "self-correction"]
    assert {event.event_key for event in tool_events} == {"tool-incident", "tool-msds"}
    assert all(event.parent_event_key == "risk-review-agent:activity" for event in tool_events)
    assert {event.title for event in tool_events} == {"사고·정비 이력 조회", "MSDS 상세 위험성 조회"}
    final_progress = [event for event in recorded if event.event_key == "risk-review-agent:activity"][-1]
    assert final_progress.loading is True
    assert "원인→결과 연결" in final_progress.detail


def test_planning_completion_counts_only_explicit_completed_todos():
    import app.hazop_engine.workflow as workflow

    assert workflow._planning_completion(
        "1. 입력 확인 [완료]\n2. 근거 조회 [진행 중]\n3. 결과 생성 [대기]"
    ) == (1, 3)


def test_english_review_todos_are_localized_and_successful_return_closes_last_item():
    import app.hazop_engine.workflow as workflow

    english_items = [
        "Read required SKILL.md files for hazop-risk-review, severity-estimation, and standard-hazop-comparison",
        "Verify input combination preservation and review all #3 rows against causes and safeguards",
        "Decide whether additional lookup tools are necessary and gather only missing evidence if needed",
        "Apply only necessary corrections to affected risk_rows while preserving unchanged rows exactly",
        "Return full risk_rows and review_findings with per-modified-row findings",
    ]
    localized = [workflow._localize_todo_content(item) for item in english_items]
    detail = "\n".join(
        f"{index}. {content} [{'완료' if index < 5 else '진행 중'}]"
        for index, content in enumerate(localized, start=1)
    )
    finalized = workflow._finalize_returned_planning_detail(detail)

    assert all(any("가" <= char <= "힣" for char in content) for content in localized)
    assert "[완료 · 시스템 확인]" in finalized
    assert workflow._planning_completion(finalized) == (5, 5)


def test_planning_does_not_hide_multiple_incomplete_steps():
    import app.hazop_engine.workflow as workflow

    detail = "1. 입력 확인 [완료]\n2. 근거 조회 [진행 중]\n3. 결과 반환 [대기]"

    assert workflow._finalize_returned_planning_detail(detail) == detail


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


def test_workflow_fetches_each_input_material_once_before_agents(monkeypatch, tmp_path, caplog):
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
    caplog.set_level("INFO", logger="uvicorn.error")

    async def consume():
        return [
            event
            async for event in service_agent.run_hazop_agent(
                HazopInput(
                    maker="ASM",
                    model="Epsilon3200",
                    materials="Silane, Hydrogen, Silane",
                    standard_hazop_link="STD-HAZOP-SILANE-GAS-2026-001",
                ),
                tmp_path / "input.xlsx",
                tmp_path / "requests",
            )
        ]

    events = asyncio.run(consume())

    assert calls == ["Silane", "Hydrogen"]
    assert any(event.data.get("title") == "Workflow 필수 MSDS 조회 · 고유 물질 전체 확인" for event in events)
    incident_event = next(
        event for event in events
        if event.data.get("title") == "로컬 사고·정비 이력 저장소를 조회했습니다."
    )
    assert "유사 이력 1건" in incident_event.data["detail"]
    assert "PoC 합성" in incident_event.data["detail"]
    assert sum(
        event.data.get("title") == "로컬 표준 HAZOP 문서를 조회했습니다."
        for event in events
    ) == 1
    msds_children = [
        event.data for event in events
        if event.data.get("agent_id") == "msds-lookup-workflow" and str(event.data.get("event_key", "")).startswith("msds:")
    ]
    assert {event["event_key"] for event in msds_children} == {"msds:silane", "msds:hydrogen"}
    assert all(any(item["event_key"] == event_key and item["loading"] is False for item in msds_children) for event_key in {"msds:silane", "msds:hydrogen"})
    assert not any("위험도를 계산했습니다" in event.data.get("title", "") for event in events)
    assert sum(event.data.get("title") == "최종 결과의 시스템 검증을 완료했습니다." for event in events) == 1
    assert any(event.event == "run_mode" and event.data["mode"] == "demo" for event in events)
    done_event = next(event for event in events if event.event == "done")
    assert done_event.data["risk_rows"][0]["frequency_evidence"][0]["source"] == "로컬 사고·정비 이력 JSON + 빈도 기준표"
    assert any("AGENT_TRACE" in record.message and '"request_id"' in record.message for record in caplog.records)
    # Demo fallback에는 모델이 세운 Agent 계획이 없으므로 가짜 Planning 로그를 만들지 않는다.
    # 대신 실제로 수행된 구조화 이벤트가 백엔드 콘솔에도 남는지만 확인한다.
    assert any('"kind": "workflow"' in record.message for record in caplog.records)
    assert not any(
        f'"kind": "{kind}"' in record.message
        for record in caplog.records
        for kind in {"plan-candidate", "plan-evaluation", "plan-selected"}
    )


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


def test_preloaded_evidence_results_are_inside_draft_tool_aggregation_block():
    import app.hazop_engine.workflow as workflow

    context = HazopDraftContext(
        input_data=HazopInput(
            maker="ColdChain",
            model="NH3-Refrigeration",
            materials="Ammonia",
            standard_hazop_link="STD-HAZOP-NH3-REFRIGERATION-2026-001",
        ),
        nodes=[NodeRow(node_order=1, node_name="NH3 Receiver")],
        guidewords=[GuidewordRow(node_order=1, node_name="NH3 Receiver", parameter="Containment", guideword="Leak")],
        incident_history_context=IncidentHistoryContext(
            matched_count=2,
            frequency_hint=3,
            dataset_title="HAZOP PoC 사고·정비 이력 샘플",
            data_notice="PoC 합성 샘플",
            evidence=["ALM-NH3-003 · 빈도 참고=3"],
        ),
        standard_hazop_context=StandardHazopContext(
            reference_id="STD-HAZOP-NH3-REFRIGERATION-2026-001",
            document_title="암모니아 냉동설비 표준 HAZOP",
            revision="2026-01",
            matched_count=4,
            evidence=["NH3 Receiver · Containment/Leak · 참조 빈도=2, 강도=4"],
        ),
    )

    class FakeAgent:
        def invoke(self, _payload):
            return {
                "messages": _successful_skill_messages(
                    ["hazop-risk-draft", "frequency-estimation", "severity-estimation"]
                )
            }

    recorded = []

    async def progress(event):
        recorded.append(event)

    asyncio.run(
        workflow._invoke_agent_with_live_stage(
            FakeAgent(),
            {"messages": []},
            context=context,
            events=[],
            progress=progress,
            agent_id="risk-draft-agent",
            required_skills={"hazop-risk-draft", "frequency-estimation", "severity-estimation"},
            skill_detail="테스트 Skill",
            tool_detail="테스트 Tool",
            context_title="Context 구성",
            context_detail="테스트 Context",
            activity_title="Tool 결과를 취합해 Agent 결과를 생성 중입니다.",
            activity_detail="구조화 결과를 생성하고 검증하는 중입니다.",
            activity_kind="agent",
        )
    )

    activity = next(event for event in recorded if event.event_key == "risk-draft-agent:activity")
    assert activity.title == "Tool 결과를 취합해 Agent 결과를 생성 중입니다."
    evidence_events = [
        event for event in recorded
        if event.event_key in {"workflow:incident-history", "workflow:standard-hazop"}
    ]
    assert {event.title for event in evidence_events} == {
        "로컬 사고·정비 이력 저장소를 조회했습니다.",
        "로컬 표준 HAZOP 문서를 조회했습니다.",
    }
    assert all(event.parent_event_key == "risk-draft-agent:activity" for event in evidence_events)
    assert all(event.parent_kind == "agent" for event in evidence_events)


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
