import asyncio

from app.services import msds
from app.services.msds import KoshaLookupOutcome, MsdsLookupResult, MsdsSummary


def test_msds_material_names_preserve_user_keyin_without_alias_normalization():
    assert msds.material_names("Ammonia, Ammonia Water, Aqueous Ammonia") == [
        "Ammonia",
        "Ammonia Water",
        "Aqueous Ammonia",
    ]
    assert msds.LOCAL_MSDS["ammonia water"].material == "Ammonia Water"


def test_kosha_parser_selects_exact_material_and_extracts_detail():
    search_html = """
        <a href="javascript:getDetail('msds','999999');">Hydrogen peroxide</a>
        <a href="javascript:getDetail('msds','000557');">HYDROGEN</a>
    """
    detail_html = """
        <dd>인화성 가스 : 구분1</dd>
        <dd>H220 : 극인화성 가스</dd>
        <dd>P210 : 열, 고온의 표면 및 점화원으로부터 멀리하시오.</dd>
    """

    assert msds._first_kosha_result(search_html, "Hydrogen") == ("000557", "HYDROGEN")
    assert "H220 : 극인화성 가스" in msds._extract_kosha_hazards(detail_html)
    assert any(value.startswith("P210") for value in msds._extract_kosha_handling(detail_html))


def test_msds_hazard_classification_keeps_explainable_signals():
    classified = msds.classify_msds_hazard(
        MsdsSummary(
            material="HYDROGEN",
            hazards=["H220 : 극인화성 가스"],
            handling=["P210 : 점화원으로부터 멀리하시오"],
            source="KOSHA MSDS 검색 chem_id=000557",
        )
    )

    assert classified.is_high_hazard
    assert "고위험 H문구: H220" in classified.hazard_signals
    assert "화재/폭발" in classified.hazard_signals


def test_kosha_parser_rejects_short_material_false_positive():
    search_html = """<a href="javascript:getDetail('msds','123456');">HfSi2</a>"""

    assert msds._first_kosha_result(search_html, "HF") == (None, None)


def test_lookup_trace_explains_connection_failure(monkeypatch):
    async def failed_lookup(_material: str) -> KoshaLookupOutcome:
        return KoshaLookupOutcome(None, "KOSHA 사이트 연결 또는 응답 처리에 실패했습니다. 오류 종류: ConnectError")

    monkeypatch.setattr(msds, "_fetch_kosha_msds_summary_with_reason", failed_lookup)
    result = asyncio.run(msds.fetch_msds_summary_with_trace("Hydrogen"))

    assert result.summary.source == "PoC 내장 MSDS 요약"
    assert "ConnectError" in result.steps[1].detail


def test_lookup_trace_reports_kosha_success(monkeypatch):
    summary = MsdsSummary(
        material="HYDROGEN",
        hazards=["H220 : 극인화성 가스"],
        handling=["P210 : 점화원으로부터 멀리하시오"],
        source="KOSHA MSDS 검색 chem_id=000557",
    )

    async def successful_lookup(_material: str) -> KoshaLookupOutcome:
        return KoshaLookupOutcome(summary, "KOSHA에서 상세정보를 확인했습니다.")

    monkeypatch.setattr(msds, "_fetch_kosha_msds_summary_with_reason", successful_lookup)
    result = asyncio.run(msds.fetch_msds_summary_with_trace("Hydrogen"))

    assert result.summary.source.startswith("KOSHA MSDS 검색")
    assert result.summary.is_high_hazard
    assert "고위험 H문구: H220" in result.summary.hazard_signals
    assert "검색 결과를 찾았습니다" in result.steps[-1].title


def test_agent_msds_tool_returns_explicit_lookup_contract(monkeypatch):
    import app.hazop_engine.tools.msds_tools as msds_tools

    async def fake_lookup(_material: str) -> MsdsLookupResult:
        return MsdsLookupResult(
            summary=MsdsSummary(
                material="Silane",
                hazards=["공기 중 자연발화 가능"],
                handling=["누출 시 긴급차단 및 대피"],
                source="PoC 내장 MSDS 요약",
                is_high_hazard=True,
                hazard_signals=["화재/폭발"],
            ),
            steps=[],
        )

    monkeypatch.setattr(msds_tools, "fetch_msds_summary_with_trace", fake_lookup)

    result = msds_tools.lookup_msds_detail(
        "Silane",
        cas_number="7803-62-5",
        requested_sections=["hazards", "leak_fire_emergency"],
    )

    assert result["cas_number"] == "7803-62-5"
    assert result["requested_sections"] == ["hazards", "leak_fire_emergency"]
    assert result["lookup_succeeded"]
    assert result["fallback_used"]
    assert result["source"] == "PoC 내장 MSDS 요약"
    assert result["is_high_hazard"]
    assert result["hazard_signals"] == ["화재/폭발"]
