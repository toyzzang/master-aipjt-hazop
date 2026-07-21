from __future__ import annotations

import hashlib

from app.hazop_engine.context import HazopDraftContext, HazopExecutionPlan, HazopPlanStep


def build_execution_plan(context: HazopDraftContext) -> HazopExecutionPlan:
    """모든 실행에서 동일하게 적용하는 안전한 5단계 Workflow를 만듭니다."""

    input_data = context.input_data
    raw_id = f"{input_data.maker}|{input_data.model}|{len(context.nodes)}|{len(context.guidewords)}"
    plan_id = "PLAN-" + hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:10].upper()
    return HazopExecutionPlan(
        plan_id=plan_id,
        steps=[
            HazopPlanStep(number=1, name="입력 검증", mode="fixed", objective="Excel 입력 조합을 확정합니다.", success_condition="Node·변수·Guideword 원본과 Row 수가 일치"),
            HazopPlanStep(number=2, name="근거 확보", mode="required", objective="MSDS·사고이력·표준 HAZOP 근거를 준비합니다.", success_condition="모든 점수 판단에 출처와 이유 존재"),
            HazopPlanStep(number=3, name="위험성평가 초안", mode="required", objective="#3 원인·결과·안전조치와 점수 후보를 작성합니다.", success_condition="Guideword 조합별 정확히 1개 Row"),
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
    )


def plan_prompt(context: HazopDraftContext) -> str:
    """고정 Workflow와 Tool 사용 원칙을 Agent Prompt용 텍스트로 만듭니다."""

    if context.execution_plan is None:
        return "고정 HAZOP Workflow가 준비되지 않았습니다."
    plan = context.execution_plan
    steps = "\n".join(
        f"{step.number}. {step.name}: {step.objective} / 완료 조건: {step.success_condition}"
        for step in plan.steps
    )
    conditions = "\n".join(f"- {condition}" for condition in plan.success_conditions)
    return (
        f"plan_id: {plan.plan_id}\n"
        f"고정 Workflow:\n{steps}\n"
        f"성공 조건:\n{conditions}\n"
        "Tool 사용 원칙:\n"
        "- MSDS 상세 조회: Workflow 요약만으로 유해성과 영향 강도를 판단할 수 없을 때만 호출\n"
        "- 사고이력 조회: 사용자 이력만으로 빈도 근거가 부족할 때만 호출\n"
        "- 표준 HAZOP: Workflow가 연결된 문서를 한 번만 선조회하며 모든 Agent가 같은 Context를 재사용"
    )
