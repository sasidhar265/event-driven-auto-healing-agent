"""Enterprise webhook delivery tables."""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS supports both upgrades and fresh databases because 0001 originally
    # bootstrapped metadata dynamically.
    statements = ["""
    CREATE TABLE IF NOT EXISTS webhook_subscriptions (
      id UUID PRIMARY KEY, tenant_id VARCHAR(100) NOT NULL, name VARCHAR(150) NOT NULL,
      callback_url VARCHAR(2000) NOT NULL, event_types JSONB NOT NULL,
      secret VARCHAR(500), active BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """, "CREATE INDEX IF NOT EXISTS ix_webhook_subscriptions_tenant_id ON webhook_subscriptions (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_webhook_subscriptions_tenant_active ON webhook_subscriptions (tenant_id, active)", """
    CREATE TABLE IF NOT EXISTS webhook_deliveries (
      id UUID PRIMARY KEY, tenant_id VARCHAR(100) NOT NULL,
      subscription_id UUID NOT NULL REFERENCES webhook_subscriptions(id),
      suggestion_id UUID NOT NULL REFERENCES suggestions(id), status VARCHAR(30) NOT NULL,
      attempts INTEGER NOT NULL DEFAULT 0, response_status INTEGER, last_error TEXT,
      next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(), delivered_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CONSTRAINT uq_delivery_subscription_suggestion UNIQUE (subscription_id, suggestion_id)
    )
    """, "CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_tenant_id ON webhook_deliveries (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_due ON webhook_deliveries (status, next_attempt_at)"]
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS webhook_deliveries")
    op.execute("DROP TABLE IF EXISTS webhook_subscriptions")
