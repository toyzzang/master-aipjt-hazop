from __future__ import annotations

import asyncio
import io
import re
import sys
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.schemas.hazop import HazopInput, HazopResult
from app.services.agent import run_hazop_agent
from app.services.excel import read_nodes_from_excel


load_dotenv()

DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
REQUEST_DIR = DATA_DIR / "requests"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
REQUEST_DIR.mkdir(parents=True, exist_ok=True)


st.set_page_config(page_title="HAZOP AI Agent PoC", layout="wide")

DEFAULT_NODE_MATERIALS = """DI Water 공급 탱크: DI Water
DI Water 이송 펌프: DI Water
Wet 장비 공급 배관: DI Water"""

DEFAULT_STANDARD_HAZOP_LINK = "STD-HAZOP-DIW-UTILITY-2026-001"

DEFAULT_NOTES = """CleanTech CT-DIW-100 신규 도입 PoC 검토용 입력입니다.
DI Water 공급 중단, 유량 저하, 누수 중심으로 초안을 생성합니다."""


def main() -> None:
    _inject_styles()

    st.title("HAZOP AI Agent PoC")
    st.caption("업로드 Excel의 #1 노드리스트와 #2 가이드워드만 기준으로 #3/#4 초안을 생성합니다.")

    input_col, log_col = st.columns([0.9, 1.1], gap="large")

    with input_col:
        st.subheader("입력")
        uploaded_file = st.file_uploader(
            "HAZOP Excel 업로드",
            type=["xlsx"],
            help="샘플 또는 사용자가 작성한 .xlsx 파일을 선택하세요.",
        )
        maker = st.text_input("Maker", value="CleanTech")
        model = st.text_input("Model", value="CT-DIW-100")
        materials = st.text_area("MSDS 기준 물질", value="DI Water", height=80)
        node_materials = _render_node_material_inputs(uploaded_file, materials)
        standard_hazop_link = st.text_input("표준공정위험성평가서 Link/ID", value=DEFAULT_STANDARD_HAZOP_LINK)
        notes = st.text_area("추가 메모", value=DEFAULT_NOTES, height=110)
        submitted = st.button("AI 초안생성", type="primary", use_container_width=True)

    with log_col:
        st.subheader("Agent 로그")
        log_placeholder = st.empty()
        result_placeholder = st.empty()

    if not submitted:
        with log_placeholder.container():
            st.info("왼쪽에서 Excel과 기본정보를 입력한 뒤 AI 초안생성을 누르면 로그가 여기에 표시됩니다.")
        return

    if uploaded_file is None:
        with log_placeholder.container():
            st.error("xlsx 파일을 먼저 업로드해 주세요.")
        return

    input_data = HazopInput(
        maker=maker,
        model=model,
        materials=materials,
        node_materials=node_materials,
        standard_hazop_link=standard_hazop_link,
        notes=notes,
    )
    excel_path = _save_uploaded_excel(uploaded_file)
    logs: list[dict[str, str]] = []

    try:
        result = asyncio.run(_run_agent_for_streamlit(input_data, excel_path, logs, log_placeholder))
    except Exception as exc:
        logs.append({"title": "오류", "detail": str(exc)})
        _render_logs(log_placeholder, logs, active=False)
        return

    _render_logs(log_placeholder, logs, active=False)
    _render_result(result_placeholder, result)


def _render_node_material_inputs(uploaded_file, materials: str) -> str:
    """업로드 Excel의 Node 개수만큼 Streamlit 입력칸을 표시합니다.

    쉽게 말하면 Excel의 `#1 노드리스트`를 보고, Node 이름을 사람이 다시 치지 않도록
    Node별 물질 입력칸을 자동으로 만들어 주는 화면 함수입니다.
    """

    st.markdown("**Node별 물질 정보**")
    if uploaded_file is None:
        st.caption("Excel을 업로드하면 #1 노드리스트 기준으로 Node별 입력칸이 표시됩니다.")
        return st.text_area("Node별 물질 정보 직접 입력", value=DEFAULT_NODE_MATERIALS, height=110)

    try:
        nodes = read_nodes_from_excel(io.BytesIO(uploaded_file.getvalue()))
    except Exception as exc:
        st.warning(f"Node 목록을 읽지 못했습니다: {exc}")
        return st.text_area("Node별 물질 정보 직접 입력", value=DEFAULT_NODE_MATERIALS, height=110)

    st.caption(f"Excel에서 Node {len(nodes)}개를 읽었습니다.")
    default_material = materials.splitlines()[0].strip() if materials.strip() else ""
    lines: list[str] = []
    for node in nodes:
        material = st.text_input(
            f"{node.node_order}. {node.node_name}",
            value=default_material,
            key=f"node_material_{node.node_order}_{_safe_key(node.node_name)}",
        )
        if material.strip():
            lines.append(f"{node.node_name}: {material.strip()}")
    return "\n".join(lines)


