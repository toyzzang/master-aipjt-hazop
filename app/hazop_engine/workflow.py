from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

from app.hazop_engine.agents.deepagent_factory import DeepAgentUnavailable, create_hazop_deep_agent
from app.hazop_engine.context import AgentTrace, HazopDraftContext, HazopDraftResult
from app.hazop_engine.events import engine_event
from app.hazop_engine.tools.incident_history_tools import lookup_incident_history
from app.hazop_engine.tools.msds_tools import lookup_msds_detail
from app.hazop_engine.tools.standard_hazop_tools import lookup_standard_hazop
from app.hazop_engine.tools.validation_tools import (
    parse_action_rows,
    parse_risk_rows,
    validate_and_calculate_action_rows,
    validate_and_calculate_risk_rows,
)
from app.schemas.hazop import ActionPlanRow, AgentEvidence, ReviewFinding, RiskAssessmentRow
from app.services.llm import azure_openai_configured, missing_azure_openai_env


ProgressCallback = Callable[[Any], Awaitable[None]]


class DeepAgentRiskOutput(BaseModel):
    """Deepagent가 반환해야 하는 #3 위험성평가 결과 형식입니다."""

    risk_rows: list[RiskAssessmentRow] = Field(default_factory=list)
    review_findings: list[str] = Field(default_factory=list)


class DeepAgentActionOutput(BaseModel):
    """Deepagent가 반환해야 하는 #4 조치계획서 결과 형식입니다."""

    action_rows: list[ActionPlanRow] = Field(default_factory=list)
    review_findings: list[str] = Field(default_factory=list)


class DeepAgentReviewOutput(BaseModel):
    """독립 risk-review-agent가 보완해 반환해야 하는 #3 전체 결과 형식입니다."""

    risk_rows: list[RiskAssessmentRow] = Field(default_factory=list)
    review_findings: list[ReviewFinding] = Field(default_factory=list)


class DeepAgentStageError(RuntimeError):
    """어느 전문 Agent의 어느 단계에서 실패했는지 보존합니다."""

    def __init__(self, agent_id: str, stage: str, cause: Exception):
        self.agent_id = agent_id
        self.stage = stage
        self.cause = cause
        super().__init__(f"{agent_id} / {stage}: {cause}")


