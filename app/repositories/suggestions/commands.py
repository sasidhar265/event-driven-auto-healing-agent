"""Write operations for operator suggestion decisions."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.decisions import record_suggestion_decision
from app.models import Event, Suggestion
from app.schemas import DecisionCreate
from app.security import Principal


async def apply_decision(
    session: AsyncSession,
    suggestion: Suggestion,
    event: Event,
    body: DecisionCreate,
    principal: Principal,
) -> Suggestion:
    """Apply, commit, and refresh an operator decision transaction."""
    await record_suggestion_decision(session, suggestion, event, body, principal)
    await session.commit()
    await session.refresh(suggestion)
    return suggestion
