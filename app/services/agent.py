from __future__ import annotations

import asyncio
import json
import os
import random
from pathlib import Path
from typing import AsyncIterator
from uuid import uuid4

from pydantic import ValidationError

from app.hazop_engine.context import HazopDraftContext
from app.hazop_engine.workflow import generate_hazop_draft
from app.schemas.hazop import (
    ActionPlanRow,
    AgentEvidence,
    GuidewordRow,
    HazopInput,
    HazopResult,
    RiskAssessmentRow,
)
from app.services.excel import export_result_excel, validate_and_parse_excel_with_criteria
from app.services.llm import azure_openai_configured, connected_model_label, generate_json_with_azure, missing_azure_openai_env
from app.services.msds import MsdsSummary, fetch_msds_summary_with_trace, material_names
from app.services.risk import action_required, calculate_risk_score, clamp_frequency, clamp_severity, risk_level


class AgentRunEvent:
    """SSE로 브라우저에 보낼 Agent 실행 이벤트입니다."""

    def __init__(self, event: str, data: dict):
        self.event = event
        self.data = data

    def to_sse(self) -> str:
        return f"event: {self.event}\ndata: {json.dumps(self.data, ensure_ascii=False)}\n\n"


async def run_hazop_agent(
    input_data: HazopInput,
    excel_path: Path,
    request_root: Path,
) -> AsyncIterator[AgentRunEvent]:
    """HAZOP Agent 전체 흐름을 실행하고, 중간 과정을 실시간 이벤트로 내보냅니다.

    쉽게 말하면 이 함수가 "AI Agent가 지금 무슨 일을 하는지"를 보여주는 무대입니다.
    실제 구현에서는 파일 검증/위험도 계산처럼 정답이 있는 일은 시스템 함수가 하고,
    원인/결과/안전조치 문장 생성처럼 판단과 문장화가 필요한 일은 Agent가 맡습니다.
    """

    request_id = uuid4().hex[:12]
    workdir = request_root / request_id
    workdir.mkdir(parents=True, exist_ok=True)

    yield _log("요청을 접수했습니다.", f"request_id={request_id} 작업 폴더를 만들었습니다.", kind="system")
    await _log_delay()

    try:
        nodes, guidewords, risk_criteria = validate_and_parse_excel_with_criteria(excel_path)
    except Exception as exc:
        yield AgentRunEvent(
            "agent_error",
            {
                "title": "Excel 입력 검증에 실패했습니다.",
                "message": str(exc) or exc.__class__.__name__,
                "stage": "excel_validation",
            },
        )
        return

    yield _log(
        "#1 노드리스트와 #2 가이드워드를 검증했습니다.",
        f"Node {len(nodes)}개, 평가 조합 {len(guidewords)}개를 확인했습니다. #3/#4는 비어 있어도 정상입니다.",
        kind="workflow",
    )
    await _log_delay()

    yield _log(
        "위험도 기준표를 준비했습니다.",
        f"{risk_criteria.source}에서 빈도·강도·위험도 기준 {len(risk_criteria.items)}건을 읽었습니다."
        + (" 업로드 기준표가 없어 담당자 확인이 필요합니다." if risk_criteria.requires_confirmation else ""),
        kind="workflow",
    )
    await _log_delay()

    materials = material_names(input_data.materials, input_data.node_materials)
    if not materials:
        materials = ["확인 필요"]

    yield _log(
        "Workflow 필수 MSDS 조회를 시작합니다.",
        f"입력된 모든 물질({', '.join(materials)})을 누락 없이 최초 1회씩 조회합니다. 이 단계는 AI 판단이 아닌 고정 절차입니다.",
        kind="system",
    )
    await _log_delay()

    msds_context: dict[str, MsdsSummary] = {}
    for material in materials:
        yield _log(
            "입력 물질 MSDS를 최초 조회합니다.",
            f"{material}의 유해성, 취급 기준, 누출 대응 정보를 Workflow가 1회 조회합니다.",
            kind="workflow",
        )
        await _log_delay()
        lookup = await fetch_msds_summary_with_trace(material)
        for step in lookup.steps:
            yield _log(step.title, step.detail, kind="workflow")
            await _log_delay()
        summary = lookup.summary
        msds_context[material.lower()] = summary
        yield _log(
            "MSDS 정보를 요약했습니다.",
            f"{summary.material}: {'; '.join(summary.hazards[:2])} / 출처: {summary.source} / 최초 조회 완료",
            kind="result",
        )
        await _log_delay()

    if input_data.standard_hazop_link:
        yield _log(
            "표준공정위험성평가서 참고 여부를 판단했습니다.",
            f"사용자가 제공한 Link/ID({input_data.standard_hazop_link})를 유사사례 근거로 사용합니다.",
            kind="workflow",
        )
        await _log_delay()
    else:
        yield _log(
            "표준공정위험성평가서 참고자료가 없습니다.",
            "표준 문서 근거가 부족한 항목은 결과 비고에 '확인 필요'를 표시합니다.",
            kind="workflow",
        )
        await _log_delay()

    if azure_openai_configured():
        yield _log(
            "Deepagent HAZOP Engine을 시작합니다.",
            f"연결된 {connected_model_label()} 모델로 #3 작성, 초안 검토 및 보완, 검토 반영, #4 조치계획 생성을 순서대로 수행합니다.",
            kind="agent",
        )
    else:
        missing_keys = ", ".join(missing_azure_openai_env())
        yield _log(
            "Deepagent HAZOP Engine을 Demo 모드로 시작합니다.",
            f"컨테이너/서버 프로세스에서 Azure OpenAI 설정을 찾지 못했습니다. 비어 있는 키: {missing_keys}. PoC 내장 생성기로 계속 진행합니다.",
            kind="warning",
        )
    await _log_delay()

    draft_context = HazopDraftContext(
        input_data=input_data,
        nodes=nodes,
        guidewords=guidewords,
        risk_criteria=risk_criteria,
        msds_context=msds_context,
    )
    draft_result = None
    progress_events: asyncio.Queue = asyncio.Queue()

    async def on_draft_progress(engine_event) -> None:
        await progress_events.put(engine_event)

    draft_task = asyncio.create_task(generate_hazop_draft(draft_context, progress=on_draft_progress))
    heartbeat_seconds = float(os.getenv("AGENT_LLM_HEARTBEAT_SECONDS", "2.0"))
    while not draft_task.done() or not progress_events.empty():
        try:
            engine_event = await asyncio.wait_for(progress_events.get(), timeout=max(0.5, heartbeat_seconds))
            yield _log(
                engine_event.title,
                engine_event.detail,
                kind=engine_event.kind,
                loading=engine_event.loading,
                agent_id=engine_event.agent_id,
                phase=engine_event.phase,
            )
            await _progress_log_delay(engine_event)
        except TimeoutError:
            if not draft_task.done():
                # 화면에 같은 대기 문장을 계속 쌓지 않고 SSE 연결만 조용히 유지합니다.
                yield AgentRunEvent("heartbeat", {"status": "waiting"})

    if draft_result is None:
        draft_result = await draft_task

    if draft_result.fallback_reason:
        yield _log(
            "Demo 모드 전환 사유를 기록했습니다.",
            f"치명 오류는 아니며, Deepagent 대신 PoC 내장 생성기로 계속 진행합니다. 사유: {draft_result.fallback_reason}",
            kind="warning",
        )
        await _log_delay()

    calculated_rows = draft_result.risk_rows
    action_rows = draft_result.action_rows
    high_risk_count = sum(row.risk_score >= 9 for row in calculated_rows)
    yield _log(
        "최종 결과의 시스템 검증을 완료했습니다.",
        f"위험성평가 {len(calculated_rows)}건의 빈도·강도 범위와 위험도 계산값을 확인했습니다. 위험도 9 이상은 {high_risk_count}건입니다.",
        kind="validation",
    )
    await _log_delay()

    if action_rows:
        yield _log(
            "#4 조치계획서 초안을 확보했습니다.",
            f"위험도 9 이상 항목 기준으로 조치계획서 {len(action_rows)}건을 생성했습니다.",
            kind="result",
        )
    else:
        yield _log(
            "#4 조치계획서 생성 대상이 없습니다.",
            "위험도 9 이상 항목이 없거나 검토 가능한 고위험 항목이 없어 별도 개선권고사항을 만들지 않습니다.",
            kind="result",
        )
    await _log_delay()

    output_excel = workdir / f"HAZOP_RESULT_{input_data.maker}_{input_data.model}.xlsx"
    export_result_excel(excel_path, output_excel, calculated_rows, action_rows)

    result = HazopResult(
        request_id=request_id,
        risk_rows=calculated_rows,
        action_rows=action_rows,
        review_findings=draft_result.review_findings,
        output_excel=str(output_excel),
    )
    result_path = workdir / "result.json"
    result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    yield _log("결과 Excel을 생성했습니다.", f"#3/#4 생성 결과를 {output_excel.name} 파일에 저장했습니다.", kind="result")
    await _log_delay()
    yield AgentRunEvent("done", result.model_dump())