async def generate_hazop_draft(context: HazopDraftContext, progress: ProgressCallback | None = None) -> HazopDraftResult:
    """Deepagent 기반으로 HAZOP #3/#4 초안을 생성합니다.

    Deepagent를 실행할 수 없으면 PoC 흐름이 끊기지 않도록 규칙 기반 demo 결과로 fallback합니다.
    """

    events = []

    if not azure_openai_configured():
        missing_keys = ", ".join(missing_azure_openai_env())
        await _record_event(
            events,
            engine_event(
                "Deepagent 실행을 생략합니다.",
                f"Azure OpenAI 설정이 서버에 전달되지 않았습니다. 비어 있는 키: {missing_keys}.",
                kind="warning",
            ),
            progress,
        )
        return await _demo_result(context, events, "연결된 Azure OpenAI 설정이 없습니다.", progress)

    active_agent_id: str | None = None
    active_stage = "DeepAgent 실행 준비"

    try:
        active_agent_id = "risk-draft-agent"
        active_stage = "#3 위험성평가 초안 생성"
        await _record_events(
            events,
            progress,
            [
                engine_event(
                    "risk-draft-agent (위험성평가 초안 작성) Agent를 실행합니다.",
                    "#1 노드리스트와 #2 가이드워드를 기반으로 #3 위험성평가 초안을 작성합니다.",
                    kind="agent",
                    agent_id="risk-draft-agent",
                    phase="start",
                    loading=True,
                ),
                engine_event(
                    "hazop_risk_draft 스킬을 실행 기준으로 등록합니다.",
                    "Deviation, Cause, Consequence, Safeguard, 판단 근거 문장 작성 기준을 Agent가 실행 중 읽고 적용하도록 준비합니다.",
                    kind="skill",
                    agent_id="risk-draft-agent",
                    phase="progress",
                ),
                engine_event(
                    "frequency_estimation 스킬을 실행 기준으로 등록합니다.",
                    "사고이력, 유사 HAZOP 문서, 일반 HAZOP 규칙 순서로 빈도 근거를 확인하도록 준비합니다.",
                    kind="skill",
                    agent_id="risk-draft-agent",
                    phase="progress",
                ),
                engine_event(
                    "severity_estimation 스킬을 실행 기준으로 등록합니다.",
                    "MSDS 물질 위험성과 작업자·설비·환경의 사고 영향 범위로 강도를 판단하도록 준비합니다.",
                    kind="skill",
                    agent_id="risk-draft-agent",
                    phase="progress",
                ),
                engine_event(
                    "lookup_msds_detail Tool을 연결합니다.",
                    "최초 MSDS 요약보다 더 자세한 유해성·취급·누출 대응 정보가 필요할 때만 보완 조회합니다.",
                    kind="tool",
                    agent_id="risk-draft-agent",
                    phase="progress",
                ),
                engine_event(
                    "lookup_incident_history Tool을 연결합니다.",
                    "빈도 판단 근거가 부족할 때 유사 물질·설비의 사고이력을 보완 조회합니다.",
                    kind="tool",
                    agent_id="risk-draft-agent",
                    phase="progress",
                ),
                engine_event(
                    "lookup_standard_hazop Tool을 연결합니다.",
                    "원인·결과·안전조치 후보를 비교할 때 표준 HAZOP 사례를 보완 조회합니다.",
                    kind="tool",
                    agent_id="risk-draft-agent",
                    phase="progress",
                ),
                engine_event(
                    "위험성평가 작성 Context를 구성합니다.",
                    _draft_context_summary(context),
                    kind="agent",
                    agent_id="risk-draft-agent",
                    phase="progress",
                ),
                engine_event(
                    "모델 응답 대기 중입니다.",
                    "risk-draft-agent가 Skill과 작업 Context를 연결된 Azure OpenAI 모델에 전달해 #3 위험성평가 초안을 작성하고 있습니다.",
                    kind="tool",
                    agent_id="risk-draft-agent",
                    phase="progress",
                    loading=True,
                ),
            ],
        )
        risk_started_at = time.perf_counter()
        risk_rows, risk_traces = await _generate_risk_rows_with_deepagent(context)
        await _record_trace_events(events, risk_traces, progress, agent_id="risk-draft-agent")
        risk_elapsed = time.perf_counter() - risk_started_at
        await _record_event(
            events,
            engine_event(
                "#3 위험성평가 Deepagent 초안을 생성했습니다.",
                f"작성 Agent가 위험성평가 Row {len(risk_rows)}건을 생성했습니다. 소요 시간: {risk_elapsed:.1f}초.",
                kind="result",
                agent_id="risk-draft-agent",
                phase="finish",
            ),
            progress,
        )
        system_checked_rows = validate_and_calculate_risk_rows(risk_rows, context.guidewords, context.risk_criteria)
        await _record_event(
            events,
            engine_event(
                "1단계 시스템 검증을 완료했습니다.",
                f"Node/변수/Guideword, Row {len(system_checked_rows)}건, 빈도·강도 범위, 근거 존재 여부를 확인하고 위험도를 계산했습니다.",
                kind="validation",
            ),
            progress,
        )
        active_agent_id = "risk-review-agent"
        active_stage = "#3 초안 검토 및 보완"
        await _record_events(
            events,
            progress,
            [
                engine_event(
                    "risk-review-agent (초안 검토 및 보완) Agent를 실행합니다.",
                    "Workflow가 시스템 검증본의 의미 검토를 반드시 실행합니다. 이 Agent는 초안 작성 Agent와 분리된 Azure OpenAI 모델 호출입니다.",
                    kind="agent",
                    agent_id="risk-review-agent",
                    phase="start",
                    loading=True,
                ),
                engine_event(
                    "hazop_risk_review 스킬을 실행 기준으로 등록합니다.",
                    "원인·결과 연결, 안전조치, 판단 근거 누락을 Agent가 실행 중 읽고 검토하도록 준비합니다.",
                    kind="skill",
                    agent_id="risk-review-agent",
                    phase="progress",
                ),
                engine_event(
                    "severity_estimation 스킬을 실행 기준으로 등록합니다.",
                    "MSDS와 사고 영향 범위에 비해 강도가 낮게 평가되지 않았는지 검토하도록 준비합니다.",
                    kind="skill",
                    agent_id="risk-review-agent",
                    phase="progress",
                ),
                engine_event(
                    "standard_hazop_comparison 스킬을 실행 기준으로 등록합니다.",
                    "표준 HAZOP보다 위험을 낮게 평가한 근거가 충분한지 비교하도록 준비합니다.",
                    kind="skill",
                    agent_id="risk-review-agent",
                    phase="progress",
                ),
                engine_event(
                    "보완 검토 Tool을 연결합니다.",
                    "근거가 부족하거나 서로 모순될 때 MSDS 상세, 사고이력, 표준 HAZOP Tool을 선택 호출할 수 있게 준비합니다.",
                    kind="tool",
                    agent_id="risk-review-agent",
                    phase="progress",
                ),
                engine_event(
                    "위험도 검토 Context를 구성합니다.",
                    _review_context_summary(context, system_checked_rows),
                    kind="agent",
                    agent_id="risk-review-agent",
                    phase="progress",
                ),
                engine_event(
                    "모델 응답 대기 중입니다.",
                    "risk-review-agent가 시스템 검증본과 Skill 기준을 연결된 Azure OpenAI 모델에 전달해 전체 Row를 검토하고 있습니다.",
                    kind="tool",
                    agent_id="risk-review-agent",
                    phase="progress",
                    loading=True,
                ),
            ],
        )
        reviewed_rows, review_findings, review_traces = await _review_risk_rows_with_deepagent(context, system_checked_rows)
        await _record_trace_events(events, review_traces, progress, agent_id="risk-review-agent")
        await _record_review_findings(events, review_findings, progress, agent_id="risk-review-agent")
        reviewed_rows = _apply_confirmation_findings(reviewed_rows, review_findings)
        calculated_rows = validate_and_calculate_risk_rows(reviewed_rows, context.guidewords, context.risk_criteria)
        high_risk_rows = [row for row in calculated_rows if row.risk_score >= 9]
        await _record_events(
            events,
            progress,
            [
                engine_event(
                    "risk-review-agent 검토 결과를 최종 초안에 반영했습니다.",
                    "보완된 전체 위험성평가 Row를 시스템이 다시 검증하고 위험도를 재계산했습니다.",
                    kind="result",
                    agent_id="risk-review-agent",
                    phase="finish",
                ),
                engine_event(
                    "고위험 조치 대상을 선별했습니다.",
                    f"검토 반영본을 시스템 코드가 빈도 * 강도로 계산해 위험도 9 이상 {len(high_risk_rows)}건을 선별했습니다.",
                    kind="validation",
                ),
            ],
        )
        if high_risk_rows:
            active_agent_id = "action-plan-agent"
            active_stage = "#4 조치계획서 초안 생성"
            await _record_events(
                events,
                progress,
                [
                    engine_event(
                        "action-plan-agent (고위험 항목 조치계획 작성) Agent를 실행합니다.",
                        "Workflow가 시스템 계산 위험도 9 이상 항목만 전달해 #4 조치계획서 작성을 시작합니다.",
                        kind="agent",
                        agent_id="action-plan-agent",
                        phase="start",
                        loading=True,
                    ),
                    engine_event(
                        "hazop_action_plan 스킬을 실행 기준으로 등록합니다.",
                        "고위험 원인을 줄일 권고 조치, 담당 부서, 완료 기준을 작성하도록 준비합니다.",
                        kind="skill",
                        agent_id="action-plan-agent",
                        phase="progress",
                    ),
                    engine_event(
                        "severity_estimation 스킬을 실행 기준으로 등록합니다.",
                        "조치 후에도 남는 사고 영향 강도를 확인하도록 준비합니다.",
                        kind="skill",
                        agent_id="action-plan-agent",
                        phase="progress",
                    ),
                    engine_event(
                        "보완 조치 Tool을 연결합니다.",
                        "예방·완화 조치 근거가 필요할 때 MSDS 상세, 사고이력, 표준 HAZOP Tool을 선택 호출할 수 있게 준비합니다.",
                        kind="tool",
                        agent_id="action-plan-agent",
                        phase="progress",
                    ),
                    engine_event(
                        "조치계획 작성 Context를 구성합니다.",
                        _action_context_summary(context, high_risk_rows),
                        kind="agent",
                        agent_id="action-plan-agent",
                        phase="progress",
                    ),
                    engine_event(
                        "모델 응답 대기 중입니다.",
                        "action-plan-agent가 고위험 Context와 Skill 기준을 연결된 Azure OpenAI 모델에 전달해 #4 조치계획서를 작성하고 있습니다.",
                        kind="tool",
                        agent_id="action-plan-agent",
                        phase="progress",
                        loading=True,
                    ),
                ],
            )
        else:
            await _record_event(
                events,
                engine_event("action-plan-agent 호출 대상이 없습니다.", "위험도 9 이상 항목이 없어 #4 조치계획서 LLM 호출을 생략합니다.", kind="result"),
                progress,
            )
        action_started_at = time.perf_counter()
        action_rows, action_traces = await _generate_action_rows_with_deepagent(context, high_risk_rows)
        await _record_trace_events(events, action_traces, progress, agent_id="action-plan-agent")
        calculated_action_rows = validate_and_calculate_action_rows(action_rows, high_risk_rows)
        action_elapsed = time.perf_counter() - action_started_at
        await _record_event(
            events,
            engine_event(
                "#4 조치계획서 Deepagent 초안을 생성했습니다.",
                f"조치계획서 Row {len(action_rows)}건을 확보했습니다. 소요 시간: {action_elapsed:.1f}초.",
                kind="result",
                agent_id="action-plan-agent" if high_risk_rows else None,
                phase="finish" if high_risk_rows else None,
            ),
            progress,
        )
        return HazopDraftResult(
            risk_rows=calculated_rows,
            action_rows=calculated_action_rows,
            review_findings=review_findings,
            events=events,
            mode="deepagent",
        )
    except Exception as exc:
        if isinstance(exc, DeepAgentStageError):
            active_agent_id = exc.agent_id
            active_stage = exc.stage
            root_exc = exc.cause
        else:
            root_exc = exc
        await _record_event(
            events,
            engine_event(
                f"{active_agent_id or 'HAZOP Workflow'} 실행에 실패했습니다.",
                f"실패 단계: {active_stage}. 원인: {_describe_deepagent_exception(root_exc)}",
                kind="error",
                agent_id=active_agent_id,
                phase="finish" if active_agent_id else None,
            ),
            progress,
        )
        fallback_reason = _describe_deepagent_exception(exc)
        await _record_event(
            events,
            engine_event(
                "Deepagent 실행 중 fallback으로 전환합니다.",
                f"Deepagent 초안 생성이 완료되지 않아 PoC 내장 생성기를 사용합니다. 사유: {fallback_reason}",
                kind="warning",
            ),
            progress,
        )
        return await _demo_result(context, events, fallback_reason, progress)


