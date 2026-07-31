import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal, engine
from app.models import Outbox
from app.processor import process_event
from app.runtime_config import get_runtime_rules
from app.webhooks import deliver_due


async def run() -> None:
    settings = get_settings()
    rules = get_runtime_rules()
    bridge = None
    if settings.external_postgres_enabled:
        from app.integrations.postgres_bridge import ExternalPostgresBridge

        bridge = ExternalPostgresBridge(settings)
        validation = await bridge.validate()
        if not validation["valid"]:
            raise RuntimeError(f"invalid external PostgreSQL bridge mapping: {validation}")
    try:
        while True:
            pulled = await bridge.pull_events() if bridge else 0
            async with SessionLocal() as session:
                items = (await session.scalars(
                    select(Outbox).where(Outbox.published_at.is_(None))
                    .order_by(Outbox.available_at)
                    .limit(rules.delivery.worker_batch_size)
                    .with_for_update(skip_locked=True)
                )).all()
                for item in items:
                    if item.topic == "event.received":
                        await process_event(session, item.aggregate_id)
                    item.published_at = datetime.now(UTC)
                delivery_count = await deliver_due(session)
                await session.commit()
            pushed = await bridge.push_ready_suggestions() if bridge else 0
            busy = pulled or items or delivery_count or pushed
            idle_seconds = (
                settings.external_poll_seconds if bridge else settings.worker_poll_seconds
            )
            await asyncio.sleep(idle_seconds if not busy else 0)
    finally:
        if bridge:
            await bridge.close()


async def main() -> None:
    try:
        await run()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