def _generate_risk_rows_demo(
    input_data: HazopInput,
    guidewords: list[GuidewordRow],
    msds_context: dict[str, MsdsSummary],
) -> list[RiskAssessmentRow]:
    """키 없이도 PoC가 돌아가도록 만든 규칙 기반 demo Agent입니다.

    이 함수도 "아무 말 생성기"가 아니라, Node/Guideword/MSDS 키워드를 보고
    왜 그런 판단을 했는지 evidence를 같이 만듭니다.
    """

    joined_materials = " ".join(msds_context.keys()).lower()
    rows: list[RiskAssessmentRow] = []
    for index, item in enumerate(guidewords, start=1):
        text = f"{item.node_name} {item.parameter} {item.guideword}".lower()
        hazardous_gas = any(token in joined_materials for token in ["silane", "hydrogen", "hf"])
        leak = any(token in text for token in ["leak", "containment", "누출"])
        purge = any(token in text for token in ["purge", "no"])
        flow_more = "more" in text or "과다" in text
        water = "di water" in joined_materials or "water" in joined_materials

        if hazardous_gas and leak:
            severity = 4
            frequency = 3
            deviation = f"{_material_label(msds_context)} 누출"
            cause = "연결부 체결 불량, 밸브 패킹 손상, 피팅 누설"
            consequence = "가연성 또는 유해 분위기 형성, 화재/폭발 가능성, 작업자 대피 및 설비 손상"
            safeguard = "Gas Detector, 긴급차단밸브, 국소배기, 누설 점검 절차"
            decision_reason = "Guideword가 Leak이고 물질 MSDS에 가연성/유해성 위험이 있어 물질 위험성이 핵심 판단 요소입니다."
            severity_reason = "누출 시 작업자 대피, 화재/폭발, 설비 손상까지 이어질 수 있어 강도 4 후보로 제안합니다."
        elif hazardous_gas and (purge or flow_more):
            severity = 4
            frequency = 2 if purge else 3
            deviation = f"{item.parameter} {item.guideword}로 인한 공정가스 제어 이탈"
            cause = "Sequence 오류, 밸브 동작 불량, 제어 설정 오류 또는 센서 이상"
            consequence = "잔류 가스 축적, 반응 이상, 배기계 가연성 분위기 형성"
            safeguard = "Purge Sequence, Flow Alarm, Recipe 권한관리, Scrubber 연동"
            decision_reason = "위험 물질을 다루는 구간에서 유량/Purge 이탈은 잔류 가스와 반응 이상으로 연결될 수 있습니다."
            severity_reason = "물질 자체 위험성과 공정 영향이 커서 강도 4 후보로 제안합니다."
        elif water:
            severity = 2 if leak else 3 if "flow" in text else 2
            frequency = 2
            deviation = _water_deviation(item)
            cause = "공급 지연, 펌프 정지, 밸브 오동작, 계측기 오차 또는 배관 체결 불량"
            consequence = "일시적 공급 불안정, 장비 세정 품질 저하, 주변 바닥 젖음"
            safeguard = "Low Alarm, 유량 알람, 운전원 점검, Drain 처리"
            decision_reason = "DI Water는 물질 유해성은 낮지만 공급 중단/누수에 따른 설비 영향이 있어 평가 대상입니다."
            severity_reason = "MSDS상 중대 유해성은 낮고 주된 영향이 설비 정지/미끄럼/품질 저하 수준이라 강도 2~3 후보입니다."
        else:
            severity = 3
            frequency = 2
            deviation = f"{item.parameter} {item.guideword} 상태 발생"
            cause = "설비 고장, 제어 이상, 운전 조건 이탈"
            consequence = "공정 지연, 품질 영향, 작업자 확인 필요"
            safeguard = "알람, 인터록, 정기 점검"
            decision_reason = "입력된 Node/Guideword 조합상 정상 운전 의도에서 벗어나는 상태이므로 평가가 필요합니다."
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
                decision_evidence=[AgentEvidence(reason=decision_reason, source="Node/Guideword + MSDS")],
                severity_evidence=[AgentEvidence(reason=severity_reason, source="MSDS 위험성 + 영향 범위")],
                frequency_evidence=[
                    AgentEvidence(
                        reason=f"사용자 이력 데이터가 제한적이므로 Guideword 특성과 일반 점검 주기를 기준으로 빈도 {frequency} 후보를 제안합니다.",
                        source="PoC 빈도 판단 규칙",
                    )
                ],
                note="담당자 검토용 AI 초안",
            )
        )
    return rows