async def _generate_risk_rows_with_deepagent(
    context: HazopDraftContext,
) -> tuple[list[RiskAssessmentRow], list[AgentTrace]]:
    agent_id = "risk-draft-agent"
    try:
        agent = create_hazop_deep_agent(
            tools=[lookup_msds_detail, lookup_incident_history, lookup_standard_hazop],
            system_prompt=_risk_system_prompt(),
            response_format=DeepAgentRiskOutput,
            agent_name=agent_id,
        )
        result = await asyncio.to_thread(
            agent.invoke,
            {"messages": [{"role": "user", "content": _risk_user_prompt(context)}]},
        )
        data = _structured_response(result)
        traces = _extract_agent_traces(result)
        _require_skill_reads(traces, {"hazop-risk-draft", "frequency-estimation", "severity-estimation"})
        return parse_risk_rows(data, context.guidewords), traces
    except Exception as exc:
        raise DeepAgentStageError(agent_id, "#3 결과 형식 및 필수 Skill 검증", exc) from exc


async def _review_risk_rows_with_deepagent(
    context: HazopDraftContext,
    system_checked_rows: list[RiskAssessmentRow],
) -> tuple[list[RiskAssessmentRow], list[ReviewFinding], list[AgentTrace]]:
    """별도 LLM 호출로 의미 검토를 수행하고 보완된 전체 Row를 받습니다."""

    agent_id = "risk-review-agent"
    try:
        agent = create_hazop_deep_agent(
            tools=[lookup_msds_detail, lookup_incident_history, lookup_standard_hazop],
            system_prompt=_review_system_prompt(),
            response_format=DeepAgentReviewOutput,
            agent_name=agent_id,
        )
        result = await asyncio.to_thread(
            agent.invoke,
            {"messages": [{"role": "user", "content": _review_user_prompt(context, system_checked_rows)}]},
        )
        data = _structured_response(result)
        traces = _extract_agent_traces(result)
        _require_skill_reads(traces, {"hazop-risk-review", "severity-estimation", "standard-hazop-comparison"})
        reviewed_rows = parse_risk_rows(data, context.guidewords)
        findings = data.get("review_findings", []) if isinstance(data, dict) else []
        return reviewed_rows, [ReviewFinding.model_validate(item) for item in findings], traces
    except Exception as exc:
        raise DeepAgentStageError(agent_id, "검토 결과 형식 및 필수 Skill 검증", exc) from exc


