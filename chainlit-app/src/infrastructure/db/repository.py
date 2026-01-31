# src/infrastructure/db/repository.py
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import LangGraphState


class GraphStateRepository:

    async def get(
        self, session: AsyncSession, thread_id: str
    ) -> Optional[LangGraphState]:
        return await session.get(LangGraphState, thread_id)

    async def upsert(
        self,
        session: AsyncSession,
        *,
        thread_id: str,
        workflow: str,
        state: Dict[str, Any],
    ) -> None:
        stmt = (
            insert(LangGraphState)
            .values(thread_id=thread_id, workflow=workflow, state=state)
            .on_conflict_do_update(
                index_elements=["thread_id"],
                set_=dict(workflow=workflow, state=state),
            )
        )
        await session.execute(stmt)
        await session.commit()
