import asyncio

from app.services import msds
from app.services.msds import KoshaLookupOutcome, MsdsSummary


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
    assert "검색 결과를 찾았습니다" in result.steps[-1].title
