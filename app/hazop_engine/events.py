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
    emphasis: bool = False,
    parent_kind: str | None = None,
    parent_event_key: str | None = None,
    event_key: str | None = None,
) -> EngineEvent:
    """화면에 보여줄 HAZOP Engine 진행 이벤트를 만듭니다."""

    return EngineEvent(
        title=title,
        detail=detail,
        kind=kind,
        agent_id=agent_id,
        phase=phase,
        loading=loading,
        emphasis=emphasis,
        parent_kind=parent_kind,
        parent_event_key=parent_event_key,
        event_key=event_key,
    )