def _generate_action_rows_demo(high_risk_rows: list[RiskAssessmentRow]) -> list[ActionPlanRow]:
    rows: list[ActionPlanRow] = []
    for index, risk in enumerate(high_risk_rows, start=1):
        after_frequency = 1 if risk.frequency <= 3 else 2
        after_severity = risk.severity
        after_score = calculate_risk_score(after_frequency, after_severity)
        rows.append(
            ActionPlanRow(
                no=index,
                risk_assessment_no=risk.no,
                node_name=risk.node_name,
                recommendation=_recommendation_for(risk),
                after_frequency=after_frequency,
                after_severity=after_severity,
                after_risk_score=after_score,
                evidence=[
                    AgentEvidence(
                        reason="개선조치는 사고 발생 가능성을 낮추는 방향이므로 조치 후 빈도를 낮춰 후보값을 제안합니다.",
                        source="위험도 9 이상 조치 기준",
                    ),
                    AgentEvidence(
                        reason="물질 자체 위험성은 바뀌지 않으므로 조치 후 강도는 유지했습니다.",
                        source="MSDS 위험성 판단",
                    ),
                ],
                note="실제 적용 가능성 확인 필요",
            )
        )
    return rows


async def _generate_risk_rows_with_llm(
    input_data: HazopInput,
    guidewords: list[GuidewordRow],
    msds_context: dict[str, MsdsSummary],
) -> list[RiskAssessmentRow]:
    system_prompt, user_prompt = _build_risk_prompt(input_data, guidewords, msds_context)
    data = await generate_json_with_azure(system_prompt, user_prompt)
    return _parse_risk_rows(data)