async def _run_agent_for_streamlit(
    input_data: HazopInput,
    excel_path: Path,
    logs: list[dict[str, str]],
    log_placeholder,
) -> HazopResult:
    """Agent 이벤트를 Streamlit 화면에 한 줄씩 표시합니다.

    쉽게 말하면 FastAPI의 실시간 로그(SSE) 대신 Streamlit 화면에 직접
    "지금 Agent가 무엇을 하는 중인지"를 차곡차곡 쌓아 보여주는 함수입니다.
    """

    async for event in run_hazop_agent(input_data, excel_path, REQUEST_DIR):
        if event.event == "log":
            logs.append({"title": event.data.get("title", ""), "detail": event.data.get("detail", "")})
            _render_logs(log_placeholder, logs, active=True)
            # Streamlit 화면에서 로그가 한꺼번에 튀지 않고 한 줄씩 보이도록 아주 짧게 쉽니다.
            time.sleep(0.15)
        elif event.event == "error":
            message = event.data.get("message", "Agent 실행 중 오류가 발생했습니다.")
            logs.append({"title": "오류", "detail": message})
            _render_logs(log_placeholder, logs, active=False)
            raise RuntimeError(message)
        elif event.event == "done":
            return HazopResult.model_validate(event.data)

    raise RuntimeError("Agent가 결과를 반환하지 않았습니다.")


def _save_uploaded_excel(uploaded_file) -> Path:
    safe_name = _safe_filename(uploaded_file.name or "hazop.xlsx")
    job_dir = UPLOAD_DIR / f"streamlit_{int(time.time() * 1000)}"
    job_dir.mkdir(parents=True, exist_ok=True)
    target = job_dir / safe_name
    target.write_bytes(uploaded_file.getbuffer())
    return target


def _render_logs(log_placeholder, logs: list[dict[str, str]], active: bool) -> None:
    with log_placeholder.container():
        log_panel = st.container(height=640, border=True)
        with log_panel:
            if not logs:
                st.info("Agent 로그가 여기에 표시됩니다.")
                return

            for index, item in enumerate(logs):
                title = item.get("title", "")
                detail = item.get("detail", "")
                is_active = active and index == len(logs) - 1

                if is_active:
                    with st.spinner(title):
                        st.caption(detail)
                else:
                    st.markdown(f"**● {title}**")
                    st.caption(detail)

                if index < len(logs) - 1:
                    st.divider()


