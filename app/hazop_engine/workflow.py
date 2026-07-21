from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

from app.hazop_engine.agents.deepagent_factory import DeepAgentUnavailable, create_hazop_deep_agent
from app.hazop_engine.context import AgentTrace, HazopDraftContext, HazopDraftResult
from app.hazop_engine.events import engine_event
from app.hazop_engine.planning import build_execution_plan, plan_prompt
from app.hazop_engine.tools.incident_history_tools import lookup_incident_history
from app.hazop_engine.tools.msds_tools import lookup_msds_detail
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

    # 전체 5단계 순서는 안전 규칙으로 고정하고 모든 Agent가 같은 Plan을 공유합니다.
    execution_plan = context.execution_plan or build_execution_plan(context)
    context.execution_plan = execution_plan

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
                    "Planning: DeepAgent가 실행계획을 수립하는 중입니다.",
                    "입력과 안전 규칙을 확인해 5단계 안팎의 작업 순서를 구성하고 있습니다.",
                    kind="planning",
                    agent_id="risk-draft-agent",
                    phase="progress",
                    loading=True,
                    event_key="risk-draft-agent:planning",
                ),
            ],
        )
        risk_started_at = time.perf_counter()
        risk_rows, risk_traces = await _generate_risk_rows_with_deepagent(context, events, progress)
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
                    "Planning: DeepAgent가 실행계획을 수립하는 중입니다.",
                    "검토 대상과 안전 규칙을 확인해 5단계 안팎의 독립 검토 순서를 구성하고 있습니다.",
                    kind="planning",
                    agent_id="risk-review-agent",
                    phase="progress",
                    loading=True,
                    event_key="risk-review-agent:planning",
                ),
            ],
        )
        reviewed_rows, review_findings, review_traces = await _review_risk_rows_with_deepagent(
            context, system_checked_rows, events, progress
        )
        await _record_trace_events(events, review_traces, progress, agent_id="risk-review-agent")
        reviewed_rows = _apply_reviewed_rows_for_findings(system_checked_rows, reviewed_rows, review_findings)
        review_findings = _normalize_review_findings(review_findings)
        reviewed_rows = _apply_confirmation_findings(reviewed_rows, review_findings)
        calculated_rows = validate_and_calculate_risk_rows(reviewed_rows, context.guidewords, context.risk_criteria)
        await _record_self_correction_events(
            events,
            system_checked_rows,
            calculated_rows,
            review_findings,
            progress,
            agent_id="risk-review-agent",
        )
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
                        "Planning: DeepAgent가 실행계획을 수립하는 중입니다.",
                        "고위험 항목과 안전 규칙을 확인해 5단계 안팎의 조치계획 작성 순서를 구성하고 있습니다.",
                        kind="planning",
                        agent_id="action-plan-agent",
                        phase="progress",
                        loading=True,
                        event_key="action-plan-agent:planning",
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
        action_rows, action_traces = await _generate_action_rows_with_deepagent(
            context, high_risk_rows, events, progress
        )
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
            execution_plan=execution_plan,
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


def _tool_call_detail(context: HazopDraftContext, agent_id: str, trace: AgentTrace) -> str:
    purposes = {
        "lookup_msds_detail": "MSDS 요약만으로 물질 위험성과 영향 강도를 판단하기 어려울 때 호출",
        "lookup_incident_history": "사용자 이력만으로 빈도 근거가 부족할 때 호출",
    }
    purpose = purposes.get(trace.name, "Agent 판단에 필요한 보완 근거 조회")
    return (
        f"호출 목적: {purpose}\n"
        f"입력: {trace.input_detail or '인수 없음'}\n"
        f"요청 Agent: {agent_id}"
    )


def _tool_result_detail(agent_id: str, trace: AgentTrace) -> str:
    destinations = {
        "lookup_msds_detail": "물질 위험성·강도·예방/완화 조치 판단 Context",
        "lookup_incident_history": "발생 빈도와 반복 고장 판단 Context",
    }
    destination = destinations.get(trace.name, f"{agent_id} 보완 판단 Context")
    return (
        f"실행 결과: {trace.result_detail or trace.detail or '상세 결과 없음'}\n"
        f"판단 반영 위치: {destination}\n"
        "표시 원칙: Tool 결과를 다음 판단 입력으로 전달했으며, 최종 채택 여부는 결과 근거에서 다시 확인합니다."
    )


def _tool_display_name(tool_name: str) -> str:
    """Tool 함수명을 시연 화면에서 바로 이해할 수 있는 업무 이름으로 바꿉니다."""

    return {
        "lookup_msds_detail": "MSDS 상세 위험성 조회",
        "lookup_incident_history": "사고·정비 이력 조회",
    }.get(tool_name, tool_name)


