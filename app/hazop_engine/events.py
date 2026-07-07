from __future__ import annotations

from app.hazop_engine.context import EngineEvent


def engine_event(title: str, detail: str) -> EngineEvent:
    """화면에 보여줄 HAZOP Engine 진행 이벤트를 만듭니다."""

    return EngineEvent(title=title, detail=detail)