async def _run_risk_llm_with_progress(
    input_data: HazopInput,
    guidewords: list[GuidewordRow],
    msds_context: dict[str, MsdsSummary],
) -> AsyncIterator[AgentRunEvent]:
    """#3 위험성평가 LLM 생성 진행 상황을 잘게 나누어 로그로 보여줍니다."""

    yield _log(
        "#3 위험성평가 생성 대상을 정리했습니다.",
        f"업로드 Excel 기준 평가 조합 {len(guidewords)}건을 LLM 입력으로 구성합니다.",
    )
    system_prompt, user_prompt = _build_risk_prompt(input_data, guidewords, msds_context)
    yield _log(
        "LLM 입력 Context를 구성했습니다.",
        f"Node/Guideword {len(guidewords)}건, MSDS 요약 {len(msds_context)}건, 사용자 입력정보를 하나의 JSON Context로 묶었습니다.",
    )
    yield _log(
        "연결된 모델에 #3 초안 생성을 요청했습니다.",
        "원인, 결과, 현재안전조치, 빈도/강도 후보와 근거를 JSON으로 생성하도록 요청했습니다.",
    )
    task = asyncio.create_task(generate_json_with_azure(system_prompt, user_prompt))
    step_index = 0
    while not task.done():
        await asyncio.sleep(_llm_heartbeat_seconds())
        if task.done():
            break
        title, detail = _risk_generation_step(step_index, len(guidewords))
        step_index += 1
        yield _log(title, detail)
    data = await task
    yield _log("연결된 모델의 응답을 수신했습니다.", f"{_shape_hint(data)} 형태의 JSON 응답을 받았습니다.")
    try:
        rows = _parse_risk_rows(data)
    except (KeyError, TypeError, ValidationError) as exc:
        raise ValueError(f"Azure OpenAI 위험성평가 결과 형식이 올바르지 않습니다: {_shape_hint(data)} / {exc}") from exc
    yield _log("위험성평가 JSON Schema 검증을 완료했습니다.", f"검증된 #3 위험성평가 Row {len(rows)}건을 확보했습니다.")
    yield AgentRunEvent("result", {"rows": rows})


