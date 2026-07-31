"""Shared router for governed ART lifecycle endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/v1/art", tags=["ART lifecycle"])
