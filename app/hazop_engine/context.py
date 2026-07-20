from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.hazop import (
    ActionPlanRow,
    GuidewordRow,
    HazopInput,
    NodeRow,
    ReviewFinding,
    RiskAssessmentRow,
    RiskCriteria,
)
from app.services.msds import MsdsSummary


class HazopPlanStep(BaseModel):
    """안전하게 고정된 HAZOP Workflow의 한 단계입니다."""

    number: int
    name: str
    mode: str
    objective: str
    success_condition: str


class HazopPlanCandidate(BaseModel):
    """고정 Workflow 안에서 비교하는 제한된 근거 활용 전략입니다."""

    candidate_id: str
    name: str
    description: str
    reason: str
    observed_conditions: list[str]
    limitations: list[str]
    evidence_priority: list[str]
    review_focus: list[str]
    tool_policy: dict[str, str]


class HazopExecutionPlan(BaseModel):
    """Agent들이 실제로 공유하는 구조화 실행계획입니다."""

    plan_id: str
    steps: list[HazopPlanStep]
    success_conditions: list[str]
    candidates: list[HazopPlanCandidate]
    selected_candidate_id: str

    def selected_candidate(self) -> HazopPlanCandidate:
        return next(item for item in self.candidates if item.candidate_id == self.selected_candidate_id)


class EngineEvent(BaseModel):
    """HAZOP Engine 내부 진행 상황을 화면 로그로 바꾸기 전의 구조화 이벤트입니다."""

    title: str
    detail: str
    kind: str = "agent"
    agent_id: str | None = None
    phase: str | None = None
    loading: bool = False


class AgentTrace(BaseModel):
    """DeepAgents 반환 메시지에서 확인한 실제 Skill/Tool 호출 기록입니다."""

    name: str
    kind: str
    success: bool
    detail: str = ""


class IncidentHistoryContext(BaseModel):
    """사고이력 분석 결과입니다.

    초기 PoC에는 실제 사고이력 저장소가 없으므로, 데이터 부재도 명시적인 근거로 남깁니다.
    """

    matched_count: int = 0
    evidence: list[str] = Field(default_factory=list)
    frequency_hint: int | None = None


class StandardHazopContext(BaseModel):
    """표준공정위험성평가서 참조 결과입니다."""

    reference_id: str = ""
    matched_count: int = 0
    evidence: list[str] = Field(default_factory=list)


class HazopDraftContext(BaseModel):
    """Deepagent와 Skill들이 함께 사용하는 작업 메모리입니다."""

    input_data: HazopInput
    nodes: list[NodeRow]
    guidewords: list[GuidewordRow]
    risk_criteria: RiskCriteria | None = None
    msds_context: dict[str, MsdsSummary] = Field(default_factory=dict)
    incident_history_context: IncidentHistoryContext = Field(default_factory=IncidentHistoryContext)
    standard_hazop_context: StandardHazopContext = Field(default_factory=StandardHazopContext)
    execution_plan: HazopExecutionPlan | None = None
    events: list[EngineEvent] = Field(default_factory=list)


class HazopDraftResult(BaseModel):
    """HAZOP Engine이 기존 Agent 흐름으로 돌려주는 최종 초안 결과입니다."""

    risk_rows: list[RiskAssessmentRow]
    action_rows: list[ActionPlanRow]
    review_findings: list[ReviewFinding] = Field(default_factory=list)
    execution_plan: HazopExecutionPlan | None = None
    events: list[EngineEvent] = Field(default_factory=list)
    mode: str = "demo"
    fallback_reason: str = ""
