"""Outbox state changes staged in the worker transaction."""

from datetime import UTC, datetime

from app.models import Outbox


def mark_published(item: Outbox) -> None:
    """Mark one processed outbox item as published at the current UTC time."""
    item.published_at = datetime.now(UTC)