async def _generate_action_rows_with_deepagent(
    context: HazopDraftContext,
    high_risk_rows: list[RiskAssessmentRow],
) -> tuple[list[ActionPlanRow], list[AgentTrace]]:
    if not high_risk_rows:
        return [], []
    agent_id = "action-plan-agent"
    try:
        agent = create_hazop_deep_agent(
            tools=[lookup_msds_detail, lookup_incident_history, lookup_standard_hazop],
            system_prompt=_action_system_prompt(),
            response_format=DeepAgentActionOutput,
            agent_name=agent_id,
        )
        result = await asyncio.to_thread(
            agent.invoke,
            {"messages": [{"role": "user", "content": _action_user_prompt(context, high_risk_rows)}]},
        )
        data = _structured_response(result)
        traces = _extract_agent_traces(result)
        _require_skill_reads(traces, {"hazop-action-plan", "severity-estimation"})
        return parse_action_rows(data), traces
    except Exception as exc:
        raise DeepAgentStageError(agent_id, "#4 결과 형식 및 필수 Skill 검증", exc) from exc


def _draft_context_summary(context: HazopDraftContext) -> str:
    materials = ", ".join(summary.material for summary in context.msds_context.values()) or "없음"
    criteria = context.risk_criteria.source if context.risk_criteria else "기준표 미전달"
    return (
        f"Node {len(context.nodes)}건, Guideword {len(context.guidewords)}건, 최초 MSDS {len(context.msds_context)}건"
        f"({materials}), Maker·Model·운전 의도·사고/정비 이력, 위험도 기준표({criteria})를 전달했습니다."
    )


def _review_context_summary(context: HazopDraftContext, rows: list[RiskAssessmentRow]) -> str:
    materials = ", ".join(summary.material for summary in context.msds_context.values()) or "없음"
    return (
        f"시스템 검증 위험성평가 {len(rows)}건, 최초 MSDS {len(context.msds_context)}건({materials}), "
        "Guideword 원본, 사용자 사고/정비 이력, 표준 HAZOP 참조값, 위험도 기준표를 전달했습니다."
    )


def _action_context_summary(context: HazopDraftContext, rows: list[RiskAssessmentRow]) -> str:
    materials = ", ".join(summary.material for summary in context.msds_context.values()) or "없음"
    return (
        f"검토 반영 후 위험도 9 이상 {len(rows)}건, 원인·결과·현재 안전조치, 최초 MSDS "
        f"{len(context.msds_context)}건({materials}), 사용자 입력과 위험도 기준표를 전달했습니다."
    )


def _structured_response(result: Any) -> Any:
    if isinstance(result, dict) and "structured_response" in result:
        structured = result["structured_response"]
        if isinstance(structured, BaseModel):
            return structured.model_dump()
        return structured
    return result


def _extract_agent_traces(result: Any) -> list[AgentTrace]:
    """DeepAgents 메시지에서 실제 실행된 read_file/Domain Tool 호출만 추출합니다."""

    if not isinstance(result, dict):
        return []
    messages = result.get("messages", [])
    tool_results: dict[str, Any] = {}
    for message in messages:
        call_id = _message_value(message, "tool_call_id")
        if call_id:
            tool_results[str(call_id)] = message

    traces: list[AgentTrace] = []
    for message in messages:
        for call in _message_value(message, "tool_calls") or []:
            name = str(_object_value(call, "name") or "")
            call_id = str(_object_value(call, "id") or "")
            args = _object_value(call, "args") or {}
            tool_result = tool_results.get(call_id)
            success = _tool_result_succeeded(tool_result)
            if name == "read_file":
                path = str(_object_value(args, "file_path") or _object_value(args, "path") or "")
                if path.endswith("/SKILL.md") and "/skills/" in path:
                    skill_name = path.rstrip("/").split("/")[-2]
                    traces.append(
                        AgentTrace(
                            name=skill_name,
                            kind="skill",
                            success=success,
                            detail=f"{path} read_file {'성공' if success else '실패'}",
                        )
                    )
            elif name in {"lookup_msds_detail", "lookup_incident_history", "lookup_standard_hazop"}:
                traces.append(
                    AgentTrace(
                        name=name,
                        kind="tool",
                        success=success,
                        detail=f"호출 조건={args}",
                    )
                )
    return traces


def _require_skill_reads(traces: list[AgentTrace], required: set[str]) -> None:
    succeeded = {trace.name for trace in traces if trace.kind == "skill" and trace.success}
    missing = sorted(required - succeeded)
    if missing:
        raise ValueError("필수 Skill 본문 read_file 성공 trace가 없습니다: " + ", ".join(missing))


async def _record_trace_events(
    events: list,
    traces: list[AgentTrace],
    progress: ProgressCallback | None,
    agent_id: str | None = None,
) -> None:
    skill_traces = [trace for trace in traces if trace.kind == "skill"]
    if skill_traces:
        applied_skills = ", ".join(trace.name for trace in skill_traces if trace.success)
        await _record_event(
            events,
            engine_event(
                "필수 Skill 적용을 확인했습니다.",
                f"Agent 실행 기록에서 {len(skill_traces)}개 Skill 적용을 확인했습니다: {applied_skills}",
                kind="skill",
                agent_id=agent_id,
                phase="progress",
            ),
            progress,
        )

    for trace in traces:
        if trace.kind == "skill":
            # 개별 read_file 경로는 숨기고 위의 사용자용 적용 요약만 표시합니다.
            continue
        title = f"{trace.name} Agent Tool 호출 {'성공' if trace.success else '실패'}"
        await _record_event(
            events,
            engine_event(title, trace.detail, kind=trace.kind, agent_id=agent_id, phase="progress"),
            progress,
        )


async def _record_review_findings(
    events: list,
    findings: list[ReviewFinding],
    progress: ProgressCallback | None,
    agent_id: str | None = None,
) -> None:
    confirmation_count = sum(finding.requires_confirmation for finding in findings)
    await _record_event(
        events,
        engine_event(
            "초안 검토 및 보완 결과를 요약했습니다.",
            f"총 {len(findings)}건을 보완했습니다. 담당자 확인이 필요한 항목은 {confirmation_count}건입니다.",
            kind="warning" if confirmation_count else "result",
            agent_id=agent_id,
            phase="progress",
        ),
        progress,
    )


def _message_value(message: Any, key: str) -> Any:
    if isinstance(message, dict):
        return message.get(key)
    return getattr(message, key, None)


