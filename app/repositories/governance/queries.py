"""Read operations for tenant governance policies."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Policy


async def list_policies(
    session: AsyncSession, tenant_id: str, limit: int
) -> list[Policy]:
    """Return a tenant's newest governance policies."""
    return list(
        (
            await session.scalars(
                select(Policy)
                .where(Policy.tenant_id == tenant_id)
                .order_by(Policy.created_at.desc())
                .limit(limit)
            )
        ).all()
    )


async def list_active_policies(
    session: AsyncSession, tenant_id: str
) -> list[Policy]:
    """Return active tenant policies for runtime governance evaluation."""
    return list(
        (
            await session.scalars(
                select(Policy).where(
                    Policy.tenant_id == tenant_id,
                    Policy.active.is_(True),
                )
            )
        ).all()
    )
