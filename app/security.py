from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from app.config import get_settings


@dataclass(frozen=True)
class Principal:
    """Authenticated tenant and actor identity propagated through a request."""
    tenant_id: str
    actor: str


async def principal(
    x_api_key: str = Header(), x_tenant_id: str = Header(), x_actor: str = Header(default="api")
) -> Principal:
    """Validate API headers and construct the tenant-scoped request principal."""
    if x_api_key != get_settings().api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return Principal(tenant_id=x_tenant_id, actor=x_actor)
