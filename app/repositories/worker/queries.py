"""Outbox locking queries for worker iterations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Outbox


async def lock_pending_outbox(
    session: AsyncSession, batch_size: int
) -> list[Outbox]:
    """Lock the next available unpublished outbox batch with SKIP LOCKED."""
    return list(
        (
            await session.scalars(
                select(Outbox)
                .where(Outbox.published_at.is_(None))
                .order_by(Outbox.available_at)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
