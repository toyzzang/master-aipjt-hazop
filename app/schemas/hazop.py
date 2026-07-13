from __future__ import annotations

from pydantic import BaseModel, Field


class NodeRow(BaseModel):
    """`#1 노드리스트` Sheet에서 읽은 Node 한 줄입니다."""

    node_order: int
    node_name: str


class GuidewordRow(BaseModel):
    """`#2 가이드워드` Sheet에서 읽은 평가 조합 한 줄입니다.

    HAZOP에서 실제 평가 단위는 보통 "Node + 변수(Parameter) + Guideword"입니다.
    예를 들어 "Gas Cabinet + Containment + Leak" 조합 하나가 평가 한 줄이 됩니다.
    """

    node_order: int
    node_name: str
    parameter: str
    guideword: str


class HazopInput(BaseModel):
    """웹 화면에서 사용자가 입력하는 기본 정보입니다."""

    maker: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    materials: str = Field(..., min_length=1)
    node_materials: str = ""
    standard_hazop_link: str = ""
    notes: str = ""
    incident_maintenance_history: str = ""


class AgentEvidence(BaseModel):
    """Agent가 왜 그렇게 판단했는지 남기는 근거입니다."""

    reason: str
    source: str = "agent"


class RiskAssessmentRow(BaseModel):
    """`#3 위험성평가`에 들어갈 생성 결과 한 줄입니다."""

    no: int
    node_order: int
    node_name: str
    parameter: str
    guideword: str
    deviation: str
    cause: str
    consequence: str
    existing_safeguard: str
    frequency: int
    severity: int
    risk_score: int
    risk_level: str
    action_required: str
    decision_evidence: list[AgentEvidence] = Field(default_factory=list)
    severity_evidence: list[AgentEvidence] = Field(default_factory=list)
    frequency_evidence: list[AgentEvidence] = Field(default_factory=list)
    note: str = ""


class ActionPlanRow(BaseModel):
    """`#4 조치계획서`에 들어갈 생성 결과 한 줄입니다."""

    no: int
    risk_assessment_no: int
    node_name: str
    recommendation: str
    after_frequency: int
    after_severity: int
    after_risk_score: int
    evidence: list[AgentEvidence] = Field(default_factory=list)
    note: str = ""


class HazopResult(BaseModel):
    """화면 표시와 Excel 출력에 함께 사용하는 최종 결과입니다."""

    request_id: str
    risk_rows: list[RiskAssessmentRow]
    action_rows: list[ActionPlanRow]
    output_excel: str | None = None
