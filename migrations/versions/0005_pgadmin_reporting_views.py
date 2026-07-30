"""Read-only reporting views for pgAdmin and operational SQL tools."""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS art_reporting")
    op.execute("""
        CREATE OR REPLACE VIEW art_reporting.event_pipeline AS
        SELECT
          e.id AS event_id,
          e.tenant_id,
          e.external_id,
          e.event_type,
          e.source,
          e.severity,
          e.correlation_key,
          e.status AS event_status,
          e.attempts,
          e.created_at AS event_created_at,
          e.processed_at,
          o.published_at AS outbox_consumed_at,
          s.id AS suggestion_id,
          s.agent_type,
          s.status AS suggestion_status,
          s.confidence,
          s.proposed_changes->'routing'->>'category' AS routed_to,
          s.title,
          s.created_at AS suggestion_created_at
        FROM events e
        LEFT JOIN outbox o ON o.aggregate_id = e.id AND o.topic = 'event.received'
        LEFT JOIN suggestions s ON s.event_id = e.id
    """)
    op.execute("""
        CREATE OR REPLACE VIEW art_reporting.tenant_summary AS
        SELECT
          e.tenant_id,
          count(DISTINCT e.id) AS event_count,
          count(DISTINCT e.id) FILTER (
            WHERE e.status::text = 'COMPLETED'
          ) AS completed_events,
          count(DISTINCT s.id) AS suggestion_count,
          count(DISTINCT s.id) FILTER (
            WHERE s.status::text = 'READY'
          ) AS ready_suggestions,
          count(DISTINCT s.id) FILTER (
            WHERE s.status::text = 'REVIEW'
          ) AS review_suggestions,
          round(avg(s.confidence)::numeric, 3) AS average_confidence,
          max(e.created_at) AS latest_event_at
        FROM events e
        LEFT JOIN suggestions s ON s.event_id = e.id
        GROUP BY e.tenant_id
    """)
    op.execute("""
        CREATE OR REPLACE VIEW art_reporting.integration_activity AS
        SELECT
          e.tenant_id,
          e.external_id,
          ii.source AS integration,
          ii.ingested_at,
          s.id AS suggestion_id,
          s.agent_type,
          s.status AS suggestion_status,
          ip.target AS publication_target,
          ip.published_at
        FROM integration_ingestions ii
        JOIN events e ON e.id = ii.event_id
        LEFT JOIN suggestions s ON s.event_id = e.id
        LEFT JOIN integration_publications ip ON ip.suggestion_id = s.id
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS art_reporting.integration_activity")
    op.execute("DROP VIEW IF EXISTS art_reporting.tenant_summary")
    op.execute("DROP VIEW IF EXISTS art_reporting.event_pipeline")
    op.execute("DROP SCHEMA IF EXISTS art_reporting")
