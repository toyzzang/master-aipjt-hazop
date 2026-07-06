from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass

import httpx


@dataclass
class MsdsSummary:
    """MSDS 조회 결과를 Agent가 쓰기 쉬운 짧은 형태로 정리한 값입니다."""

    material: str
    hazards: list[str]
    handling: list[str]
    source: str


@dataclass
class MsdsLookupStep:
    """MSDS 조회 중 실제로 수행한 한 단계를 화면 로그로 보여주기 위한 값입니다."""

    title: str
    detail: str


@dataclass
class MsdsLookupResult:
    """MSDS 최종 요약과 조회 과정을 함께 담습니다."""

    summary: MsdsSummary
    steps: list[MsdsLookupStep]


LOCAL_MSDS = {
    "di water": MsdsSummary(
        material="DI Water",
        hazards=["일반적으로 인화성/독성 위험은 낮음", "누수 시 미끄럼, 설비 공급 중단, 전기설비 접촉 위험은 검토 필요"],
        handling=["누수 즉시 배수/청소", "전기설비 주변 누수 여부 점검", "저액위/유량 알람 확인"],
        source="PoC 내장 MSDS 요약",
    ),
    "silane": MsdsSummary(
        material="Silane",
        hazards=["공기 중 자연발화 가능", "가연성/폭발성 분위기 형성 가능", "누출 시 작업자 대피 및 긴급 차단 필요"],
        handling=["Gas Detector", "긴급차단밸브", "국소배기 및 Purge", "누설 점검 절차"],
        source="PoC 내장 MSDS 요약",
    ),
    "hydrogen": MsdsSummary(
        material="Hydrogen",
        hazards=["고인화성 가스", "누출 시 폭발성 분위기 형성 가능", "점화원 관리 필요"],
        handling=["Gas Detector", "환기", "압력 관리", "누설 점검"],
        source="PoC 내장 MSDS 요약",
    ),
    "nitrogen": MsdsSummary(
        material="Nitrogen",
        hazards=["불활성 가스", "밀폐공간 산소결핍 위험", "고압가스 취급 위험"],
        handling=["산소농도 관리", "환기", "압력조절밸브 점검", "Purge 절차 확인"],
        source="PoC 내장 MSDS 요약",
    ),
    "hf": MsdsSummary(
        material="HF",
        hazards=["급성 독성 및 부식성", "피부 접촉 시 중대한 화학화상 가능", "흡입 노출 위험"],
        handling=["국소배기", "보호구", "누출 대응 키트", "비상샤워/세안설비"],
        source="PoC 내장 MSDS 요약",
    ),
}


async def fetch_msds_summary(material: str) -> MsdsSummary:
    """물질명을 기준으로 MSDS 정보를 조회합니다.

    PoC 설계:
    - 1순위로 KOSHA 안전보건공단 MSDS 사이트에서 물질명을 검색합니다.
    - KOSHA 검색이 실패하면 내장 요약을 사용합니다.
    - Bing 일반 웹 검색 fallback은 현재 PoC 요청에 따라 임시 제외했습니다.
    - 이렇게 하면 개발자는 검색 API 키 없이도 "외부 MSDS 사이트 조회" 흐름을 볼 수 있습니다.
    """

    result = await fetch_msds_summary_with_trace(material)
    return result.summary