def _object_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _tool_result_succeeded(message: Any) -> bool:
    if message is None:
        return False
    status = str(_message_value(message, "status") or "success").lower()
    content = str(_message_value(message, "content") or "")
    lowered = content.lower()
    return status != "error" and "permission denied" not in lowered and not lowered.startswith("error:")


def _apply_confirmation_findings(
    rows: list[RiskAssessmentRow],
    findings: list[ReviewFinding],
) -> list[RiskAssessmentRow]:
    """담당자 확인이 필요한 검토 의견을 최종 Excel의 Risk Row 비고에도 남깁니다."""

    confirmation_by_no: dict[int | None, list[str]] = {}
    for finding in findings:
        if finding.requires_confirmation:
            confirmation_by_no.setdefault(finding.risk_assessment_no, []).append(finding.message)

    updated: list[RiskAssessmentRow] = []
    for row in rows:
        messages = [*confirmation_by_no.get(None, []), *confirmation_by_no.get(row.no, [])]
        if not messages:
            updated.append(row)
            continue
        marker = "검토 확인 필요: " + " / ".join(messages)
        note = f"{row.note}\n{marker}".strip() if row.note else marker
        updated.append(row.model_copy(update={"note": note}))
    return updated


def _describe_deepagent_exception(exc: Exception) -> str:
    """DeepAgent 실패 원인을 사용자가 확인하기 쉬운 말로 바꿉니다.

    쉽게 말하면 `Connection error`처럼 짧은 영어 경고만 보여주지 않고,
    어떤 설정을 보면 되는지까지 함께 적어주는 함수입니다.
    """

    chain = _exception_chain(exc)
    messages = [str(item).strip() for item in chain if str(item).strip()]
    type_names = {type(item).__name__ for item in chain}
    joined = " / ".join(messages) if messages else type(exc).__name__
    lowered = joined.lower()

    if "connection error" in lowered or "connecterror" in lowered or "connection" in lowered:
        checks = [
            "AZURE_OPENAI_ENDPOINT 접속 가능 여부",
            "AZURE_OPENAI_API_KEY 값",
            "AZURE_OPENAI_API_VERSION 값",
            "AZURE_OPENAI_DEPLOYMENT 배포명",
        ]
        if os.getenv("AZURE_OPENAI_VERIFY_SSL", "true").lower() in {"0", "false", "no"}:
            checks.append("사내 게이트웨이 SSL 설정(AZURE_OPENAI_VERIFY_SSL=false 적용 여부)")
        return (
            "Azure OpenAI 연결 단계에서 실패했습니다. "
            f"원본 오류: {joined}. "
            "확인할 항목: " + ", ".join(checks) + "."
        )

    if "ssl" in lowered or "certificate" in lowered:
        return (
            "SSL 인증서 검증 중 실패했습니다. "
            f"원본 오류: {joined}. "
            "사내 프록시/게이트웨이를 쓰는 환경이면 사내 CA 인증서를 설치하거나 "
            "PoC에서만 AZURE_OPENAI_VERIFY_SSL=false를 확인하세요."
        )

    if "401" in joined or "unauthorized" in lowered:
        return f"Azure OpenAI 인증에 실패했습니다. API key 또는 권한을 확인하세요. 원본 오류: {joined}."

    if "404" in joined or "deployment" in lowered:
        return f"Azure OpenAI 배포를 찾지 못했습니다. AZURE_OPENAI_DEPLOYMENT 값을 확인하세요. 원본 오류: {joined}."

    if "timeout" in lowered:
        return (
            "Azure OpenAI 응답 대기 시간이 초과되었습니다. "
            f"원본 오류: {joined}. endpoint 상태와 AZURE_OPENAI_TIMEOUT_SECONDS 값을 확인하세요."
        )

    return f"{type(exc).__name__}: {joined}. 관련 예외 종류: {', '.join(sorted(type_names))}."


def _exception_chain(exc: Exception) -> list[BaseException]:
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def _risk_system_prompt() -> str:
    return """
너는 #3 위험성평가를 작성하는 risk-draft-agent이다.
작업을 시작할 때 hazop-risk-draft, frequency-estimation, severity-estimation Skill의 SKILL.md 전체를 read_file로 반드시 읽고 따른다.
사용자가 제공한 #1 노드리스트와 #2 가이드워드 기준으로만 초안을 작성한다.
Node, 변수, Guideword를 새로 만들거나 추천하지 않는다.
빈도는 1~5 후보, 강도는 1~4 후보만 작성한다.
위험도 계산과 입력 일치 검증은 시스템이 하므로 risk_score는 0으로 둔다.
빈도 판단은 사고이력, 표준 HAZOP, 사용자 비고, 일반 HAZOP 규칙 순서로 근거를 찾는다.
강도 판단은 severity-estimation Skill의 기준표를 따르고 MSDS 물질 위험성과 사고 영향 범위를 핵심 근거로 사용한다.
Workflow가 모든 입력 물질의 MSDS를 최초 조회했다. 초안 중 정보가 부족한 경우에만 lookup_msds_detail Tool로 보완 조회한다.
사고이력이나 표준 HAZOP 데이터가 부족하면 확인 필요라고 명시한다.
각 판단에는 한국어 근거를 작성한다.
작성을 마친 뒤 별도의 risk-review-agent가 독립 검토하므로 스스로 검토 완료라고 주장하지 않는다.
""".strip()


def _review_system_prompt() -> str:
    return """
너는 초안 작성자와 분리된 독립 risk-review-agent이다.
작업을 시작할 때 hazop-risk-review, severity-estimation, standard-hazop-comparison Skill의 SKILL.md 전체를 read_file로 반드시 읽고 따른다.
시스템 검증을 통과한 #3 위험성평가 전체 Row의 의미, 논리, 근거 품질을 검토한다.
원인-결과 연결, 고위험 물질 강도 과소평가, 안전조치의 예방/완화 역할, MSDS 모순, 사고이력·표준 HAZOP 대비 과소평가를 확인한다.
필요한 정보가 부족한 경우에만 MSDS 상세, 사고이력, 표준 HAZOP Tool로 보완 조회한다.
문제가 있으면 지적만 하지 말고 risk_rows 전체에 수정 내용을 반영한다.
Node, 변수, Guideword, Row 개수와 no는 절대 바꾸지 않는다.
위험도는 시스템이 다시 계산하므로 risk_score는 0으로 둔다.
""".strip()


