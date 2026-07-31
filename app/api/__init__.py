"""HTTP API package composed from responsibility-based route modules."""

from app.api.routers import integration_router, internal_router, operations_router

# Import route modules for their router-registration side effects.
from app.api import administration as _administration
from app.api import audit as _audit
from app.api import events as _events
from app.api import integrations as _integrations
from app.api import overview as _overview
from app.api import suggestions as _suggestions

router = operations_router

__all__ = ["integration_router", "internal_router", "operations_router", "router"]