async def fetch_msds_summary_with_trace(material: str) -> MsdsLookupResult:
    """MSDS 조회 결과와 조회 과정을 함께 반환합니다.

    화면에는 이 trace를 이용해서 "KOSHA를 먼저 봤는지", "왜 fallback 했는지"를
    Agent가 실제 수행한 작업처럼 단계별로 보여줍니다.
    """

    steps: list[MsdsLookupStep] = []
    normalized = material.strip().lower()
    local = LOCAL_MSDS.get(normalized)

    steps.append(
        MsdsLookupStep(
            title="KOSHA MSDS 검색을 시도합니다.",
            detail=f"물질명 '{material}'을 KOSHA 안전보건공단 MSDS 검색 조건(물질명)으로 조회합니다.",
        )
    )

    kosha_summary = await _fetch_kosha_msds_summary(material)
    if kosha_summary:
        steps.append(
            MsdsLookupStep(
                title="KOSHA MSDS 검색 결과를 찾았습니다.",
                detail=f"{kosha_summary.material} 항목을 선택했습니다. 출처: {kosha_summary.source}",
            )
        )
        return MsdsLookupResult(summary=kosha_summary, steps=steps)

    steps.append(
        MsdsLookupStep(
            title="KOSHA MSDS에서 확정 가능한 결과를 찾지 못했습니다.",
            detail="검색 결과가 없거나, HF처럼 짧은 물질명이 다른 물질로 오매칭될 위험이 있어 KOSHA 결과를 사용하지 않습니다.",
        )
    )

    # Bing 일반 웹 검색 fallback은 현재 PoC 요청에 따라 임시 제외합니다.
    # 나중에 다시 사용할 때는 `BING_SEARCH_API_KEY`/`BING_SEARCH_ENDPOINT` 기반
    # 보완 조회 코드를 이 위치에 복구하면 됩니다.
    summary = local or _unknown_summary(material, "PoC 내장 요약 없음")
    steps.append(
        MsdsLookupStep(
            title="PoC 내장 MSDS 요약을 사용합니다.",
            detail=f"{summary.material}에 대해 내장된 참고 요약을 사용합니다. 출처: {summary.source}",
        )
    )
    return MsdsLookupResult(summary=summary, steps=steps)


def material_names(materials: str, node_materials: str = "") -> list[str]:
    """사용자가 입력한 물질 문자열에서 물질명 후보를 뽑습니다."""

    raw = f"{materials},{node_materials}"
    tokens = []
    for chunk in raw.replace("/", ",").replace("\n", ",").split(","):
        value = chunk.strip()
        if not value:
            continue
        if ":" in value:
            value = value.split(":", 1)[1].strip()
        value = _canonical_material_name(value)
        if value and value not in tokens:
            tokens.append(value)
    return tokens


