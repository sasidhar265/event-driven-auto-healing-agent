"""Shared FastAPI routers and limits used by domain endpoint modules."""

from fastapi import APIRouter

from app.config import get_settings

operations_router = APIRouter(prefix="/v1")
integration_router = APIRouter(prefix="/v1")
internal_router = APIRouter(prefix="/v1/internal", tags=["Internal services"])
api_settings = get_settings()
