from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from app.hazop_engine.agents.deepagent_factory import DeepAgentUnavailable, create_hazop_deep_agent
from app.hazop_engine.context import HazopDraftContext, HazopDraftResult
from app.hazop_engine.events import engine_event
from app.hazop_engine.tools.incident_history_tools import lookup_incident_history
from app.hazop_engine.tools.risk_tools import calculate_hazop_risk
from app.hazop_engine.tools.standard_hazop_tools import lookup_standard_hazop
from app.hazop_engine.tools.validation_tools import parse_action_rows, parse_risk_rows
from app.schemas.hazop import ActionPlanRow, AgentEvidence, RiskAssessmentRow
from app.services.llm import azure_openai_configured


class DeepAgentRiskOutput(BaseModel):
    """Deepagent가 반환해야 하는 #3 위험성평가 결과 형식입니다."""

    risk_rows: list[RiskAssessmentRow] = Field(default_factory=list)
    review_findings: list[str] = Field(default_factory=list)


class DeepAgentActionOutput(BaseModel):
    """Deepagent가 반환해야 하는 #4 조치계획서 결과 형식입니다."""

    action_rows: list[ActionPlanRow] = Field(default_factory=list)
    review_findings: list[str] = Field(default_factory=list)


async def generate_hazop_draft(context: HazopDraftContext) -> HazopDraftResult:
    """Deepagent 기반으로 HAZOP #3/#4 초안을 생성합니다.

    Deepagent를 실행할 수 없으면 PoC 흐름이 끊기지 않도록 규칙 기반 demo 결과로 fallback합니다.
    """

    events = [
        engine_event(
            "Deepagent HAZOP Engine을 준비했습니다.",
            "전문 판단이 필요한 #3/#4 초안 생성만 Deepagent 영역에서 처리합니다.",
        )
    ]

    if not azure_openai_configured():
        events.append(
            engine_event(
                "Deepagent 실행을 생략합니다.",
                "연결된 Azure OpenAI 설정이 없어 PoC 내장 생성기로 초안을 만듭니다.",
            )
        )
        return _demo_result(context, events, "연결된 Azure OpenAI 설정이 없습니다.")

    try:
        risk_rows = await _generate_risk_rows_with_deepagent(context)
        events.append(
            engine_event(
                "#3 위험성평가 Deepagent 초안을 생성했습니다.",
                f"작성자/검토자 흐름을 거쳐 위험성평가 Row {len(risk_rows)}건을 확보했습니다.",
            )
        )
        calculated_rows = _calculate_risk_rows(risk_rows)
        high_risk_rows = [row for row in calculated_rows if row.risk_score >= 9]
        events.append(
            engine_event(
                "위험도 9 이상 항목을 선별했습니다.",
                f"시스템 계산 결과 조치계획서 생성 대상은 {len(high_risk_rows)}건입니다.",
            )
        )
        action_rows = await _generate_action_rows_with_deepagent(context, high_risk_rows)
        events.append(
            engine_event(
                "#4 조치계획서 Deepagent 초안을 생성했습니다.",
                f"조치계획서 Row {len(action_rows)}건을 확보했습니다.",
            )
        )
        return HazopDraftResult(
            risk_rows=calculated_rows,
            action_rows=_calculate_action_rows(action_rows),
            events=events,
            mode="deepagent",
        )
    except Exception as exc:
        events.append(
            engine_event(
                "Deepagent 실행 중 fallback으로 전환합니다.",
                f"Deepagent 초안 생성이 완료되지 않아 PoC 내장 생성기를 사용합니다. 사유: {exc}",
            )
        )
        return _demo_result(context, events, str(exc))


async def _generate_risk_rows_with_deepagent(context: HazopDraftContext) -> list[RiskAssessmentRow]:
    agent = create_hazop_deep_agent(
        tools=[lookup_incident_history, lookup_standard_hazop, calculate_hazop_risk],
        system_prompt=_system_prompt(),
        response_format=DeepAgentRiskOutput,
    )
    result = await asyncio.to_thread(
        agent.invoke,
        {"messages": [{"role": "user", "content": _risk_user_prompt(context)}]},
    )
    data = _structured_response(result)
    return parse_risk_rows(data, context.guidewords)


async def _generate_action_rows_with_deepagent(
    context: HazopDraftContext,
    high_risk_rows: list[RiskAssessmentRow],
) -> list[ActionPlanRow]:
    if not high_risk_rows:
        return []
    agent = create_hazop_deep_agent(
        tools=[lookup_standard_hazop, calculate_hazop_risk],
        system_prompt=_system_prompt(),
        response_format=DeepAgentActionOutput,
    )
    result = await asyncio.to_thread(
        agent.invoke,
        {"messages": [{"role": "user", "content": _action_user_prompt(context, high_risk_rows)}]},
    )
    data = _structured_response(result)
    return parse_action_rows(data)


def _structured_response(result: Any) -> Any:
    if isinstance(result, dict) and "structured_response" in result:
        structured = result["structured_response"]
        if isinstance(structured, BaseModel):
            return structured.model_dump()
        return structured
    return result


