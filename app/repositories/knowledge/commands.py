"""Write operations for tenant knowledge items."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeItem
from app.schemas import KnowledgeCreate


async def create_knowledge(
    session: AsyncSession, tenant_id: str, body: KnowledgeCreate
) -> KnowledgeItem:
    """Create and commit a knowledge item, mapping API metadata to the model."""
    data = body.model_dump()
    metadata = data.pop("metadata")
    item = KnowledgeItem(tenant_id=tenant_id, metadata_=metadata, **data)
    session.add(item)
    await session.commit()
    return item