def _render_result(result_placeholder, result: HazopResult) -> None:
    with result_placeholder.container():
        st.subheader("생성 결과")
        st.write(f"#3 위험성평가 {len(result.risk_rows)}건, #4 조치계획서 {len(result.action_rows)}건이 생성되었습니다.")

        if result.output_excel:
            output_path = Path(result.output_excel)
            if output_path.exists():
                st.download_button(
                    "결과 Excel 다운로드",
                    data=output_path.read_bytes(),
                    file_name=output_path.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

        st.markdown("#### #3 위험성평가")
        st.dataframe([row.model_dump() for row in result.risk_rows], use_container_width=True, hide_index=True)

        st.markdown("#### #4 조치계획서")
        if result.action_rows:
            st.dataframe([row.model_dump() for row in result.action_rows], use_container_width=True, hide_index=True)
        else:
            st.info("위험도 9 이상 항목이 없어 별도 조치계획서가 생성되지 않았습니다.")


def _safe_filename(filename: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.가-힣-]+", "_", filename).strip("._")
    return stem or "hazop.xlsx"


def _safe_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9가-힣]+", "_", value).strip("_") or "node"


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --hazop-bg: #f7f4ee;
            --hazop-paper: #fffdf8;
            --hazop-surface: #ffffff;
            --hazop-surface-soft: #fbf8f1;
            --hazop-line: #e4ded2;
            --hazop-line-strong: #d5cabc;
            --hazop-ink: #2f2923;
            --hazop-muted: #756d63;
            --hazop-accent: #2f6f5e;
            --hazop-accent-hover: #26584b;
            --hazop-warning: #fff4d8;
            --hazop-info: #eef6f2;
        }

        .stApp {
            background: var(--hazop-bg);
            color: var(--hazop-ink);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }

        .block-container {
            padding-top: 1.6rem;
            padding-bottom: 2.4rem;
            max-width: 1380px;
        }

        h1, h2, h3, h4, h5, h6 {
            color: var(--hazop-ink);
            font-family: Georgia, "Times New Roman", serif;
            font-weight: 650;
            letter-spacing: 0;
        }

        h1 {
            font-size: 2.35rem;
            margin-bottom: 0.25rem;
        }

        h2, h3 {
            font-size: 1.28rem;
        }

        [data-testid="stMarkdownContainer"] strong {
            color: var(--hazop-ink);
        }

        [data-testid="stCaptionContainer"],
        [data-testid="stMarkdownContainer"] p {
            color: var(--hazop-muted);
        }

        [data-testid="column"] {
            background: var(--hazop-paper);
            border: 1px solid var(--hazop-line);
            border-radius: 8px;
            padding: 1rem 1rem 1.1rem;
            box-shadow: 0 1px 2px rgba(47, 41, 35, 0.04);
        }

        [data-testid="stVerticalBlockBorderWrapper"],
        [data-testid="stForm"],
        [data-testid="stExpander"] {
            background: var(--hazop-surface);
            border-color: var(--hazop-line);
            border-radius: 8px;
            box-shadow: 0 1px 2px rgba(47, 41, 35, 0.05);
        }

        [data-testid="stFileUploader"] section {
            background: var(--hazop-surface-soft);
            border: 1.5px dashed var(--hazop-line-strong);
            border-radius: 8px;
            min-height: 118px;
        }

        [data-testid="stFileUploader"] section:hover {
            background: #fffaf0;
            border-color: var(--hazop-accent);
        }

        [data-testid="stFileUploader"] section * {
            color: var(--hazop-ink);
            pointer-events: auto;
        }

        [data-testid="stFileUploader"] button {
            background: var(--hazop-surface);
            border: 1px solid var(--hazop-line-strong);
            color: var(--hazop-ink);
            border-radius: 6px;
            font-weight: 650;
        }

        [data-testid="stTextInput"] input,
        [data-testid="stTextArea"] textarea {
            background: var(--hazop-surface);
            border: 1px solid var(--hazop-line);
            color: var(--hazop-ink);
            border-radius: 6px;
        }

        [data-testid="stTextInput"] input:focus,
        [data-testid="stTextArea"] textarea:focus {
            border-color: var(--hazop-accent);
            box-shadow: 0 0 0 1px var(--hazop-accent);
        }

        .stButton > button,
        .stDownloadButton > button {
            background: var(--hazop-accent);
            border: 1px solid var(--hazop-accent);
            color: #ffffff;
            font-weight: 700;
            border-radius: 6px;
            min-height: 2.75rem;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            background: var(--hazop-accent-hover);
            border-color: var(--hazop-accent-hover);
            color: #ffffff;
        }

        [data-testid="stAlert"] {
            background: var(--hazop-info);
            border-color: #c8ded5;
            color: var(--hazop-ink);
            border-radius: 8px;
        }

        [data-testid="stDataFrame"] {
            background: var(--hazop-surface);
            border: 1px solid var(--hazop-line);
            border-radius: 8px;
        }

        [data-testid="stSpinner"] {
            color: var(--hazop-accent);
        }

        hr {
            border-color: var(--hazop-line);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