async def _generate_action_rows_with_llm(
    input_data: HazopInput,
    high_risk_rows: list[RiskAssessmentRow],
    msds_context: dict[str, MsdsSummary],
) -> list[ActionPlanRow]:
    system_prompt, user_prompt = _build_action_prompt(input_data, high_risk_rows, msds_context)
    data = await generate_json_with_azure(system_prompt, user_prompt)
    return _parse_action_rows(data)


async def _run_action_llm_with_progress(
    input_data: HazopInput,
    high_risk_rows: list[RiskAssessmentRow],
    msds_context: dict[str, MsdsSummary],
) -> AsyncIterator[AgentRunEvent]:
    """#4 조치계획서 LLM 생성 진행 상황을 잘게 나누어 로그로 보여줍니다."""

    yield _log(
        "#4 조치계획서 생성 Context를 구성했습니다.",
        f"위험도 9 이상 항목 {len(high_risk_rows)}건과 MSDS 요약 {len(msds_context)}건을 조치계획서 입력으로 묶었습니다.",
    )
    system_prompt, user_prompt = _build_action_prompt(input_data, high_risk_rows, msds_context)
    yield _log(
        "연결된 모델에 #4 조치계획서 생성을 요청했습니다.",
        "개선권고사항, 조치 후 빈도/강도 후보, 조치 근거를 JSON으로 생성하도록 요청했습니다.",
    )
    task = asyncio.create_task(generate_json_with_azure(system_prompt, user_prompt))
    step_index = 0
    while not task.done():
        await asyncio.sleep(_llm_heartbeat_seconds())
        if task.done():
            break
        title, detail = _action_generation_step(step_index, len(high_risk_rows))
        step_index += 1
        yield _log(title, detail)
    data = await task
    yield _log("연결된 모델의 응답을 수신했습니다.", f"{_shape_hint(data)} 형태의 JSON 응답을 받았습니다.")
    try:
        checked = _parse_action_rows(data)
    except (KeyError, TypeError, ValidationError) as exc:
        raise ValueError(f"Azure OpenAI 조치계획서 결과 형식이 올바르지 않습니다: {_shape_hint(data)} / {exc}") from exc
    yield _log("조치계획서 JSON Schema 검증을 완료했습니다.", f"검증된 #4 조치계획서 Row {len(checked)}건을 확보했습니다.")
    yield AgentRunEvent("result", {"rows": checked})