async def _fetch_kosha_msds_summary(material: str) -> MsdsSummary | None:
    """KOSHA MSDS 사이트에서 물질명을 검색하고 첫 번째 유사 결과의 상세정보를 요약합니다.

    이것은 구글처럼 인터넷 전체를 뒤지는 "일반 웹 검색"은 아닙니다.
    대신 KOSHA라는 특정 MSDS 사이트 안에서 검색하는 "사이트 내부 검색 + 크롤링"입니다.
    HAZOP 관점에서는 일반 웹 검색보다 출처가 명확해서 더 좋은 방식입니다.
    """

    base_url = os.getenv("KOSHA_MSDS_BASE_URL", "https://msds.kosha.or.kr")
    search_url = f"{base_url}/MSDSInfo/kcic/msdssearchMsds.do"
    detail_url = f"{base_url}/MSDSInfo/kcic/msdsdetail.do"

    try:
        # KOSHA 사이트는 실행 환경에 따라 Python 인증서 검증에서
        # self-signed certificate chain 오류가 날 수 있습니다.
        # PoC에서는 외부 MSDS 조회 흐름을 보여주는 것이 목적이라 KOSHA 호출에 한해
        # 검증을 끕니다. 운영 적용 시에는 사내 신뢰 CA 또는 인증서 번들을 설정해야 합니다.
        async with httpx.AsyncClient(timeout=12, follow_redirects=True, verify=False) as client:
            search_response = await client.post(
                search_url,
                data={
                    "viewType": "",
                    "listType": "msds",
                    "pageIndex": "1",
                    "chem_id": "",
                    "pageSize": "10",
                    "searchCondition": "chem_name",
                    "searchKeyword": material,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            search_response.raise_for_status()
            chem_id, chem_name = _first_kosha_result(search_response.text, material)
            if not chem_id:
                return None

            detail_response = await client.post(
                detail_url,
                data={
                    "viewType": "msds",
                    "listType": "msds",
                    "pageIndex": "1",
                    "chem_id": chem_id,
                    "pageSize": "10",
                    "searchCondition": "chem_name",
                    "searchKeyword": material,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            detail_response.raise_for_status()
    except Exception:
        return None

    hazards = _extract_kosha_hazards(detail_response.text)
    handling = _extract_kosha_handling(detail_response.text)
    if not hazards and not handling:
        return None

    return MsdsSummary(
        material=chem_name or material,
        hazards=hazards or ["KOSHA 상세 페이지에서 유해성 문구를 찾지 못해 담당자 확인 필요"],
        handling=handling or ["KOSHA 상세 페이지에서 취급/누출 대응 문구를 찾지 못해 담당자 확인 필요"],
        source=f"KOSHA MSDS 검색 chem_id={chem_id}",
    )


def _first_kosha_result(page_html: str, material: str) -> tuple[str | None, str | None]:
    """KOSHA 검색 결과 목록에서 가장 그럴듯한 첫 번째 상세 ID를 찾습니다."""

    matches = re.findall(r"getDetail\('msds','([^']+)'\).*?>([^<]+)</a>", page_html, flags=re.DOTALL)
    if not matches:
        return None, None

    normalized = material.strip().lower()
    exact_matches = [(chem_id, name) for chem_id, name in matches if html.unescape(name).strip().lower() == normalized]
    if len(normalized) <= 3 and not exact_matches:
        # HF처럼 짧은 검색어는 KOSHA에서 HfSi2 같은 다른 물질이 먼저 잡힐 수 있습니다.
        # 짧은 물질명은 정확히 같은 이름이 없으면 잘못된 근거를 쓰지 않고 fallback합니다.
        return None, None
    chem_id, name = exact_matches[0] if exact_matches else matches[0]
    return chem_id, _clean_text(name)


def _canonical_material_name(value: str) -> str:
    """Node별 물질 설명에서 대표 물질명만 최대한 보수적으로 추출합니다.

    예를 들어 `HF byproduct`는 KOSHA 검색어로 그대로 쓰면 엉뚱한 결과가 나올 수 있으므로
    대표 물질인 `HF`로 정규화합니다.
    """

    lowered = value.strip().lower()
    if re.search(r"\bhf\b", lowered):
        return "HF"
    if "silane" in lowered:
        return "Silane"
    if "hydrogen" in lowered:
        return "Hydrogen"
    if "nitrogen" in lowered or "n2" in lowered:
        return "Nitrogen"
    if "di water" in lowered or "diw" in lowered:
        return "DI Water"
    return value.strip()


def _extract_kosha_hazards(page_html: str) -> list[str]:
    """상세 MSDS에서 H문구와 유해성 분류를 우선 추출합니다."""

    text = _html_to_text(page_html)
    patterns = [
        r"H\d{3}\s*:\s*[^P\n\r]+",
        r"인화성 가스\s*:\s*구분\d+",
        r"고압가스\s*:\s*[^가-힣A-Za-z0-9\n\r]*[^\n\r]+",
        r"급성 독성\([^)]*\)\s*:\s*구분\d+",
        r"공기 중에서 자연점화함",
        r"공기와 폭발성 혼합물을 형성함",
    ]
    return _unique_matches(text, patterns, limit=8)


def _extract_kosha_handling(page_html: str) -> list[str]:
    """상세 MSDS에서 취급, 저장, 누출 대응에 쓸 수 있는 P문구/대응 문구를 추출합니다."""

    text = _html_to_text(page_html)
    patterns = [
        r"P\d{3}(?:\+P\d{3})?\s*:\s*[^\n\r]+",
        r"누출 시 모든 점화원을 제거하시오",
        r"옥외 또는 환기가 잘 되는 곳에서만 취급하시오",
        r"환기가 잘 되는 곳에 보관하시오",
        r"가스 누출 화재;[^\n\r]+",
        r"위험하지 않다면 누출을 멈추시오",
    ]
    return _unique_matches(text, patterns, limit=10)


def _html_to_text(page_html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", page_html, flags=re.IGNORECASE)
    text = re.sub(r"</(?:dd|dt|li|p|tr|h\d)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"[ \t]+", " ", text)


def _unique_matches(text: str, patterns: list[str], limit: int) -> list[str]:
    values: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            cleaned = _clean_text(match)
            if cleaned and cleaned not in values:
                values.append(cleaned)
            if len(values) >= limit:
                return values
    return values


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _unknown_summary(material: str, source: str) -> MsdsSummary:
    return MsdsSummary(
        material=material,
        hazards=["MSDS 상세 위험성 확인 필요"],
        handling=["취급/보관/누출 대응 기준 확인 필요"],
        source=source,
    )