async def _invoke_agent_with_live_stage(
    agent: Any,
    payload: dict[str, Any],
    *,
    context: HazopDraftContext,
    events: list,
    progress: ProgressCallback | None,
    agent_id: str,
    required_skills: set[str],
    skill_detail: str,
    tool_detail: str,
    context_title: str,
    context_detail: str,
    activity_title: str,
    activity_detail: str,
    activity_kind: str,
) -> Any:
    """DeepAgent stream을 읽어 Planning 이후 로그를 실제 순서대로 공개합니다.

    `invoke()`가 끝난 뒤 trace 전체를 한꺼번에 붙이면 Planning이 로그 중간에
    끼어든 것처럼 보입니다. `stream(values)`에서 write_todos 완료를 처음 확인한
    순간 같은 Planning 블록을 완료 상태로 바꾸고, 그 다음 Skill/Tool/실행 상태를
    차례로 보냅니다. 테스트용 Agent처럼 stream이 없으면 invoke 결과로 동일하게 처리합니다.
    """

    planning_opened = False
    last_planning_detail = ""
    skills_confirmed = False
    tool_states: dict[str, str] = {}
    last_tool_progress: tuple[int, int] | None = None
    parallel_tools_observed = False
    activity_event_key = f"{agent_id}:activity"

    async def open_stage(snapshot: Any) -> None:
        nonlocal planning_opened, last_planning_detail, skills_confirmed, last_tool_progress, parallel_tools_observed
        traces = _extract_agent_traces(snapshot)
        planning_traces = [trace for trace in traces if trace.kind == "planning" and trace.success]
        if planning_traces and not planning_opened:
            planning_opened = True
            last_planning_detail = planning_traces[-1].detail
            completed_todos, total_todos = _planning_completion(last_planning_detail)
            await _record_events(events, progress, [
                engine_event(
                    f"Planning 실행 현황 · {completed_todos}/{total_todos} 완료",
                    last_planning_detail,
                    kind="planning",
                    agent_id=agent_id,
                    phase="progress",
                    loading=completed_todos < total_todos,
                    emphasis=True,
                    event_key=f"{agent_id}:planning",
                ),
                engine_event(
                    "실행할 Skill을 등록했습니다.",
                    skill_detail,
                    kind="skill",
                    agent_id=agent_id,
                    phase="progress",
                ),
                engine_event(
                    "사용 가능한 Tool을 연결했습니다.",
                    tool_detail,
                    kind="tool",
                    agent_id=agent_id,
                    phase="progress",
                ),
                engine_event(
                    context_title,
                    context_detail,
                    kind="agent",
                    agent_id=agent_id,
                    phase="progress",
                ),
            ])
        elif planning_traces and planning_traces[-1].detail != last_planning_detail:
            last_planning_detail = planning_traces[-1].detail
            completed_todos, total_todos = _planning_completion(last_planning_detail)
            await _record_event(
                events,
                engine_event(
                    f"Planning 실행 현황 · {completed_todos}/{total_todos} 완료",
                    last_planning_detail,
                    kind="planning",
                    agent_id=agent_id,
                    phase="progress",
                    loading=completed_todos < total_todos,
                    emphasis=True,
                    event_key=f"{agent_id}:planning",
                ),
                progress,
            )

        succeeded_skills = {trace.name for trace in traces if trace.kind == "skill" and trace.success}
        if planning_opened and required_skills <= succeeded_skills and not skills_confirmed:
            skills_confirmed = True
            stage_events = [
                engine_event(
                    "필수 Skill 적용을 확인했습니다.",
                    f"Agent 실행 기록에서 {len(required_skills)}개 Skill 본문을 읽고 적용한 것을 확인했습니다: "
                    + ", ".join(sorted(required_skills)),
                    kind="skill",
                    agent_id=agent_id,
                    phase="progress",
                ),
                engine_event(
                    activity_title,
                    activity_detail,
                    kind=activity_kind,
                    agent_id=agent_id,
                    phase="progress",
                    loading=True,
                    emphasis=activity_kind == "self-correction",
                    event_key=activity_event_key,
                ),
            ]
            if agent_id == "risk-draft-agent":
                if context.incident_history_context.evidence:
                    stage_events.append(
                        engine_event(
                            "로컬 사고·정비 이력 저장소를 조회했습니다.",
                            (
                                f"{context.incident_history_context.dataset_title or 'PoC 사고·정비 이력'}에서 유사 이력 "
                                f"{context.incident_history_context.matched_count}건을 찾아 Agent 공통 Context에 저장했습니다. "
                                f"빈도 참고값: {context.incident_history_context.frequency_hint or '확인 필요'}\n"
                                f"자료 구분: {context.incident_history_context.data_notice or 'PoC 합성 샘플'}\n"
                                + "\n".join(context.incident_history_context.evidence[:3])
                            ),
                            kind="result" if context.incident_history_context.matched_count else "warning",
                            agent_id=agent_id,
                            phase="progress",
                            parent_kind=activity_kind,
                            parent_event_key=activity_event_key,
                            event_key="workflow:incident-history",
                        )
                    )
                if context.input_data.standard_hazop_link:
                    stage_events.append(
                        engine_event(
                            "로컬 표준 HAZOP 문서를 조회했습니다.",
                            (
                                f"{context.standard_hazop_context.document_title or context.input_data.standard_hazop_link} "
                                f"개정 {context.standard_hazop_context.revision or '확인 필요'}에서 유사 Row "
                                f"{context.standard_hazop_context.matched_count}건을 찾아 Agent 공통 Context에 저장했습니다.\n"
                                + "\n".join(context.standard_hazop_context.evidence[:3])
                            ),
                            kind="result" if context.standard_hazop_context.matched_count else "warning",
                            agent_id=agent_id,
                            phase="progress",
                            parent_kind=activity_kind,
                            parent_event_key=activity_event_key,
                            event_key="workflow:standard-hazop",
                        )
                    )
            await _record_events(events, progress, stage_events)

        # DeepAgent가 실제로 만든 Tool call id를 기준으로 시작과 완료를 한 번씩만
        # 보냅니다. 모델의 내부 사고를 추측하지 않고 SDK 메시지에서 확인한 사실만 표시합니다.
        tool_traces = [item for item in traces if item.kind == "tool"]
        latest_tool_traces: dict[str, AgentTrace] = {}
        for trace in tool_traces:
            trace_key = trace.trace_id or f"{trace.name}:{trace.input_detail}"
            latest_tool_traces[trace_key] = trace

        if sum(trace.status == "running" for trace in latest_tool_traces.values()) > 1:
            parallel_tools_observed = True

        if latest_tool_traces:
            projected_states = {**tool_states}
            projected_states.update({key: trace.status for key, trace in latest_tool_traces.items()})
            total_count = len(projected_states)
            completed_count = sum(status != "running" for status in projected_states.values())
            progress_state = (completed_count, total_count)
            if progress_state != last_tool_progress:
                last_tool_progress = progress_state
                parallel_label = "병렬 근거 조회" if parallel_tools_observed else "근거 조회"
                if activity_kind == "self-correction":
                    progress_title = activity_title
                    waiting_text = (
                        "Tool 결과를 근거 Context에 합쳤습니다. 이제 원인→결과 연결, MSDS 모순, "
                        "빈도·강도 근거와 수정 필요 Row를 검토하고 있습니다."
                        if completed_count == total_count
                        else "모든 조회 결과를 취합한 뒤 원인→결과 연결과 근거 모순 검토를 계속합니다."
                    )
                else:
                    progress_title = (
                        "Tool 결과를 취합해 Agent 결과를 생성 중입니다."
                        if completed_count == total_count
                        else activity_title
                    )
                    waiting_text = (
                        "조회 결과를 모델 Context에 전달했습니다. 구조화 결과를 생성하고 검증하는 중입니다."
                        if completed_count == total_count
                        else "모든 조회 결과가 도착하면 모델 Context에 합쳐 다음 작업을 계속합니다."
                    )
                await _record_event(
                    events,
                    engine_event(
                        progress_title,
                        f"{parallel_label} · {completed_count}/{total_count} 완료\n{waiting_text}",
                        kind=activity_kind,
                        agent_id=agent_id,
                        phase="progress",
                        loading=True,
                        emphasis=activity_kind == "self-correction",
                        event_key=activity_event_key,
                    ),
                    progress,
                )

        for trace_key, trace in latest_tool_traces.items():
            previous_status = tool_states.get(trace_key)
            if previous_status is None:
                await _record_event(
                    events,
                    engine_event(
                        _tool_display_name(trace.name),
                        _tool_call_detail(context, agent_id, trace),
                        kind="tool",
                        agent_id=agent_id,
                        phase="progress",
                        loading=trace.status == "running",
                        emphasis=True,
                        parent_kind=activity_kind,
                        parent_event_key=activity_event_key,
                        event_key=trace_key,
                    ),
                    progress,
                )
            if trace.status != "running" and previous_status != trace.status:
                await _record_event(
                    events,
                    engine_event(
                        _tool_display_name(trace.name),
                        _tool_result_detail(agent_id, trace),
                        kind="tool" if trace.success else "warning",
                        agent_id=agent_id,
                        phase="progress",
                        emphasis=True,
                        parent_kind=activity_kind,
                        parent_event_key=activity_event_key,
                        event_key=trace_key,
                    ),
                    progress,
                )
            tool_states[trace_key] = trace.status

    stream = getattr(agent, "stream", None)
    if not callable(stream):
        result = await asyncio.to_thread(agent.invoke, payload)
        await open_stage(result)
        return result

    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def produce() -> None:
        try:
            for snapshot in stream(payload, stream_mode="values"):
                loop.call_soon_threadsafe(queue.put_nowait, ("snapshot", snapshot))
        except Exception as exc:  # pragma: no cover - 실제 SDK/통신 오류 경로
            loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

    producer = asyncio.create_task(asyncio.to_thread(produce))
    result: Any = None
    stream_error: Exception | None = None
    while True:
        event_type, value = await queue.get()
        if event_type == "snapshot":
            result = value
            await open_stage(value)
        elif event_type == "error":
            stream_error = value
        else:
            break
    await producer
    if stream_error is not None:
        raise stream_error
    if result is None:
        raise ValueError("DeepAgent stream이 결과를 반환하지 않았습니다.")
    await open_stage(result)
    return result