def _parse_action_rows(data) -> list[ActionPlanRow]:
    rows = [ActionPlanRow.model_validate(item) for item in _extract_rows(data, "action_rows")]
    checked: list[ActionPlanRow] = []
    for row in rows:
        after_frequency = clamp_frequency(row.after_frequency)
        after_severity = clamp_severity(row.after_severity)
        checked.append(
            row.model_copy(
                update={
                    "after_frequency": after_frequency,
                    "after_severity": after_severity,
                    "after_risk_score": calculate_risk_score(after_frequency, after_severity),
                }
            )
        )
    return checked


def _parse_risk_rows(data) -> list[RiskAssessmentRow]:
    rows = _extract_rows(data, "risk_rows")
    return [RiskAssessmentRow.model_validate(item) for item in rows]


def _build_risk_prompt(
    input_data: HazopInput,
    guidewords: list[GuidewordRow],
    msds_context: dict[str, MsdsSummary],
) -> tuple[str, str]:
    """#3 위험성평가 생성을 위한 LLM 입력을 구성합니다."""

    return _system_prompt(), json.dumps(
        {
            "task": "#3 위험성평가 초안을 JSON으로 생성",
            "required_output_shape": {
                "risk_rows": [
                    {
                        "no": 1,
                        "node_order": 1,
                        "node_name": "업로드 Excel의 노드명",
                        "parameter": "업로드 Excel의 변수",
                        "guideword": "업로드 Excel의 가이드워드",
                        "deviation": "일탈",
                        "cause": "원인",
                        "consequence": "결과",
                        "existing_safeguard": "현재안전조치",
                        "frequency": 1,
                        "severity": 1,
                        "risk_score": 0,
                        "risk_level": "계산 전",
                        "action_required": "계산 전",
                        "decision_evidence": [{"reason": "판단 근거", "source": "근거 출처"}],
                        "severity_evidence": [{"reason": "강도 후보 근거", "source": "근거 출처"}],
                        "frequency_evidence": [{"reason": "빈도 후보 근거", "source": "근거 출처"}],
                        "note": "담당자 검토용 AI 초안",
                    }
                ]
            },
            "rules": [
                "반드시 최상위 JSON object로 응답한다.",
                "반드시 최상위 키는 risk_rows 하나를 사용한다.",
                "risk_rows는 배열이다.",
                "업로드 Excel의 node_name, parameter, guideword만 사용한다.",
                "frequency는 1~5, severity는 1~4 후보만 허용한다.",
                "risk_score는 0으로 둔다. 시스템이 계산한다.",
                "decision_evidence, severity_evidence, frequency_evidence를 반드시 작성한다.",
            ],
            "input": input_data.model_dump(),
            "guidewords": [item.model_dump() for item in guidewords],
            "msds": {key: value.__dict__ for key, value in msds_context.items()},
        },
        ensure_ascii=False,
    )


def _build_action_prompt(
    input_data: HazopInput,
    high_risk_rows: list[RiskAssessmentRow],
    msds_context: dict[str, MsdsSummary],
) -> tuple[str, str]:
    """#4 조치계획서 생성을 위한 LLM 입력을 구성합니다."""

    return _system_prompt(), json.dumps(
        {
            "task": "#4 조치계획서 초안을 JSON으로 생성",
            "required_output_shape": {
                "action_rows": [
                    {
                        "no": 1,
                        "risk_assessment_no": 1,
                        "node_name": "위험성평가의 노드명",
                        "recommendation": "개선권고사항",
                        "after_frequency": 1,
                        "after_severity": 1,
                        "after_risk_score": 0,
                        "evidence": [{"reason": "조치계획 근거", "source": "근거 출처"}],
                        "note": "실제 적용 가능성 확인 필요",
                    }
                ]
            },
            "rules": [
                "반드시 최상위 JSON object로 응답한다.",
                "반드시 최상위 키는 action_rows 하나를 사용한다.",
                "action_rows는 배열이다.",
                "위험도 9 이상 항목만 대상으로 한다.",
                "after_frequency는 1~5, after_severity는 1~4 후보만 허용한다.",
                "after_risk_score는 직접 계산해서 넣어도 되지만 시스템이 다시 검증한다.",
                "evidence를 반드시 작성한다.",
            ],
            "input": input_data.model_dump(),
            "high_risk_rows": [item.model_dump() for item in high_risk_rows],
            "msds": {key: value.__dict__ for key, value in msds_context.items()},
        },
        ensure_ascii=False,
    )


