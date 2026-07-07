from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.hazop import ActionPlanRow, GuidewordRow, HazopInput, NodeRow, RiskAssessmentRow
from app.services.msds import MsdsSummary


class EngineEvent(BaseModel):
    """HAZOP Engine 내부 진행 상황을 화면 로그로 바꾸기 전의 구조화 이벤트입니다."""

    title: str
    detail: str


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
    msds_context: dict[str, MsdsSummary] = Field(default_factory=dict)
    incident_history_context: IncidentHistoryContext = Field(default_factory=IncidentHistoryContext)
    standard_hazop_context: StandardHazopContext = Field(default_factory=StandardHazopContext)
    events: list[EngineEvent] = Field(default_factory=list)


class HazopDraftResult(BaseModel):
    """HAZOP Engine이 기존 Agent 흐름으로 돌려주는 최종 초안 결과입니다."""

    risk_rows: list[RiskAssessmentRow]
    action_rows: list[ActionPlanRow]
    events: list[EngineEvent] = Field(default_factory=list)
    mode: str = "demo"
    fallback_reason: str = ""