def _system_prompt() -> str:
    return """
너는 HAZOP 초안 생성 Deepagent이다.
사용자가 제공한 #1 노드리스트와 #2 가이드워드 기준으로만 #3 위험성평가와 #4 조치계획서를 작성한다.
Node, 변수, Guideword를 새로 만들거나 추천하지 않는다.
빈도는 1~5 후보, 강도는 1~4 후보만 작성한다.
위험도 계산은 시스템이 하므로 #3 초안의 risk_score는 0으로 둔다.
빈도 판단은 사고이력, 표준 HAZOP, 사용자 비고, 일반 HAZOP 규칙 순서로 근거를 찾는다.
사고이력이나 표준 HAZOP 데이터가 부족하면 확인 필요라고 명시한다.
각 판단에는 한국어 근거를 작성한다.
가능하면 risk-draft-agent, risk-review-agent, action-plan-agent 역할을 나누어 작성과 검토를 수행한다.
""".strip()


def _risk_user_prompt(context: HazopDraftContext) -> str:
    return f"""
작업: #3 위험성평가 초안을 생성하고 검토하라.

출력 형식:
- structured_response의 risk_rows에 RiskAssessmentRow 배열을 넣어라.
- review_findings에는 검토자가 확인한 보완점 또는 확인 필요 사항을 넣어라.

입력 정보:
{context.input_data.model_dump_json(indent=2)}

#1 노드리스트:
{[node.model_dump() for node in context.nodes]}

#2 가이드워드:
{[item.model_dump() for item in context.guidewords]}

MSDS 요약:
{ {key: value.__dict__ for key, value in context.msds_context.items()} }

필수 규칙:
- guidewords에 있는 조합별로 정확히 하나의 risk row를 작성한다.
- node_order, node_name, parameter, guideword는 입력값 그대로 사용한다.
- risk_score는 0, risk_level은 "계산 전", action_required는 "계산 전"으로 둔다.
- decision_evidence, severity_evidence, frequency_evidence를 반드시 작성한다.
- 빈도 산정에는 사고이력과 표준 HAZOP 근거 부족 여부를 반드시 언급한다.
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

필수 규칙:
- action_rows는 high_risk_rows에 있는 항목만 대상으로 한다.
- risk_assessment_no는 원본 위험성평가 Row의 no를 사용한다.
- after_risk_score는 0으로 둬도 된다. 시스템이 다시 계산한다.
- evidence를 반드시 작성한다.
""".strip()


def _calculate_risk_rows(rows: list[RiskAssessmentRow]) -> list[RiskAssessmentRow]:
    calculated: list[RiskAssessmentRow] = []
    for row in rows:
        values = calculate_hazop_risk(row.frequency, row.severity)
        calculated.append(row.model_copy(update=values))
    return calculated


def _calculate_action_rows(rows: list[ActionPlanRow]) -> list[ActionPlanRow]:
    calculated: list[ActionPlanRow] = []
    for row in rows:
        values = calculate_hazop_risk(row.after_frequency, row.after_severity)
        calculated.append(
            row.model_copy(
                update={
                    "after_frequency": values["frequency"],
                    "after_severity": values["severity"],
                    "after_risk_score": values["risk_score"],
                }
            )
        )
    return calculated


def _demo_result(context: HazopDraftContext, events: list, reason: str) -> HazopDraftResult:
    risk_rows = _calculate_risk_rows(_generate_risk_rows_demo(context))
    high_risk_rows = [row for row in risk_rows if row.risk_score >= 9]
    action_rows = _calculate_action_rows(_generate_action_rows_demo(high_risk_rows))
    return HazopDraftResult(
        risk_rows=risk_rows,
        action_rows=action_rows,
        events=events,
        mode="demo",
        fallback_reason=reason,
    )


def _generate_risk_rows_demo(context: HazopDraftContext) -> list[RiskAssessmentRow]:
    joined_materials = " ".join(context.msds_context.keys()).lower()
    rows: list[RiskAssessmentRow] = []
    for index, item in enumerate(context.guidewords, start=1):
        text = f"{item.node_name} {item.parameter} {item.guideword}".lower()
        hazardous = any(token in joined_materials for token in ["silane", "hydrogen", "hf"])
        leak = any(token in text for token in ["leak", "containment", "누출"])
        purge = any(token in text for token in ["purge", "no"])
        water = "di water" in joined_materials or "water" in joined_materials

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
                            f"Guideword 특성과 사용자 비고를 기준으로 빈도 {frequency} 후보를 제안합니다."
                        ),
                        source="IncidentHistoryAnalysisSkill + FrequencyEstimationSkill fallback",
                    )
                ],
                note="Deepagent fallback 초안 - 사고이력/표준 HAZOP 확인 필요",
            )
        )
    return rows


def _generate_action_rows_demo(high_risk_rows: list[RiskAssessmentRow]) -> list[ActionPlanRow]:
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
                        reason="물질 자체 위험성은 바뀌지 않으므로 조치 후 강도는 유지했습니다.",
                        source="MSDS 위험성 판단",
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