def _llm_heartbeat_seconds() -> float:
    return max(0.5, float(os.getenv("AGENT_LLM_HEARTBEAT_SECONDS", "2.0")))


def _risk_generation_step(step_index: int, row_count: int) -> tuple[str, str]:
    """#3 생성 대기 중 사용자가 이해하기 쉬운 진행 단계 문구를 만듭니다."""

    steps = [
        ("원인을 생성중입니다.", f"{row_count}개 평가 조합의 가능한 고장 원인과 운전 이탈 원인을 정리하고 있습니다."),
        ("결과를 생성중입니다.", "각 원인이 사람, 설비, 공정 품질에 어떤 영향으로 이어질 수 있는지 작성하고 있습니다."),
        ("현재 안전조치를 생성중입니다.", "알람, 인터록, 점검 절차처럼 이미 있을 수 있는 보호 장치를 정리하고 있습니다."),
        ("빈도와 강도 후보 근거를 생성중입니다.", "위험도는 시스템이 나중에 계산하므로, 모델은 빈도/강도 후보와 판단 근거만 준비합니다."),
    ]
    return steps[step_index % len(steps)]


def _action_generation_step(step_index: int, row_count: int) -> tuple[str, str]:
    """#4 생성 대기 중 사용자가 이해하기 쉬운 진행 단계 문구를 만듭니다."""

    steps = [
        ("개선권고사항을 생성중입니다.", f"위험도 9 이상 {row_count}개 항목에 대해 추가 조치 후보를 작성하고 있습니다."),
        ("조치 후 빈도 후보를 생성중입니다.", "개선조치가 사고 가능성을 얼마나 낮출 수 있을지 후보값을 정리하고 있습니다."),
        ("조치계획 근거를 생성중입니다.", "왜 이 개선권고사항이 필요한지 담당자가 검토할 수 있는 근거를 붙이고 있습니다."),
    ]
    return steps[step_index % len(steps)]


def _system_prompt() -> str:
    return """
너는 HAZOP 초안 생성 Agent이다.
사용자가 제공한 #1 노드리스트와 #2 가이드워드 기준으로만 #3 위험성평가와 #4 조치계획서를 작성한다.
Node, 변수, Guideword를 새로 만들거나 추천하지 않는다.
근거가 부족하면 확인 필요라고 표시한다.
빈도와 강도는 최종값이 아니라 후보값이다.
위험도 계산은 시스템이 하므로 위험성평가 생성 시 risk_score는 0으로 둔다.
각 판단에는 반드시 한국어 근거를 작성한다.
응답은 반드시 JSON object로만 한다.
위험성평가는 반드시 {"risk_rows": [...]} 형태로 응답한다.
조치계획서는 반드시 {"action_rows": [...]} 형태로 응답한다.
""".strip()


def _extract_rows(data, expected_key: str) -> list:
    """LLM JSON 응답에서 Row 배열을 꺼냅니다.

    LLM은 가끔 `risk_rows` 대신 `rows`, `data` 같은 키를 쓰거나,
    최상위에 배열을 바로 반환할 수 있습니다. PoC에서는 가능한 경우 복구해서
    사용자 흐름이 끊기지 않게 합니다.
    """

    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        raise TypeError(f"JSON object 또는 array가 필요하지만 {type(data).__name__}를 받았습니다.")
    if expected_key in data and isinstance(data[expected_key], list):
        return data[expected_key]
    for fallback_key in ["rows", "data", "items", "results"]:
        if fallback_key in data and isinstance(data[fallback_key], list):
            return data[fallback_key]
    if expected_key == "risk_rows":
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict) and "cause" in value[0]:
                return value
    if expected_key == "action_rows":
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict) and "recommendation" in value[0]:
                return value
    raise KeyError(expected_key)


