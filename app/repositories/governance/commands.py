"""Write operations for tenant governance policies."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Policy
from app.schemas import PolicyCreate


async def create_policy(
    session: AsyncSession, tenant_id: str, body: PolicyCreate
) -> Policy:
    """Create and commit one tenant governance policy."""
    policy = Policy(tenant_id=tenant_id, **body.model_dump())
    session.add(policy)
    await session.commit()
    return policy
