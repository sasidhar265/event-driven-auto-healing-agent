"""Read operations for tenant knowledge items."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeItem, RemediationReference


async def list_knowledge(
    session: AsyncSession, tenant_id: str, limit: int
) -> list[KnowledgeItem]:
    """Return a tenant's newest knowledge items."""
    return list(
        (
            await session.scalars(
                select(KnowledgeItem)
                .where(KnowledgeItem.tenant_id == tenant_id)
                .order_by(KnowledgeItem.created_at.desc())
                .limit(limit)
            )
        ).all()
    )


async def scan_knowledge(
    session: AsyncSession, tenant_id: str, limit: int
) -> list[KnowledgeItem]:
    """Return bounded tenant knowledge candidates for relevance ranking."""
    return list(
        (
            await session.scalars(
                select(KnowledgeItem)
                .where(KnowledgeItem.tenant_id == tenant_id)
                .limit(limit)
            )
        ).all()
    )


async def scan_active_references(
    session: AsyncSession, tenant_id: str, limit: int
) -> list[RemediationReference]:
    """Return bounded active remediation references for relevance ranking."""
    return list(
        (
            await session.scalars(
                select(RemediationReference)
                .where(
                    RemediationReference.tenant_id == tenant_id,
                    RemediationReference.active.is_(True),
                )
                .order_by(RemediationReference.created_at.desc())
                .limit(limit)
            )
        ).all()
    )
