from __future__ import annotations

from app.hazop_engine.context import EngineEvent


def engine_event(
    title: str,
    detail: str,
    kind: str = "agent",
    *,
    agent_id: str | None = None,
    phase: str | None = None,
    loading: bool = False,
) -> EngineEvent:
    """화면에 보여줄 HAZOP Engine 진행 이벤트를 만듭니다."""

    return EngineEvent(
        title=title,
        detail=detail,
        kind=kind,
        agent_id=agent_id,
        phase=phase,
        loading=loading,
    )
