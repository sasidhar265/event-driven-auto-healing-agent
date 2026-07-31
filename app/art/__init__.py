"""Governed ART lifecycle API composed from domain route modules."""

from app.art import analysis as _analysis  # noqa: F401
from app.art import events as _events  # noqa: F401
from app.art import execution as _execution  # noqa: F401
from app.art import failures as _failures  # noqa: F401
from app.art import reads as _reads  # noqa: F401
from app.art.router import router

# ART_Feedback.docx defines these four resource-oriented public APIs. The
# granular routes are retained for workers and backwards compatibility, but
# are deliberately omitted from Swagger/API Explorer. Their data is returned
# by the four aggregate GET APIs instead.
PUBLIC_ART_PATHS = {
    "/v1/art/failure-events",
    "/v1/art/agent-runs",
    "/v1/art/impact-assessments",
    "/v1/art/execution-intents",
}
for route in router.routes:
    route.include_in_schema = route.path in PUBLIC_ART_PATHS

__all__ = ["router"]