def _action_system_prompt() -> str:
    return """
너는 #4 조치계획서를 작성하는 action-plan-agent이다.
작업을 시작할 때 hazop-action-plan과 severity-estimation Skill의 SKILL.md 전체를 read_file로 반드시 읽고 따른다.
독립 검토가 반영되고 시스템이 위험도 9 이상으로 선별한 Row만 대상으로 LLM 초안을 작성한다.
현재 안전조치의 예방/완화 역할을 구분해 부족한 방어를 구체적인 개선권고사항으로 보완한다.
필요한 정보가 부족한 경우에만 MSDS 상세, 사고이력, 표준 HAZOP Tool로 보완 조회한다.
조치가 발생 가능성만 낮춘다면 물질 자체의 피해 강도를 임의로 낮추지 않는다.
조치 후 빈도는 1~5, 강도는 1~4 범위로 제안하고 근거를 반드시 작성한다.
조치 후 위험도는 시스템이 계산한다.
""".strip()


def _risk_user_prompt(context: HazopDraftContext) -> str:
    return f"""
작업: #3 위험성평가 초안을 생성하라.

출력 형식:
- structured_response의 risk_rows에 RiskAssessmentRow 배열을 넣어라.
- review_findings는 비워 둬도 된다. 독립 검토는 다음 단계의 risk-review-agent가 수행한다.

입력 정보:
{context.input_data.model_dump_json(indent=2)}

#1 노드리스트:
{[node.model_dump() for node in context.nodes]}

#2 가이드워드:
{[item.model_dump() for item in context.guidewords]}

MSDS 요약:
{ {key: value.__dict__ for key, value in context.msds_context.items()} }

업로드 위험도 기준표:
{_criteria_json(context)}

필수 규칙:
- guidewords에 있는 조합별로 정확히 하나의 risk row를 작성한다.
- node_order, node_name, parameter, guideword는 입력값 그대로 사용한다.
- risk_score는 0, risk_level은 "계산 전", action_required는 "계산 전"으로 둔다.
- decision_evidence, severity_evidence, frequency_evidence를 반드시 작성한다.
- 빈도 산정에는 사고이력과 표준 HAZOP 근거 부족 여부를 반드시 언급한다.
- 강도 근거에는 대상 물질, MSDS 위험 특성, 예상 영향 범위, 강도 기준표와의 연결을 포함한다.
- 빈도·강도는 위 업로드 기준표 문구에 직접 대입하고, 근거에 적용한 점수와 기준 문구를 포함한다.
- 기준표 requires_confirmation이 true이면 note와 근거에 "업로드 기준표 확인 필요"를 남긴다.
- 제공된 MSDS 요약만으로 부족할 때만 lookup_msds_detail을 호출한다.
""".strip()


def _review_user_prompt(
    context: HazopDraftContext,
    system_checked_rows: list[RiskAssessmentRow],
) -> str:
    return f"""
작업: 시스템 검증을 통과한 #3 위험성평가 초안을 독립적으로 의미 검토하고 보완하라.

출력 형식:
- structured_response의 risk_rows에 보완이 반영된 전체 RiskAssessmentRow 배열을 넣어라.
- review_findings에는 risk_assessment_no, category, message, resolution, requires_confirmation을 넣어라.

시스템 검증본:
{[row.model_dump() for row in system_checked_rows]}

입력 Guideword 원본:
{[item.model_dump() for item in context.guidewords]}

Workflow 최초 MSDS 조회 요약:
{ {key: value.__dict__ for key, value in context.msds_context.items()} }

업로드 위험도 기준표:
{_criteria_json(context)}

사용자 입력 및 사고/정비 이력:
{context.input_data.model_dump_json(indent=2)}

필수 규칙:
- 원인 현실성, 원인-결과 연결, 강도 과소평가, 안전조치의 예방/완화 역할, MSDS 모순을 확인한다.
- 표준 HAZOP보다 위험을 낮게 평가했다면 구체적인 차이 근거가 있는지 확인한다.
- no, node_order, node_name, parameter, guideword와 Row 개수는 입력 그대로 유지한다.
- 검토 수정 내용을 risk_rows에 실제로 반영한다.
- 강도는 동일한 업로드 기준표와 MSDS 출처를 사용해 재검토한다.
- risk_score는 0, risk_level은 "계산 전", action_required는 "계산 전"으로 돌려놓는다.
""".strip()


def _action_user_prompt(context: HazopDraftContext, high_risk_rows: list[RiskAssessmentRow]) -> str:
    return f"""
작업: 위험도 9 이상 항목에 대한 #4 조치계획서 초안을 생성하라.

출력 형식:
- structured_response의 action_rows에 ActionPlanRow 배열을 넣어라.
- review_findings에는 표준 HAZOP와 차이 또는 확인 필요 사항을 넣어라.

사용자 입력:
{context.input_data.model_dump_json(indent=2)}

고위험 위험성평가 Row:
{[row.model_dump() for row in high_risk_rows]}

MSDS 요약:
{ {key: value.__dict__ for key, value in context.msds_context.items()} }

업로드 위험도 기준표:
{_criteria_json(context)}

필수 규칙:
- action_rows는 high_risk_rows에 있는 항목만 대상으로 한다.
- high_risk_rows 각 항목마다 정확히 하나의 action row를 작성한다.
- risk_assessment_no는 원본 위험성평가 Row의 no를 사용한다.
- after_risk_score는 0으로 둬도 된다. 시스템이 다시 계산한다.
- evidence를 반드시 작성한다.
- 현재 안전조치와 겹치지 않는 구체적인 추가 조치를 제안한다.
- 제공된 MSDS 요약만으로 부족할 때만 lookup_msds_detail을 호출한다.
""".strip()