def _shape_hint(data) -> str:
    if isinstance(data, dict):
        return f"응답 최상위 키={list(data.keys())}"
    if isinstance(data, list):
        return f"응답 최상위 타입=list, 길이={len(data)}"
    return f"응답 최상위 타입={type(data).__name__}"


def _recommendation_for(risk: RiskAssessmentRow) -> str:
    text = f"{risk.parameter} {risk.guideword} {risk.consequence}".lower()
    if "누출" in risk.deviation or "leak" in text:
        return "누설 감지 알람과 긴급차단밸브 연동 로직을 검증하고, 연결부 체결 후 누설 확인 절차를 강화한다."
    if "purge" in text or "퍼지" in text:
        return "Purge 완료 신호 없이는 공정가스 공급이 불가하도록 인터록을 검증하고 정기 점검 항목에 반영한다."
    if "flow" in text or "유량" in text:
        return "High/Low Flow Alarm 설정값을 재검토하고 Recipe 변경 승인 절차 및 계측기 교정 주기를 강화한다."
    return "현재 안전조치의 작동 여부를 검증하고, 알람/인터록/점검 절차의 누락 항목을 보완한다."


def _water_deviation(item: GuidewordRow) -> str:
    guideword = item.guideword.lower()
    parameter = item.parameter.lower()
    if "less" in guideword or "low" in guideword:
        return f"{item.node_name} {item.parameter} 부족"
    if "no" in guideword:
        return f"{item.node_name} {item.parameter} 없음"
    if "leak" in guideword:
        return f"{item.node_name} 누수"
    return f"{item.parameter} {item.guideword} 상태 발생"


def _material_label(msds_context: dict[str, MsdsSummary]) -> str:
    names = [value.material for value in msds_context.values()]
    return "/".join(names) if names else "물질"


def _log(
    title: str,
    detail: str,
    kind: str = "agent",
    loading: bool = False,
    agent_id: str | None = None,
    phase: str | None = None,
) -> AgentRunEvent:
    return AgentRunEvent(
        "log",
        {
            "title": title,
            "detail": detail,
            "kind": kind,
            "loading": loading,
            "agent_id": agent_id,
            "phase": phase,
        },
    )


async def _log_delay() -> None:
    """실시간 로그가 한 번에 몰려 나오지 않도록 짧게 쉼표를 둡니다.

    실제 업무에서는 MSDS 조회, LLM 호출, Excel 생성이 시간이 걸립니다.
    로컬 PoC에서는 일부 단계가 너무 빨라서 Agent가 생각 없이 찍는 느낌이 나므로,
    사용자가 흐름을 읽을 수 있을 정도의 작은 지연을 둡니다.
    """

    delay = float(os.getenv("AGENT_LOG_DELAY_SECONDS", "1.0"))
    if delay > 0:
        await asyncio.sleep(delay)


async def _progress_log_delay(engine_event) -> None:
    """전문 Agent의 세부 로그를 사용자가 읽을 수 있는 속도로 전달합니다.

    실제 Agent 작업은 별도 Task에서 계속 실행됩니다. 여기서는 이미 Queue에 들어온
    화면 이벤트만 불규칙한 간격으로 내보내므로 LLM 실행 시간을 인위적으로 늘리지 않습니다.
    """

    if not engine_event.agent_id or engine_event.phase not in {"start", "progress"}:
        return

    minimum = max(0.0, float(os.getenv("AGENT_PROGRESS_LOG_MIN_SECONDS", "0.8")))
    maximum = max(minimum, float(os.getenv("AGENT_PROGRESS_LOG_MAX_SECONDS", "2.0")))
    if maximum > 0:
        await asyncio.sleep(random.uniform(minimum, maximum))