async def _generate_risk_rows_with_deepagent(
    context: HazopDraftContext,
    events: list | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[list[RiskAssessmentRow], list[AgentTrace]]:
    agent_id = "risk-draft-agent"
    try:
        agent = create_hazop_deep_agent(
            tools=[lookup_msds_detail, lookup_incident_history],
            system_prompt=_risk_system_prompt(),
            response_format=DeepAgentRiskOutput,
            agent_name=agent_id,
        )
        result = await _invoke_agent_with_live_stage(
            agent,
            {"messages": [{"role": "user", "content": _risk_user_prompt(context)}]},
            context=context,
            events=events if events is not None else [],
            progress=progress,
            agent_id=agent_id,
            required_skills={"hazop-risk-draft", "frequency-estimation", "severity-estimation"},
            skill_detail=(
                "hazop-risk-draft: 원인·결과·안전조치·판단 근거 작성\n"
                "frequency-estimation: 사고이력과 HAZOP 근거로 빈도 판단\n"
                "severity-estimation: MSDS와 영향 범위로 강도 판단"
            ),
            tool_detail=(
                "lookup_msds_detail: 상세 유해성·누출 대응 보완 조회\n"
                "lookup_incident_history: 유사 사고이력 보완 조회\n"
                "표준 HAZOP: Workflow가 한 번 선조회한 공통 Context를 재사용"
            ),
            context_title="위험성평가 작성 Context Prompt를 구성했습니다.",
            context_detail=(
                f"{_draft_context_summary(context)}\n"
                "Excel의 Node·변수·Guideword, MSDS, 사고·정비 이력, 위험도 기준표를 하나의 LLM 입력 Context로 결합했습니다."
            ),
            activity_title="Tool 결과를 취합해 Agent 결과를 생성 중입니다.",
            activity_detail=(
                f"{_draft_context_summary(context)}\n"
                "Skill과 Context를 Azure OpenAI 모델에 전달해 #3 위험성평가 초안을 작성하고 있습니다."
            ),
            activity_kind="agent",
        )
        data = _structured_response(result)
        traces = _extract_agent_traces(result)
        _require_skill_reads(traces, {"hazop-risk-draft", "frequency-estimation", "severity-estimation"})
        _require_planning_trace(traces)
        return parse_risk_rows(data, context.guidewords), traces
    except Exception as exc:
        raise DeepAgentStageError(agent_id, "#3 결과 형식 및 필수 Skill 검증", exc) from exc


async def _review_risk_rows_with_deepagent(
    context: HazopDraftContext,
    system_checked_rows: list[RiskAssessmentRow],
    events: list | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[list[RiskAssessmentRow], list[ReviewFinding], list[AgentTrace]]:
    """별도 LLM 호출로 의미 검토를 수행하고 보완된 전체 Row를 받습니다."""

    agent_id = "risk-review-agent"
    try:
        agent = create_hazop_deep_agent(
            tools=[lookup_msds_detail, lookup_incident_history],
            system_prompt=_review_system_prompt(),
            response_format=DeepAgentReviewOutput,
            agent_name=agent_id,
        )
        result = await _invoke_agent_with_live_stage(
            agent,
            {"messages": [{"role": "user", "content": _review_user_prompt(context, system_checked_rows)}]},
            context=context,
            events=events if events is not None else [],
            progress=progress,
            agent_id=agent_id,
            required_skills={"hazop-risk-review", "severity-estimation", "standard-hazop-comparison"},
            skill_detail=(
                "hazop-risk-review: 원인·결과 연결과 근거 누락 검토\n"
                "severity-estimation: MSDS 대비 강도 과소평가 검토\n"
                "standard-hazop-comparison: 표준 사례 대비 위험 판단 비교"
            ),
            tool_detail=(
                "lookup_msds_detail: MSDS 모순 보완 조회\n"
                "lookup_incident_history: 빈도 근거 보완 조회\n"
                "표준 HAZOP: Workflow가 한 번 선조회한 공통 Context를 재사용"
            ),
            context_title="위험도 검토 Context Prompt를 구성했습니다.",
            context_detail=(
                f"{_review_context_summary(context, system_checked_rows)}\n"
                "Excel 원본, 초안, MSDS, 사고·정비 이력, 위험도 기준표를 독립 검토용 LLM Context로 결합했습니다."
            ),
            activity_title=f"Self-Correction · 전체 {len(system_checked_rows)}건 비교 검토 중",
            activity_detail=(
                f"{_review_context_summary(context, system_checked_rows)}\n"
                f"초안 {len(system_checked_rows)}건을 다음 공개 검토 기준으로 독립 검토합니다.\n"
                "1. Excel Node·변수·Guideword와 평가 Row 연결 보존\n"
                "2. 원인 → 결과 문장의 논리 연결과 안전조치 역할\n"
                "3. MSDS 유해성과 강도 판단의 모순·과소평가\n"
                "4. 사고이력·표준 HAZOP 대비 빈도와 누락 근거\n"
                "5. 수정본 전체 Row 반환 후 시스템 재계산 준비"
            ),
            activity_kind="self-correction",
        )
        data = _structured_response(result)
        traces = _extract_agent_traces(result)
        _require_skill_reads(traces, {"hazop-risk-review", "severity-estimation", "standard-hazop-comparison"})
        _require_planning_trace(traces)
        reviewed_rows = parse_risk_rows(data, context.guidewords)
        findings = data.get("review_findings", []) if isinstance(data, dict) else []
        normalized_findings = [
            {**item, "risk_assessment_no": item.get("risk_assessment_no") or "전체"}
            if isinstance(item, dict)
            else item
            for item in findings
        ]
        return reviewed_rows, [ReviewFinding.model_validate(item) for item in normalized_findings], traces
    except Exception as exc:
        raise DeepAgentStageError(agent_id, "검토 결과 형식 및 필수 Skill 검증", exc) from exc


async def _generate_action_rows_with_deepagent(
    context: HazopDraftContext,
    high_risk_rows: list[RiskAssessmentRow],
    events: list | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[list[ActionPlanRow], list[AgentTrace]]:
    if not high_risk_rows:
        return [], []
    agent_id = "action-plan-agent"
    try:
        agent = create_hazop_deep_agent(
            tools=[lookup_msds_detail, lookup_incident_history],
            system_prompt=_action_system_prompt(),
            response_format=DeepAgentActionOutput,
            agent_name=agent_id,
        )
        result = await _invoke_agent_with_live_stage(
            agent,
            {"messages": [{"role": "user", "content": _action_user_prompt(context, high_risk_rows)}]},
            context=context,
            events=events if events is not None else [],
            progress=progress,
            agent_id=agent_id,
            required_skills={"hazop-action-plan", "severity-estimation"},
            skill_detail=(
                "hazop-action-plan: 권고 조치·담당 부서·완료 기준 작성\n"
                "severity-estimation: 조치 후에도 남는 사고 영향 확인"
            ),
            tool_detail=(
                "lookup_msds_detail: 물질별 예방·완화 조치 보완 조회\n"
                "lookup_incident_history: 사고 재발 방지 조치 보완 조회\n"
                "표준 HAZOP: Workflow가 한 번 선조회한 공통 Context를 재사용"
            ),
            context_title="조치계획 작성 Context Prompt를 구성했습니다.",
            context_detail=(
                f"{_action_context_summary(context, high_risk_rows)}\n"
                "고위험 Excel Row, MSDS, 사고·정비 이력, 위험도 기준표를 조치계획 작성용 LLM Context로 결합했습니다."
            ),
            activity_title="Agent가 모델과 Tool을 사용해 작업 중입니다.",
            activity_detail=(
                f"{_action_context_summary(context, high_risk_rows)}\n"
                "고위험 Context와 Skill 기준을 Azure OpenAI 모델에 전달해 #4 조치계획서를 작성하고 있습니다."
            ),
            activity_kind="agent",
        )
        data = _structured_response(result)
        traces = _extract_agent_traces(result)
        _require_skill_reads(traces, {"hazop-action-plan", "severity-estimation"})
        _require_planning_trace(traces)
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
            status = "running" if tool_result is None else ("completed" if success else "failed")
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
                            trace_id=call_id,
                            status=status,
                        )
                    )
            elif name in {"lookup_msds_detail", "lookup_incident_history"}:
                traces.append(
                    AgentTrace(
                        name=name,
                        kind="tool",
                        success=success,
                        detail=f"호출 조건={args}",
                        trace_id=call_id,
                        status=status,
                        input_detail=json.dumps(args, ensure_ascii=False, default=str),
                        result_detail=_tool_result_summary(tool_result),
                    )
                )
            elif name == "write_todos":
                todos = _object_value(args, "todos") or []
                todo_lines = []
                for index, todo in enumerate(todos, start=1):
                    content = str(_object_value(todo, "content") or _object_value(todo, "task") or "실행 항목")
                    content = _localize_todo_content(content)
                    status = str(_object_value(todo, "status") or "pending")
                    status_label = {
                        "pending": "대기",
                        "in_progress": "진행 중",
                        "completed": "완료",
                    }.get(status, status)
                    todo_lines.append(f"{index}. {content} [{status_label}]")
                traces.append(
                    AgentTrace(
                        name="DeepAgent Planning",
                        kind="planning",
                        success=success,
                        detail="\n".join(todo_lines) or "Planning 항목을 구성했습니다.",
                        trace_id=call_id,
                        status=status,
                    )
                )
    return traces


def _require_skill_reads(traces: list[AgentTrace], required: set[str]) -> None:
    succeeded = {trace.name for trace in traces if trace.kind == "skill" and trace.success}
    missing = sorted(required - succeeded)
    if missing:
        raise ValueError("필수 Skill 본문 read_file 성공 trace가 없습니다: " + ", ".join(missing))


def _require_planning_trace(traces: list[AgentTrace]) -> None:
    if not any(trace.kind == "planning" and trace.success for trace in traces):
        raise ValueError("DeepAgent 기본 write_todos Planning trace가 없습니다.")


def _planning_completion(detail: str) -> tuple[int, int]:
    """공개 Todo 상태 문자열에서 완료 개수만 계산합니다.

    모델의 숨은 생각이 아니라 write_todos가 반환한 명시적 체크리스트 상태입니다.
    """

    todo_lines = [line for line in detail.splitlines() if line.strip()]
    completed = sum("[완료" in line for line in todo_lines)
    return completed, len(todo_lines)


def _localize_todo_content(content: str) -> str:
    """모델이 영어로 만든 공개 Todo를 시연 화면용 한국어 작업명으로 바꿉니다."""

    if re.search(r"[가-힣]", content):
        return content
    lowered = content.lower()
    if "read" in lowered and "skill" in lowered:
        return "필수 HAZOP·빈도·강도·표준 비교 Skill 문서를 읽고 적용합니다."
    if "verify" in lowered and ("input" in lowered or "combination" in lowered):
        return "입력 조합을 보존하고 전체 위험성평가 Row의 원인·결과·안전조치와 근거를 검토합니다."
    if "tool" in lowered and any(word in lowered for word in ("lookup", "evidence", "necessary", "missing")):
        return "추가 근거가 필요한지 판단하고 부족한 MSDS·사고이력·표준 HAZOP만 조회합니다."
    if any(word in lowered for word in ("correction", "corrected", "affected")) and "risk" in lowered:
        return "문제가 확인된 위험성평가 Row만 수정하고 나머지 Row는 그대로 유지합니다."
    if "return" in lowered and any(word in lowered for word in ("risk_rows", "action_rows", "review_findings", "result")):
        return "전체 구조화 결과와 검토 내역을 반환합니다."
    if "evidence" in lowered and "prior" in lowered:
        return "선택된 근거 우선순위를 적용합니다."
    if "draft" in lowered or "generate" in lowered:
        return "Agent 구조화 초안을 생성합니다."
    if "review" in lowered or "validate" in lowered or "check" in lowered:
        return "생성 결과의 누락과 기준 위반을 검토합니다."
    return "Agent 실행계획의 작업 항목을 수행합니다."


def _finalize_returned_planning_detail(detail: str) -> str:
    """실제 결과 반환 성공으로 마지막 Todo 하나만 안전하게 완료 처리합니다."""

    lines = [line for line in detail.splitlines() if line.strip()]
    incomplete = [index for index, line in enumerate(lines) if "[완료" not in line]
    if len(lines) > 0 and incomplete == [len(lines) - 1] and any(
        marker in lines[-1] for marker in ("[진행 중]", "[대기]")
    ):
        lines[-1] = re.sub(r"\[(?:진행 중|대기)\]", "[완료 · 시스템 확인]", lines[-1])
    return "\n".join(lines)


async def _record_trace_events(
    events: list,
    traces: list[AgentTrace],
    progress: ProgressCallback | None,
    agent_id: str | None = None,
) -> None:
    planning_traces = [trace for trace in traces if trace.kind == "planning" and trace.success]
    if planning_traces:
        final_plan = planning_traces[-1]
        final_detail = _finalize_returned_planning_detail(final_plan.detail)
        completed_todos, total_todos = _planning_completion(final_detail)
        await _record_event(
            events,
            engine_event(
                f"Planning 최종 실행 현황 · {completed_todos}/{total_todos} 완료",
                final_detail,
                kind="planning",
                agent_id=agent_id,
                phase="progress",
                emphasis=True,
                event_key=f"{agent_id}:planning" if agent_id else None,
            ),
            progress,
        )

    tool_traces = [trace for trace in traces if trace.kind == "tool"]
    if tool_traces:
        tool_lines = [
            f"{trace.name}: {'성공' if trace.success else '실패'} · {trace.detail}"
            for trace in tool_traces
        ]
        await _record_event(
            events,
            engine_event(
                "Tool 실행 결과를 확인했습니다.",
                "\n".join(tool_lines),
                kind="tool",
                agent_id=agent_id,
                phase="progress",
            ),
            progress,
        )


async def _record_self_correction_events(
    events: list,
    before_rows: list[RiskAssessmentRow],
    after_rows: list[RiskAssessmentRow],
    findings: list[ReviewFinding],
    progress: ProgressCallback | None,
    agent_id: str,
) -> None:
    """검토 전후 실제 차이를 찾아 수정·근거·재계산 로그를 남깁니다.

    LLM의 숨은 생각을 출력하지 않고, 반환된 구조화 결과와 시스템 계산값만 비교합니다.
    """

    before_by_no = {row.no: row for row in before_rows}
    summary_event_key = f"{agent_id}:self-correction-summary"
    changed_count = 0
    maintained_count = 0
    action_target_changed_count = 0
    changes: list[tuple[int, RiskAssessmentRow, RiskAssessmentRow, list[str], bool]] = []
    confirmation_count = sum(finding.requires_confirmation for finding in findings)
    finding_row_count = len({finding.risk_assessment_no for finding in findings if isinstance(finding.risk_assessment_no, int)})
    for after in after_rows:
        before = before_by_no.get(after.no)
        if before is None:
            continue
        changed_fields = _changed_review_fields(before, after)
        if not changed_fields:
            maintained_count += 1
            continue
        changed_count += 1
        before_action = "예" if before.risk_score >= 9 else "아니오"
        after_action = "예" if after.risk_score >= 9 else "아니오"
        if before_action != after_action:
            action_target_changed_count += 1
        changes.append((after.no, before, after, changed_fields, before_action != after_action))

    await _record_event(
        events,
        engine_event(
            "Self-Correction: 독립 검토와 수정 반영을 완료했습니다.",
            f"검토 의견 {len(findings)}건 · 의견이 지정한 Row {finding_row_count}건 · 담당자 확인 필요 {confirmation_count}건\n"
            f"전체 {len(after_rows)}개 Row 중 실제 수정 {changed_count}개, 그대로 유지 {maintained_count}개, "
            f"조치계획 대상 변경 {action_target_changed_count}개입니다. 담당자 확인 필요 건수는 수정 Row 수와 별도입니다.\n"
            "대표 카드에서는 '수정 이유 → 적용 내용 → 위험도/조치대상 변화'만 확인하면 됩니다.\n"
            "대표 변경은 최대 3건만 표시합니다. 선정 순서: ① 조치계획 대상 변경 "
            "② 위험도 점수 변경 ③ 그 밖의 원인·결과·안전조치·근거 변경. 같은 순위는 평가 Row 번호가 빠른 순서입니다.\n"
            "전체 검토 내역은 아래 '초안 검토 및 보완 내역' 표에서 확인할 수 있습니다.",
            kind="self-correction",
            agent_id=agent_id,
            phase="progress",
            emphasis=True,
            event_key=summary_event_key,
        ),
        progress,
    )

    # 영상에서 읽을 수 있도록 조치 대상 변경 → 점수 변경 → 기타 변경 순서로
    # 대표 Row만 최대 3건 표시하고 전체 내역은 결과 표에 남깁니다.
    ranked = sorted(
        changes,
        key=lambda item: (
            not item[4],
            item[1].risk_score == item[2].risk_score,
            item[0],
        ),
    )
    findings_by_no: dict[int | str, list[ReviewFinding]] = {}
    for finding in findings:
        findings_by_no.setdefault(finding.risk_assessment_no, []).append(finding)

    for row_no, before, after, changed_fields, action_changed in ranked[:3]:
        related = [*findings_by_no.get("전체", []), *findings_by_no.get(row_no, [])]
        issue = " / ".join(finding.message for finding in related) or "검토 전후 구조화 결과 비교에서 차이를 확인했습니다."
        resolution = " / ".join(finding.resolution for finding in related) or ", ".join(changed_fields) + " 항목을 수정했습니다."
        evidence = _row_evidence_summary(after)
        before_action = "예" if before.risk_score >= 9 else "아니오"
        after_action = "예" if after.risk_score >= 9 else "아니오"
        action_line = (
            f"조치계획 대상: {before_action} → {after_action}"
            if action_changed
            else f"조치계획 대상: {after_action} 유지"
        )
        await _record_event(
            events,
            engine_event(
                f"Self-Correction 대표 변경 · 평가 {row_no:03d} · {after.node_name} · {after.parameter}/{after.guideword}",
                f"수정 이유: {issue}\n"
                f"적용 내용: {resolution}\n"
                f"위험도: {before.frequency}×{before.severity}={before.risk_score} → "
                f"{after.frequency}×{after.severity}={after.risk_score} (시스템 재계산)\n"
                f"판정: {action_line}\n"
                f"핵심 근거: {evidence}\n"
                f"변경 항목: {', '.join(changed_fields)}",
                kind="self-correction",
                agent_id=agent_id,
                phase="progress",
                emphasis=action_changed or before.risk_score != after.risk_score,
                parent_kind="self-correction",
                parent_event_key=summary_event_key,
                event_key=f"{summary_event_key}:row:{row_no}",
            ),
            progress,
        )

    if len(ranked) > 3:
        await _record_event(
            events,
            engine_event(
                "Self-Correction 나머지 변경 내역을 결과 표에 보관했습니다.",
                f"대표 3건 외 {len(ranked) - 3}건은 아래 '초안 검토 및 보완 내역' 표에서 확인할 수 있습니다.",
                kind="self-correction",
                agent_id=agent_id,
                phase="progress",
                parent_kind="self-correction",
                parent_event_key=summary_event_key,
                event_key=f"{summary_event_key}:remaining",
            ),
            progress,
        )


def _row_evidence_summary(row: RiskAssessmentRow) -> str:
    evidence = [
        *(item.reason for item in row.decision_evidence),
        *(item.reason for item in row.frequency_evidence),
        *(item.reason for item in row.severity_evidence),
    ]
    unique = list(dict.fromkeys(value.strip() for value in evidence if value.strip()))
    text = unique[0] if unique else "구조화 검토 근거 확인 필요"
    return text if len(text) <= 240 else text[:237].rstrip() + "…"


def _changed_review_fields(before: RiskAssessmentRow, after: RiskAssessmentRow) -> list[str]:
    labels = {
        "deviation": "이탈",
        "cause": "원인",
        "consequence": "결과",
        "existing_safeguard": "현재 안전조치",
        "frequency": "빈도",
        "severity": "강도",
        "decision_evidence": "판단 근거",
        "severity_evidence": "강도 근거",
        "frequency_evidence": "빈도 근거",
        "note": "비고",
    }
    return [label for field, label in labels.items() if getattr(before, field) != getattr(after, field)]


def _apply_reviewed_rows_for_findings(
    before_rows: list[RiskAssessmentRow],
    reviewed_rows: list[RiskAssessmentRow],
    findings: list[ReviewFinding],
) -> list[RiskAssessmentRow]:
    """검토 의견이 정확한 평가 번호를 지정한 Row에만 수정본을 적용합니다.

    모델이 전체 배열을 반환하면서 문제없는 문장을 다시 표현하더라도, finding이 없는
    Row는 시스템 검증본을 그대로 유지해 불필요한 전체 수정 표시를 막습니다.
    """

    allowed_numbers = {
        finding.risk_assessment_no
        for finding in findings
        if isinstance(finding.risk_assessment_no, int)
    }
    reviewed_by_no = {row.no: row for row in reviewed_rows}
    return [reviewed_by_no.get(row.no, row) if row.no in allowed_numbers else row for row in before_rows]


def _normalize_review_findings(findings: list[ReviewFinding]) -> list[ReviewFinding]:
    """같은 Row·구분·지적·조치가 반복된 검토 의견만 제거합니다."""

    normalized: list[ReviewFinding] = []
    seen: set[tuple[int | str, str, str, str, bool]] = set()
    for finding in findings:
        key = (
            finding.risk_assessment_no,
            finding.category.strip(),
            finding.message.strip(),
            finding.resolution.strip(),
            finding.requires_confirmation,
        )
        if key in seen:
            continue
        seen.add(key)
        normalized.append(finding)
    return normalized


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


def _tool_result_summary(message: Any, limit: int = 500) -> str:
    """콘솔/화면을 과도하게 채우지 않도록 Tool 결과를 짧게 정리합니다."""

    if message is None:
        return "실행 중"
    content = _message_value(message, "content")
    if isinstance(content, (dict, list)):
        text = json.dumps(content, ensure_ascii=False, default=str)
    else:
        text = str(content or "결과 본문 없음")
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[:limit].rstrip() + "…"


def _apply_confirmation_findings(
    rows: list[RiskAssessmentRow],
    findings: list[ReviewFinding],
) -> list[RiskAssessmentRow]:
    """담당자 확인이 필요한 검토 의견을 최종 Excel의 Risk Row 비고에도 남깁니다."""

    confirmation_by_no: dict[int | str, list[str]] = {}
    for finding in findings:
        if finding.requires_confirmation and isinstance(finding.risk_assessment_no, int):
            confirmation_by_no.setdefault(finding.risk_assessment_no, []).append(finding.message)

    updated: list[RiskAssessmentRow] = []
    for row in rows:
        messages = confirmation_by_no.get(row.no, [])
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
작업을 시작하면 DeepAgent 기본 write_todos Tool을 먼저 호출하여 아래 작업을 5개 안팎의 실행 항목으로 계획하고 그 순서대로 수행한다.
write_todos의 content는 사용자가 읽을 수 있도록 반드시 한국어로 작성한다.
계획에는 입력 조합 확인, 근거 우선순위 적용, #3 초안 작성, 자체 누락 확인, 구조화 결과 반환을 포함한다.
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
작업을 시작하면 DeepAgent 기본 write_todos Tool을 먼저 호출하여 아래 검토를 5개 안팎의 실행 항목으로 계획하고 그 순서대로 수행한다.
write_todos의 content는 사용자가 읽을 수 있도록 반드시 한국어로 작성한다.
계획에는 입력 조합 보존 확인, 검토 Skill 적용, 원인·결과·점수 근거 검토, 필요한 보완 Tool 판단, 수정본과 검토 내역 반환을 포함한다.
작업을 시작할 때 hazop-risk-review, severity-estimation, standard-hazop-comparison Skill의 SKILL.md 전체를 read_file로 반드시 읽고 따른다.
시스템 검증을 통과한 #3 위험성평가 전체 Row의 의미, 논리, 근거 품질을 검토한다.
원인-결과 연결, 고위험 물질 강도 과소평가, 안전조치의 예방/완화 역할, MSDS 모순, 사고이력·표준 HAZOP 대비 과소평가를 확인한다.
필요한 정보가 부족한 경우에만 MSDS 상세, 사고이력, 표준 HAZOP Tool로 보완 조회한다.
문제가 있으면 지적만 하지 말고 risk_rows 전체에 수정 내용을 반영한다.
실제 결함이 없는 Row는 문장 표현, 단어, 근거 순서, 비고를 포함해 시스템 검증본 그대로 반환한다. 문장 다듬기나 동의어 치환만을 위한 수정은 금지한다.
수정하는 모든 Row에는 해당 no를 risk_assessment_no로 명시한 review_finding을 최소 1개 작성한다.
risk_assessment_no="전체" 의견은 공통 확인사항 기록용이며 개별 Row 수정의 허가로 사용하지 않는다.
Node, 변수, Guideword, Row 개수와 no는 절대 바꾸지 않는다.
위험도는 시스템이 다시 계산하므로 risk_score는 0으로 둔다.
""".strip()


def _action_system_prompt() -> str:
    return """
너는 #4 조치계획서를 작성하는 action-plan-agent이다.
작업을 시작하면 DeepAgent 기본 write_todos Tool을 먼저 호출하여 아래 작업을 5개 안팎의 실행 항목으로 계획하고 그 순서대로 수행한다.
write_todos의 content는 사용자가 읽을 수 있도록 반드시 한국어로 작성한다.
계획에는 고위험 Row 확인, 조치 Skill 적용, 현재 방어의 부족점 분석, 필요한 보완 Tool 판단, 조치계획과 잔여위험 근거 반환을 포함한다.
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

이번 실행에서 시스템이 선택한 구조화 Plan:
{plan_prompt(context)}

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

Workflow가 선조회한 사고·정비 이력 Context:
{context.incident_history_context.model_dump_json(indent=2)}

Workflow가 선조회한 표준 HAZOP Context:
{context.standard_hazop_context.model_dump_json(indent=2)}

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

이번 실행에서 시스템이 선택한 구조화 Plan:
{plan_prompt(context)}

출력 형식:
- structured_response의 risk_rows에 보완이 반영된 전체 RiskAssessmentRow 배열을 넣어라.
- review_findings에는 risk_assessment_no, category, message, resolution, requires_confirmation을 넣어라.

시스템 검증본:
{[row.model_dump() for row in system_checked_rows]}

입력 Guideword 원본:
{[item.model_dump() for item in context.guidewords]}

Workflow 최초 MSDS 조회 요약:
{ {key: value.__dict__ for key, value in context.msds_context.items()} }

Workflow가 선조회한 사고·정비 이력 Context:
{context.incident_history_context.model_dump_json(indent=2)}

Workflow가 선조회한 표준 HAZOP Context:
{context.standard_hazop_context.model_dump_json(indent=2)}

업로드 위험도 기준표:
{_criteria_json(context)}

사용자 입력 및 사고/정비 이력:
{context.input_data.model_dump_json(indent=2)}

필수 규칙:
- 원인 현실성, 원인-결과 연결, 강도 과소평가, 안전조치의 예방/완화 역할, MSDS 모순을 확인한다.
- 사고·정비 이력보다 빈도를 낮게 평가했다면 공정 차이 또는 안전조치 차이 근거가 있는지 확인한다.
- 표준 HAZOP보다 위험을 낮게 평가했다면 구체적인 차이 근거가 있는지 확인한다.
- no, node_order, node_name, parameter, guideword와 Row 개수는 입력 그대로 유지한다.
- 검토 수정 내용을 risk_rows에 실제로 반영한다.
- 실제 오류나 근거 결함이 확인된 Row만 수정한다. 더 자연스러운 표현으로 바꾸기 위한 재작성은 하지 않는다.
- 수정한 각 Row마다 정확한 평가 no의 review_finding을 작성한다. finding이 없는 Row는 시스템이 원본 초안으로 되돌린다.
- 공통 의견은 risk_assessment_no="전체"로 기록할 수 있지만, 이 값으로 전체 Row를 수정하지 않는다.
- 강도는 동일한 업로드 기준표와 MSDS 출처를 사용해 재검토한다.
- risk_score는 0, risk_level은 "계산 전", action_required는 "계산 전"으로 돌려놓는다.
""".strip()


def _action_user_prompt(context: HazopDraftContext, high_risk_rows: list[RiskAssessmentRow]) -> str:
    return f"""
작업: 위험도 9 이상 항목에 대한 #4 조치계획서 초안을 생성하라.

이번 실행에서 시스템이 선택한 구조화 Plan:
{plan_prompt(context)}

출력 형식:
- structured_response의 action_rows에 ActionPlanRow 배열을 넣어라.
- review_findings에는 표준 HAZOP와 차이 또는 확인 필요 사항을 넣어라.

사용자 입력:
{context.input_data.model_dump_json(indent=2)}

고위험 위험성평가 Row:
{[row.model_dump() for row in high_risk_rows]}

MSDS 요약:
{ {key: value.__dict__ for key, value in context.msds_context.items()} }

Workflow가 선조회한 사고·정비 이력 Context:
{context.incident_history_context.model_dump_json(indent=2)}

Workflow가 선조회한 표준 HAZOP Context:
{context.standard_hazop_context.model_dump_json(indent=2)}

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
        execution_plan=context.execution_plan,
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
        standard_evidence = next(
            (
                evidence
                for evidence in context.standard_hazop_context.evidence
                if item.node_name.lower() in evidence.lower()
            ),
            context.standard_hazop_context.evidence[0] if context.standard_hazop_context.evidence else "",
        )
        incident_record = next(
            (
                record
                for record in context.incident_history_context.matched_records
                if item.node_name.lower() in str(record.get("node", "")).lower()
                and item.parameter.lower() == str(record.get("parameter", "")).lower()
                and item.guideword.lower() == str(record.get("guideword", "")).lower()
            ),
            None,
        )
        if incident_record:
            incident_frequency = int(incident_record.get("frequency_hint", frequency))
            frequency = max(1, min(5, incident_frequency))
            frequency_criterion = _criterion_description(context, "빈도", frequency)
            incident_evidence = (
                f"{incident_record.get('record_id')} · {incident_record.get('event_date')} · "
                f"{incident_record.get('summary')}"
            )
            decision += f" 로컬 사고·정비 이력 비교 근거: {incident_evidence}"
            frequency_reason = (
                f"동일 Node·변수·Guideword의 PoC 합성 사고·정비 이력에서 빈도 참고값 "
                f"{frequency}를 확인했습니다. 적용 기준: {frequency_criterion}. "
                f"비교 근거: {incident_evidence}"
            )
            frequency_source = "로컬 사고·정비 이력 JSON + 빈도 기준표"
            result_note = "Deepagent fallback 초안 - 로컬 사고·정비 이력 비교 적용"
        elif standard_evidence:
            decision += f" 로컬 표준 HAZOP 비교 근거: {standard_evidence}"
            frequency_reason = (
                f"로컬 표준 HAZOP {context.standard_hazop_context.document_title}의 유사 Row를 비교하고, "
                f"사용자 사고·정비 이력과 Guideword 특성을 함께 고려해 빈도 {frequency} 후보를 제안합니다. "
                f"적용 기준: {frequency_criterion}. 비교 근거: {standard_evidence}"
            )
            frequency_source = "로컬 표준 HAZOP + 사용자 사고·정비 이력 + 빈도 기준표"
            result_note = "Deepagent fallback 초안 - 로컬 표준 HAZOP 비교 적용"
        else:
            frequency_reason = (
                "일치하는 로컬 사고·정비 이력 또는 표준 HAZOP Row가 없어 "
                f"Guideword 특성과 사용자 비고를 기준으로 빈도 {frequency} 후보를 제안합니다. "
                f"적용 기준: {frequency_criterion}."
            )
            frequency_source = "IncidentHistoryAnalysisSkill + FrequencyEstimationSkill fallback"
            result_note = "Deepagent fallback 초안 - 사고이력/표준 HAZOP 확인 필요"

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
                decision_evidence=[AgentEvidence(reason=decision, source="Node/Guideword + MSDS + 사고·정비 이력 + 표준 HAZOP")],
                severity_evidence=[AgentEvidence(reason=severity_reason, source="MSDS 위험성 + 영향 범위")],
                frequency_evidence=[
                    AgentEvidence(
                        reason=frequency_reason,
                        source=frequency_source,
                    )
                ],
                note=result_note + criteria_note,
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