def _criteria_json(context: HazopDraftContext) -> str:
    if context.risk_criteria is None:
        return '{"source":"기준표 미전달","requires_confirmation":true,"items":[]}'
    return context.risk_criteria.model_dump_json(indent=2)


async def _demo_result(
    context: HazopDraftContext,
    events: list,
    reason: str,
    progress: ProgressCallback | None = None,
) -> HazopDraftResult:
    await _record_events(
        events,
        progress,
        [
            engine_event("risk-draft-agent demo fallback을 실행합니다.", "연결된 LLM이 없어 #3 위험성평가를 PoC 내장 규칙으로 임시 작성합니다.", kind="warning"),
            engine_event("Demo 생성 규칙을 적용합니다.", "AI Skill 실행이 아니라 PoC 코드에 넣어둔 규칙으로 원인/결과/안전조치 후보를 만듭니다.", kind="workflow"),
            engine_event("Demo 빈도·강도 규칙을 적용합니다.", "Skill read trace가 없는 fallback 코드이며, 빈도는 일반 HAZOP 기준, 강도는 MSDS 요약과 영향 범위를 사용합니다.", kind="workflow"),
        ],
    )
    risk_rows = validate_and_calculate_risk_rows(
        _generate_risk_rows_demo(context),
        context.guidewords,
        context.risk_criteria,
    )
    high_risk_rows = [row for row in risk_rows if row.risk_score >= 9]
    await _record_events(
        events,
        progress,
        [
            engine_event("risk-draft-agent 초안을 생성했습니다.", f"#3 위험성평가 Row {len(risk_rows)}건을 작성했습니다.", kind="result"),
            engine_event("1단계 시스템 검증을 완료했습니다.", f"입력 일치, 범위, 근거를 확인하고 위험도 9 이상 {len(high_risk_rows)}건을 선별했습니다.", kind="validation"),
            engine_event("risk-review-agent AI 의미 검토를 실행하지 못했습니다.", "Demo 모드에는 연결된 LLM이 없어 독립 의미 검토 결과가 아닙니다. Azure OpenAI 연결 후 반드시 실행됩니다.", kind="warning"),
            engine_event("action-plan-agent demo fallback을 실행합니다.", "고위험 항목의 조치계획을 PoC 내장 규칙으로 임시 작성합니다.", kind="warning"),
        ],
    )
    action_rows = validate_and_calculate_action_rows(_generate_action_rows_demo(context, high_risk_rows), high_risk_rows)
    await _record_event(
        events,
        engine_event(
            "action-plan-agent 초안을 생성했습니다.",
            f"#4 조치계획서 Row {len(action_rows)}건을 작성했습니다.",
            kind="result",
        ),
        progress,
    )
    return HazopDraftResult(
        risk_rows=risk_rows,
        action_rows=action_rows,
        review_findings=[
            ReviewFinding(
                category="AI 의미 검토 미실행",
                message="Demo 모드에는 연결된 LLM이 없어 독립 의미 검토를 실행하지 못했습니다.",
                resolution="Azure OpenAI 연결 후 risk-review-agent 재실행 필요",
                requires_confirmation=True,
            )
        ],
        events=events,
        mode="demo",
        fallback_reason=reason,
    )


async def _record_events(events: list, progress: ProgressCallback | None, new_events: list) -> None:
    for event in new_events:
        await _record_event(events, event, progress)


async def _record_event(events: list, event: Any, progress: ProgressCallback | None) -> None:
    events.append(event)
    if progress:
        await progress(event)


