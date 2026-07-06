from __future__ import annotations

import json
import shutil
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.schemas.hazop import HazopInput
from app.services.agent import AgentRunEvent, run_hazop_agent
from app.services.db import (
    create_job_record,
    init_db,
    recent_jobs,
    save_agent_event,
    save_result_meta,
    update_job_status,
)
from app.services.excel import read_nodes_from_excel


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
REQUEST_DIR = DATA_DIR / "requests"
STATIC_DIR = BASE_DIR / "app" / "static"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
REQUEST_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="HAZOP AI Agent PoC")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def startup() -> None:
    """앱 시작 시 DB 테이블을 준비합니다."""

    init_db()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """브라우저에서 바로 볼 수 있는 PoC 화면을 반환합니다."""

    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.post("/api/jobs")
async def create_job(
    file: UploadFile = File(...),
    maker: str = Form(...),
    model: str = Form(...),
    materials: str = Form(...),
    node_materials: str = Form(""),
    standard_hazop_link: str = Form(""),
    notes: str = Form(""),
) -> dict:
    """업로드 파일과 입력값을 임시 작업으로 저장합니다.

    SSE(EventSource)는 GET 요청만 쉽게 지원하므로, 먼저 POST로 파일을 올리고
    반환된 job_id를 사용해 `/api/jobs/{job_id}/events`에 연결합니다.
    """

    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="xlsx 파일만 업로드할 수 있습니다.")

    job_id = Path(file.filename).stem.replace(" ", "_")
    job_id = f"{job_id}_{len(list(UPLOAD_DIR.glob('*'))):04d}"
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    excel_path = job_dir / file.filename
    with excel_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    input_data = HazopInput(
        maker=maker,
        model=model,
        materials=materials,
        node_materials=node_materials,
        standard_hazop_link=standard_hazop_link,
        notes=notes,
    )
    (job_dir / "input.json").write_text(input_data.model_dump_json(indent=2), encoding="utf-8")
    (job_dir / "excel_path.txt").write_text(str(excel_path), encoding="utf-8")
    create_job_record(job_id, input_data, file.filename, excel_path)

    return {"job_id": job_id}


@app.post("/api/excel/nodes")
async def preview_excel_nodes(file: UploadFile = File(...)) -> dict:
    """업로드 Excel의 `#1 노드리스트`를 읽어 화면에 미리 보여줍니다.

    쉽게 말하면, 사용자가 Excel 파일을 고르면 그 안의 Node 이름을 꺼내서
    Node별 물질정보 입력칸을 자동으로 만들 수 있게 해주는 API입니다.
    """

    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="xlsx 파일만 업로드할 수 있습니다.")

    try:
        nodes = read_nodes_from_excel(file.file)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "nodes": [
            {"node_order": node.node_order, "node_name": node.node_name}
            for node in nodes
        ]
    }


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    """Agent 실행 로그를 실시간으로 흘려보냅니다."""

    job_dir = UPLOAD_DIR / job_id
    input_path = job_dir / "input.json"
    excel_path_file = job_dir / "excel_path.txt"
    if not input_path.exists() or not excel_path_file.exists():
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")

    input_data = HazopInput.model_validate_json(input_path.read_text(encoding="utf-8"))
    excel_path = Path(excel_path_file.read_text(encoding="utf-8"))

    async def stream():
        try:
            update_job_status(job_id, "RUNNING")
            async for event in run_hazop_agent(input_data, excel_path, REQUEST_DIR):
                save_agent_event(job_id, event.event, event.data)
                if event.event == "done":
                    update_job_status(
                        job_id,
                        "DONE",
                        result_request_id=event.data.get("request_id"),
                        output_excel_path=event.data.get("output_excel"),
                    )
                    result_path = REQUEST_DIR / event.data["request_id"] / "result.json"
                    save_result_meta(
                        job_id=job_id,
                        result_json_path=result_path,
                        output_excel_path=Path(event.data["output_excel"]),
                        risk_count=len(event.data.get("risk_rows", [])),
                        action_count=len(event.data.get("action_rows", [])),
                    )
                yield event.to_sse()
        except Exception as exc:
            update_job_status(job_id, "FAILED")
            save_agent_event(job_id, "error", {"message": str(exc)})
            yield AgentRunEvent("error", {"message": str(exc)}).to_sse()

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/download")
def download(path: str) -> FileResponse:
    """생성된 결과 Excel을 다운로드합니다.

    보안을 위해 `data/requests` 아래 파일만 내려줍니다.
    """

    target = Path(path).resolve()
    allowed_root = REQUEST_DIR.resolve()
    if allowed_root not in target.parents:
        raise HTTPException(status_code=400, detail="다운로드할 수 없는 경로입니다.")
    if not target.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return FileResponse(target, filename=target.name)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/jobs")
def list_jobs() -> dict:
    """최근 작업 목록을 확인합니다."""

    return {"jobs": recent_jobs()}
