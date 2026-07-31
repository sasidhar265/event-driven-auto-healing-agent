"""Governed ART lifecycle API composed from domain route modules."""

from app.art import analysis as _analysis  # noqa: F401
from app.art import events as _events  # noqa: F401
from app.art import execution as _execution  # noqa: F401
from app.art import failures as _failures  # noqa: F401
from app.art import reads as _reads  # noqa: F401
from app.art.router import router

__all__ = ["router"]