def _generate_risk_rows_demo(context: HazopDraftContext) -> list[RiskAssessmentRow]:
    joined_materials = " ".join(context.msds_context.keys()).lower()
    joined_hazards = " ".join(
        hazard for summary in context.msds_context.values() for hazard in summary.hazards
    ).lower()
    rows: list[RiskAssessmentRow] = []
    for index, item in enumerate(context.guidewords, start=1):
        text = f"{item.node_name} {item.parameter} {item.guideword}".lower()
        material_keys = [key.lower() for key in context.msds_context]
        water = bool(material_keys) and all("di water" in key or key == "water" for key in material_keys)
        # "인화성/독성 위험은 낮음" 같은 문장에 위험 단어가 포함돼도
        # DI Water를 고위험 물질로 오판하지 않도록 먼저 제외합니다.
        hazardous = not water and any(
            token in f"{joined_materials} {joined_hazards}"
            for token in [
                "silane", "hydrogen", "hf", "ammonia", "chlorine", "isopropyl",
                "dimethyl carbonate", "독성", "부식성", "인화성", "폭발",
            ]
        )
        leak = any(token in text for token in ["leak", "containment", "누출"])
        purge = any(token in text for token in ["purge", "no"])

        if hazardous and leak:
            frequency, severity = 3, 4
            deviation = f"{_material_label(context)} 누출"
            cause = "연결부 체결 불량, 밸브 패킹 손상, 피팅 누설"
            consequence = "가연성 또는 유해 분위기 형성, 화재/폭발 가능성, 작업자 대피 및 설비 손상"
            safeguard = "Gas Detector, 긴급차단밸브, 국소배기, 누설 점검 절차"
            decision = "Guideword가 Leak이고 MSDS상 고위험 물질이라 누출 시나리오를 핵심 위험으로 보았습니다."
            severity_reason = "누출 시 화재/폭발 또는 독성 노출 가능성이 있어 강도 4 후보입니다."
        elif hazardous and purge:
            frequency, severity = 2, 4
            deviation = f"{item.parameter} {item.guideword}로 인한 공정가스 제어 이탈"
            cause = "Sequence 오류, 밸브 동작 불량, 제어 설정 오류 또는 센서 이상"
            consequence = "잔류 가스 축적, 반응 이상, 배기계 가연성 분위기 형성"
            safeguard = "Purge Sequence, Flow Alarm, Recipe 권한관리, Scrubber 연동"
            decision = "위험 물질을 다루는 구간에서 Purge/유량 이탈은 잔류 가스와 반응 이상으로 연결될 수 있습니다."
            severity_reason = "물질 자체 위험성과 공정 영향이 커서 강도 4 후보입니다."
        elif water:
            frequency, severity = 2, 2 if leak else 3 if "flow" in text else 2
            deviation = f"{item.node_name} {item.parameter} {item.guideword} 상태"
            cause = "공급 지연, 펌프 정지, 밸브 오동작, 계측기 오차 또는 배관 체결 불량"
            consequence = "일시적 공급 불안정, 장비 세정 품질 저하, 주변 바닥 젖음"
            safeguard = "Low Alarm, 유량 알람, 운전원 점검, Drain 처리"
            decision = "DI Water는 물질 유해성은 낮지만 공급 중단/누수에 따른 설비 영향이 있어 평가 대상입니다."
            severity_reason = "주된 영향이 설비 정지/미끄럼/품질 저하 수준이라 강도 2~3 후보입니다."
        else:
            frequency, severity = 2, 3
            deviation = f"{item.parameter} {item.guideword} 상태 발생"
            cause = "설비 고장, 제어 이상, 운전 조건 이탈"
            consequence = "공정 지연, 품질 영향, 작업자 확인 필요"
            safeguard = "알람, 인터록, 정기 점검"
            decision = "입력된 Node/Guideword 조합상 정상 운전 의도에서 벗어나는 상태이므로 평가가 필요합니다."
            severity_reason = "물질 상세 위험성이 부족하여 중간 수준인 강도 3 후보로 두고 담당자 확인이 필요합니다."

        severity_criterion = _criterion_description(context, "강도", severity)
        frequency_criterion = _criterion_description(context, "빈도", frequency)
        msds_sources = ", ".join(sorted({summary.source for summary in context.msds_context.values()})) or "MSDS 출처 확인 필요"
        severity_reason = (
            f"{severity_reason} 적용 기준: 강도 {severity} - {severity_criterion}. "
            f"MSDS 출처: {msds_sources}."
        )
        criteria_note = (
            " / 업로드 위험도기준 확인 필요"
            if context.risk_criteria is None or context.risk_criteria.requires_confirmation
            else ""
        )

        rows.append(
            RiskAssessmentRow(
                no=index,
                node_order=item.node_order,
                node_name=item.node_name,
                parameter=item.parameter,
                guideword=item.guideword,
                deviation=deviation,
                cause=cause,
                consequence=consequence,
                existing_safeguard=safeguard,
                frequency=frequency,
                severity=severity,
                risk_score=0,
                risk_level="계산 전",
                action_required="계산 전",
                decision_evidence=[AgentEvidence(reason=decision, source="Node/Guideword + MSDS")],
                severity_evidence=[AgentEvidence(reason=severity_reason, source="MSDS 위험성 + 영향 범위")],
                frequency_evidence=[
                    AgentEvidence(
                        reason=(
                            "현재 PoC에는 사고이력 DB와 표준 HAZOP 문서 조회 인덱스가 없어 "
                            f"Guideword 특성과 사용자 비고를 기준으로 빈도 {frequency} 후보를 제안합니다. "
                            f"적용 기준: {frequency_criterion}."
                        ),
                        source="IncidentHistoryAnalysisSkill + FrequencyEstimationSkill fallback",
                    )
                ],
                note="Deepagent fallback 초안 - 사고이력/표준 HAZOP 확인 필요" + criteria_note,
            )
        )
    return rows


def _generate_action_rows_demo(
    context: HazopDraftContext,
    high_risk_rows: list[RiskAssessmentRow],
) -> list[ActionPlanRow]:
    rows: list[ActionPlanRow] = []
    for index, risk in enumerate(high_risk_rows, start=1):
        after_frequency = 1 if risk.frequency <= 3 else 2
        rows.append(
            ActionPlanRow(
                no=index,
                risk_assessment_no=risk.no,
                node_name=risk.node_name,
                recommendation=_recommendation_for(risk),
                after_frequency=after_frequency,
                after_severity=risk.severity,
                after_risk_score=0,
                evidence=[
                    AgentEvidence(
                        reason="개선조치는 사고 발생 가능성을 낮추는 방향이므로 조치 후 빈도를 낮춰 후보값을 제안합니다.",
                        source="HazopActionPlanSkill fallback",
                    ),
                    AgentEvidence(
                        reason=(
                            "물질 자체 위험성은 바뀌지 않으므로 조치 후 강도는 유지했습니다. "
                            f"적용 기준: 강도 {risk.severity} - {_criterion_description(context, '강도', risk.severity)}."
                        ),
                        source="MSDS 위험성 + 업로드 위험도기준",
                    ),
                ],
                note="실제 적용 가능성 및 표준 HAZOP 차이 확인 필요",
            )
        )
    return rows


def _recommendation_for(risk: RiskAssessmentRow) -> str:
    text = f"{risk.parameter} {risk.guideword} {risk.consequence}".lower()
    if "누출" in risk.deviation or "leak" in text:
        return "누설 감지 알람과 긴급차단밸브 연동 로직을 검증하고, 연결부 체결 후 누설 확인 절차를 강화한다."
    if "purge" in text or "퍼지" in text:
        return "Purge 완료 신호 없이는 공정가스 공급이 불가하도록 인터록을 검증하고 정기 점검 항목에 반영한다."
    if "flow" in text or "유량" in text:
        return "High/Low Flow Alarm 설정값을 재검토하고 Recipe 변경 승인 절차 및 계측기 교정 주기를 강화한다."
    return "현재 안전조치의 작동 여부를 검증하고, 알람/인터록/점검 절차의 누락 항목을 보완한다."


def _material_label(context: HazopDraftContext) -> str:
    names = [value.material for value in context.msds_context.values()]
    return "/".join(names) if names else "물질"


def _criterion_description(context: HazopDraftContext, category: str, score: int) -> str:
    if context.risk_criteria is None:
        return "기준표 미전달 - 담당자 확인 필요"
    for item in context.risk_criteria.items:
        if item.category == category and item.score == str(score):
            return item.description
    return f"{category} {score} 기준 누락 - 담당자 확인 필요"
