import asyncio
from app.config import get_settings
from app.db import SessionLocal, engine
from app.processor import process_event
from app.repositories.worker.commands import mark_published
from app.repositories.worker.queries import lock_pending_outbox
from app.runtime_config import get_runtime_rules
from app.test_execution import execute_accepted_suggestion
from app.webhooks import deliver_due


async def run() -> None:
    """Process durable outbox work, webhook deliveries, and any enabled DB bridge."""
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
                items = await lock_pending_outbox(session, rules.delivery.worker_batch_size)
                for item in items:
                    if item.topic == "event.received":
                        await process_event(session, item.aggregate_id)
                    elif item.topic == "event.reanalysis.requested":
                        await process_event(session, item.aggregate_id, force=True)
                    elif item.topic == "test.rerun.requested":
                        await execute_accepted_suggestion(session, item.aggregate_id)
                    mark_published(item)
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
    """Run the worker and always dispose its PostgreSQL connection pool."""
    try:
        await run()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
