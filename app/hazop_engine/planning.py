from __future__ import annotations

import hashlib

from app.hazop_engine.context import (
    HazopDraftContext,
    HazopExecutionPlan,
    HazopPlanCandidate,
    HazopPlanStep,
)


def build_execution_plan(context: HazopDraftContext) -> HazopExecutionPlan:
    """고정 Workflow 안에서 입력에 맞는 근거 활용 전략을 선택합니다.

    쉽게 말하면 큰 작업 순서는 시스템이 고정하고, MSDS·사고이력·표준 HAZOP 중
    무엇을 먼저 볼지만 입력 정보의 충실도와 위험 특성으로 비교합니다. 점수는 LLM이
    임의로 만드는 값이 아니라 아래의 명시적인 시스템 규칙으로 계산합니다.
    """

    input_data = context.input_data
    history_available = bool(input_data.incident_maintenance_history.strip())
    standard_available = bool(input_data.standard_hazop_link.strip())
    msds_available = bool(context.msds_context)
    material_and_hazards = " ".join(
        [input_data.materials]
        + [summary.material for summary in context.msds_context.values()]
        + [hazard for summary in context.msds_context.values() for hazard in summary.hazards]
    ).lower()
    high_hazard = any(
        token in material_and_hazards
        for token in (
            "silane",
            "hydrogen",
            "ammonia",
            "암모니아",
            "hf",
            "chlorine",
            "염소",
            "toxic",
            "독성",
            "flammable",
            "인화",
            "폭발",
            "자연발화",
        )
    )

    common_tool_policy = {
        "lookup_msds_detail": "MSDS 요약만으로 물질 위험성과 영향 강도를 판단하기 어려울 때 호출",
        "lookup_incident_history": "사용자 이력만으로 빈도 근거가 부족할 때 호출",
        "lookup_standard_hazop": "원인·결과·안전조치 후보 또는 비교 근거가 부족할 때 호출",
    }
    candidates = [
        HazopPlanCandidate(
            candidate_id="A",
            name="MSDS 우선 + 사고이력 보완",
            description="물질 위험성과 영향 범위를 먼저 확인하고 현장 이력으로 빈도를 보완합니다.",
            reason=(
                "고위험 물질 신호가 있어 강도 과소평가 방지를 우선합니다."
                if high_hazard
                else "물질별 공식 유해성 근거를 공통 판단 기준으로 사용합니다."
            ),
            observed_conditions=[
                "Workflow 최초 MSDS 조회 결과 있음" if msds_available else "Workflow 최초 MSDS 조회 결과 없음",
                "고위험 물질 신호 발견" if high_hazard else "고위험 물질 신호 없음",
            ],
            limitations=[] if msds_available else ["공식 MSDS 조회 결과를 확보하지 못함"],
            evidence_priority=["MSDS", "사용자 사고·정비 이력", "표준 HAZOP"],
            review_focus=["물질 위험성 대비 강도 과소평가", "누출·노출 영향 범위", "빈도 근거 구체성"],
            tool_policy=common_tool_policy,
        ),
        HazopPlanCandidate(
            candidate_id="B",
            name="사고이력 우선 + MSDS 보완",
            description="현장 사고·정비 이력을 먼저 확인하고 MSDS로 영향 강도를 보완합니다.",
            reason=(
                "사용자 사고·정비 이력이 있어 실제 발생 가능성 판단에 활용할 수 있습니다."
                if history_available
                else "사용자 사고·정비 이력이 부족하여 일반 빈도 기준 의존도가 높습니다."
            ),
            observed_conditions=[
                "사용자 사고·정비 이력 입력 있음" if history_available else "사용자 사고·정비 이력 입력 없음",
                (
                    f"외부 사고이력 검색 결과 {context.incident_history_context.matched_count}건"
                    if context.incident_history_context.matched_count
                    else "외부 사고이력 검색 결과 없음"
                ),
            ],
            limitations=([] if history_available else ["현장 발생 가능성을 뒷받침할 사용자 이력이 부족함"])
            + ([] if context.incident_history_context.matched_count else ["실제 사고이력 DB 근거 없음"]),
            evidence_priority=["사용자 사고·정비 이력", "MSDS", "표준 HAZOP"],
            review_focus=["반복 고장과 빈도 점수 연결", "현장 이력 누락", "강도 근거 보완"],
            tool_policy=common_tool_policy,
        ),
        HazopPlanCandidate(
            candidate_id="C",
            name="표준 HAZOP 우선 + 입력 근거 보완",
            description="유사 HAZOP 사례를 먼저 비교하고 MSDS와 현장 이력으로 차이를 보완합니다.",
            reason=(
                "표준 HAZOP 참조값이 있어 누락 비교에 사용할 수 있습니다."
                if standard_available
                else "표준 HAZOP 참조값이 없어 비교 근거의 확인이 필요합니다."
            ),
            observed_conditions=[
                "표준 HAZOP Link/ID 입력 있음" if standard_available else "표준 HAZOP Link/ID 입력 없음",
                (
                    f"실제 표준 HAZOP 검색 결과 {context.standard_hazop_context.matched_count}건"
                    if context.standard_hazop_context.matched_count
                    else "실제 표준 HAZOP 검색 결과 없음"
                ),
            ],
            limitations=([] if standard_available else ["비교할 표준 HAZOP 참조값이 없음"])
            + ([] if context.standard_hazop_context.matched_count else ["입력된 Link/ID의 실제 문서 내용은 확인되지 않음"]),
            evidence_priority=["표준 HAZOP", "MSDS", "사용자 사고·정비 이력"],
            review_focus=["원인·결과 누락", "안전조치의 예방·완화 역할", "표준 사례 대비 과소평가"],
            tool_policy=common_tool_policy,
        ),
    ]
    # 숫자 점수 대신 누구나 설명할 수 있는 명시적 조건 분기로 전략을 선택합니다.
    if high_hazard and msds_available:
        selected_id = "A"
    elif history_available:
        selected_id = "B"
    elif standard_available:
        selected_id = "C"
    else:
        selected_id = "A"
    raw_id = f"{input_data.maker}|{input_data.model}|{len(context.nodes)}|{len(context.guidewords)}"
    plan_id = "PLAN-" + hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:10].upper()

    return HazopExecutionPlan(
        plan_id=plan_id,
        steps=[
            HazopPlanStep(number=1, name="입력 검증", mode="fixed", objective="Excel 입력 조합을 확정합니다.", success_condition="Node·변수·Guideword 원본과 Row 수가 일치"),
            HazopPlanStep(number=2, name="근거 확보", mode="adaptive", objective="선택 전략의 우선순위로 근거를 준비합니다.", success_condition="모든 점수 판단에 출처와 이유 존재"),
            HazopPlanStep(number=3, name="위험성평가 초안", mode="adaptive", objective="#3 원인·결과·안전조치와 점수 후보를 작성합니다.", success_condition="Guideword 조합별 정확히 1개 Row"),
            HazopPlanStep(number=4, name="독립 검토 및 수정", mode="required", objective="초안의 논리와 근거를 별도 Agent가 검토합니다.", success_condition="수정본 재검증 및 위험도 재계산 통과"),
            HazopPlanStep(number=5, name="고위험 조치계획", mode="conditional", objective="위험도 9 이상 항목의 #4 초안을 작성합니다.", success_condition="고위험 Row별 정확히 1개 조치계획"),
        ],
        success_conditions=[
            "입력 Node·변수·Guideword 변경 금지",
            "Guideword 조합별 정확히 1개 위험성평가 Row",
            "빈도 1~5, 강도 1~4 및 모든 판단 근거 존재",
            "위험도는 시스템 코드가 빈도 × 강도로 계산",
            "위험도 9 이상만 조치계획 작성",
        ],
        candidates=candidates,
        selected_candidate_id=selected_id,
    )


def plan_prompt(context: HazopDraftContext) -> str:
    """선택한 계획을 각 Agent 프롬프트에 넣기 쉬운 텍스트로 바꿉니다."""

    if context.execution_plan is None:
        return "구조화 실행계획 없음: 기본 HAZOP Skill 순서를 따른다."
    plan = context.execution_plan
    selected = plan.selected_candidate()
    tool_policy = "\n".join(f"- {name}: {condition}" for name, condition in selected.tool_policy.items())
    return (
        f"plan_id: {plan.plan_id}\n"
        f"선택 전략: {selected.name}\n"
        f"선택 이유: {selected.reason}\n"
        f"근거 우선순위: {' → '.join(selected.evidence_priority)}\n"
        f"검토 중점: {', '.join(selected.review_focus)}\n"
        f"Tool 호출 조건:\n{tool_policy}"
    )
