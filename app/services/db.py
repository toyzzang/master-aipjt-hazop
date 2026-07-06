from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.schemas.hazop import HazopInput


def _database_url() -> str:
    """DB 접속 주소를 결정합니다.

    Docker Compose에서는 Postgres URL을 환경 변수로 넣습니다.
    로컬에서 그냥 실행할 때는 별도 DB 없이도 볼 수 있게 SQLite 파일을 fallback으로 씁니다.
    """

    return os.getenv("DATABASE_URL", "sqlite:///./data/hazop_poc.db")


class Base(DeclarativeBase):
    pass


class HazopJob(Base):
    """AI 초안 생성 요청 1건을 저장하는 테이블입니다."""

    __tablename__ = "hazop_jobs"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    maker: Mapped[str] = mapped_column(String(200))
    model: Mapped[str] = mapped_column(String(200))
    materials: Mapped[str] = mapped_column(Text)
    node_materials: Mapped[str] = mapped_column(Text, default="")
    standard_hazop_link: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    upload_filename: Mapped[str] = mapped_column(String(500))
    upload_path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="UPLOADED")
    result_request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    output_excel_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class HazopAgentEvent(Base):
    """화면에 보여준 Agent 실시간 로그를 저장하는 테이블입니다."""

    __tablename__ = "hazop_agent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("hazop_jobs.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class HazopResultMeta(Base):
    """생성 결과 파일 위치와 건수를 저장하는 테이블입니다.

    실제 #3/#4 전체 JSON은 파일로 저장하고, DB에는 조회와 추적에 필요한 메타정보만 둡니다.
    이 방식은 PoC에서 결과 컬럼이 자주 바뀌어도 DB 마이그레이션 부담이 작습니다.
    """

    __tablename__ = "hazop_result_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("hazop_jobs.id"), index=True)
    result_json_path: Mapped[str] = mapped_column(Text)
    output_excel_path: Mapped[str] = mapped_column(Text)
    risk_count: Mapped[int] = mapped_column(Integer)
    action_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


engine = create_engine(_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """앱 시작 시 테이블이 없으면 생성합니다."""

    Base.metadata.create_all(bind=engine)


def create_job_record(job_id: str, input_data: HazopInput, upload_filename: str, upload_path: Path) -> None:
    with SessionLocal() as session:
        session.add(
            HazopJob(
                id=job_id,
                maker=input_data.maker,
                model=input_data.model,
                materials=input_data.materials,
                node_materials=input_data.node_materials,
                standard_hazop_link=input_data.standard_hazop_link,
                notes=input_data.notes,
                upload_filename=upload_filename,
                upload_path=str(upload_path),
            )
        )
        session.commit()


def update_job_status(
    job_id: str,
    status: str,
    result_request_id: str | None = None,
    output_excel_path: str | None = None,
) -> None:
    with SessionLocal() as session:
        job = session.get(HazopJob, job_id)
        if not job:
            return
        job.status = status
        job.updated_at = datetime.now(UTC)
        if result_request_id:
            job.result_request_id = result_request_id
        if output_excel_path:
            job.output_excel_path = output_excel_path
        session.commit()


def save_agent_event(job_id: str, event_type: str, payload: dict[str, Any]) -> None:
    with SessionLocal() as session:
        session.add(
            HazopAgentEvent(
                job_id=job_id,
                event_type=event_type,
                title=str(payload.get("title", "")),
                detail=str(payload.get("detail", payload.get("message", ""))),
                payload_json=json.dumps(payload, ensure_ascii=False),
            )
        )
        session.commit()


def save_result_meta(
    job_id: str,
    result_json_path: Path,
    output_excel_path: Path,
    risk_count: int,
    action_count: int,
) -> None:
    with SessionLocal() as session:
        session.add(
            HazopResultMeta(
                job_id=job_id,
                result_json_path=str(result_json_path),
                output_excel_path=str(output_excel_path),
                risk_count=risk_count,
                action_count=action_count,
            )
        )
        session.commit()


def recent_jobs(limit: int = 20) -> list[dict[str, Any]]:
    """테스트와 화면 확인용으로 최근 요청 목록을 반환합니다."""

    with SessionLocal() as session:
        rows = session.query(HazopJob).order_by(HazopJob.created_at.desc()).limit(limit).all()
        return [
            {
                "id": row.id,
                "maker": row.maker,
                "model": row.model,
                "status": row.status,
                "output_excel_path": row.output_excel_path,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
