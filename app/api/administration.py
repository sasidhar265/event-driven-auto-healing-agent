"""Internal governance-policy and knowledge administration endpoints."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import api_settings, internal_router
from app.db import get_session
from app.repositories.governance import commands as governance_commands
from app.repositories.governance import queries as governance_queries
from app.repositories.knowledge import commands as knowledge_commands
from app.repositories.knowledge import queries as knowledge_queries
from app.schemas import KnowledgeCreate, PolicyCreate
from app.security import Principal, principal

@internal_router.post("/policies", status_code=201)
async def create_policy(body: PolicyCreate, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    """Create a tenant governance policy through the internal API."""
    policy = await governance_commands.create_policy(session, auth.tenant_id, body)
    return {"id": policy.id, "version": policy.version}


@internal_router.get("/policies")
async def list_policies(
    auth: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    """List the tenant's governance policies, newest first."""
    rows = await governance_queries.list_policies(
        session, auth.tenant_id, api_settings.api_admin_limit
    )
    return [
        {
            "id": row.id, "name": row.name, "rules": row.rules,
            "active": row.active, "version": row.version, "created_at": row.created_at,
        }
        for row in rows
    ]


@internal_router.post("/knowledge", status_code=201)
async def create_knowledge(body: KnowledgeCreate, auth: Principal = Depends(principal), session: AsyncSession = Depends(get_session)):
    """Create a tenant knowledge item used during evidence retrieval."""
    item = await knowledge_commands.create_knowledge(session, auth.tenant_id, body)
    return {"id": item.id}


@internal_router.get("/knowledge")
async def list_knowledge(
    auth: Principal = Depends(principal),
    session: AsyncSession = Depends(get_session),
):
    """List knowledge items available to the authenticated tenant."""
    rows = await knowledge_queries.list_knowledge(
        session, auth.tenant_id, api_settings.api_admin_limit
    )
    return [
        {
            "id": row.id, "title": row.title, "content": row.content,
            "tags": row.tags, "metadata": row.metadata_, "created_at": row.created_at,
        }
        for row in rows
    ]
