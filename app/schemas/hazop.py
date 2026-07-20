from __future__ import annotations

from typing import Literal

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

    reason: str = Field(..., min_length=1)
    source: str = Field(default="agent", min_length=1)


class RiskCriterion(BaseModel):
    """업로드 Excel의 `위험도기준` Sheet 한 줄입니다."""

    category: Literal["빈도", "강도", "위험도"]
    score: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)


class RiskCriteria(BaseModel):
    """모든 Agent와 시스템이 함께 사용하는 빈도·강도·위험도 기준표입니다."""

    items: list[RiskCriterion] = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    requires_confirmation: bool = False


class ReviewFinding(BaseModel):
    """독립 검토 Agent가 무엇을 발견하고 어떻게 반영했는지 남기는 기록입니다."""

    risk_assessment_no: int | Literal["전체"] = "전체"
    category: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    resolution: str = Field(..., min_length=1)
    requires_confirmation: bool = False


class RiskAssessmentRow(BaseModel):
    """`#3 위험성평가`에 들어갈 생성 결과 한 줄입니다."""

    no: int = Field(..., ge=1)
    node_order: int = Field(..., ge=1)
    node_name: str = Field(..., min_length=1)
    parameter: str = Field(..., min_length=1)
    guideword: str = Field(..., min_length=1)
    deviation: str = Field(..., min_length=1)
    cause: str = Field(..., min_length=1)
    consequence: str = Field(..., min_length=1)
    existing_safeguard: str = Field(..., min_length=1)
    frequency: int = Field(..., ge=1, le=5)
    severity: int = Field(..., ge=1, le=4)
    risk_score: int = Field(..., ge=0, le=20)
    risk_level: str = Field(..., min_length=1)
    action_required: str = Field(..., min_length=1)
    decision_evidence: list[AgentEvidence] = Field(..., min_length=1)
    severity_evidence: list[AgentEvidence] = Field(..., min_length=1)
    frequency_evidence: list[AgentEvidence] = Field(..., min_length=1)
    note: str = ""


class ActionPlanRow(BaseModel):
    """`#4 조치계획서`에 들어갈 생성 결과 한 줄입니다."""

    no: int = Field(..., ge=1)
    risk_assessment_no: int = Field(..., ge=1)
    node_name: str = Field(..., min_length=1)
    recommendation: str = Field(..., min_length=1)
    after_frequency: int = Field(..., ge=1, le=5)
    after_severity: int = Field(..., ge=1, le=4)
    after_risk_score: int = Field(..., ge=0, le=20)
    evidence: list[AgentEvidence] = Field(..., min_length=1)
    note: str = ""


class HazopResult(BaseModel):
    """화면 표시와 Excel 출력에 함께 사용하는 최종 결과입니다."""

    request_id: str
    risk_rows: list[RiskAssessmentRow]
    action_rows: list[ActionPlanRow]
    review_findings: list[ReviewFinding] = Field(default_factory=list)
    execution_plan: dict | None = None
    output_excel: str | None = None
