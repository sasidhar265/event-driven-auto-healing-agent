-- ART operational workbook for pgAdmin 4 Query Tool.

-- 1. Tenant health and suggestion readiness
SELECT *
FROM art_reporting.tenant_summary
ORDER BY latest_event_at DESC NULLS LAST;

-- 2. Complete event -> outbox -> specialist -> suggestion flow
SELECT *
FROM art_reporting.event_pipeline
ORDER BY event_created_at DESC
LIMIT 200;

-- 3. Existing-table ingestion and result publication
SELECT *
FROM art_reporting.integration_activity
ORDER BY ingested_at DESC
LIMIT 200;

-- 4. Pending or failed processing
SELECT id, tenant_id, external_id, event_type, status, attempts, error, created_at
FROM events
WHERE status::text IN ('RECEIVED', 'PROCESSING', 'FAILED')
ORDER BY created_at;

-- 5. Suggestions requiring attention
SELECT
  id, tenant_id, event_id, agent_type, title, status, confidence,
  policy_result, proposed_changes, created_at
FROM suggestions
WHERE status::text IN ('REVIEW', 'SUPPRESSED')
ORDER BY created_at DESC;

-- 6. Outbox backlog
SELECT topic, count(*) AS pending, min(available_at) AS oldest
FROM outbox
WHERE published_at IS NULL
GROUP BY topic;

-- 7. Webhook retry/dead-letter state
SELECT
  tenant_id, status, count(*) AS deliveries,
  max(attempts) AS maximum_attempts,
  max(created_at) AS latest_delivery
FROM webhook_deliveries
GROUP BY tenant_id, status
ORDER BY tenant_id, status;

-- 8. Audit history
SELECT tenant_id, actor, action, resource_type, resource_id, details, created_at
FROM audit_logs
ORDER BY created_at DESC
LIMIT 500;

-- 9. Human decisions and reusable remediation references
SELECT
  tenant_id, event_type, agent_type, outcome, active, confidence,
  decision_reason, decided_by, decided_at, use_count, last_used_at
FROM art_reporting.reference_library
ORDER BY decided_at DESC
LIMIT 200;

-- 10. Accepted references most frequently reused by future analysis
SELECT
  tenant_id, event_type, title, agent_type, confidence, use_count, last_used_at
FROM art_reporting.reference_library
WHERE active
ORDER BY use_count DESC, last_used_at DESC NULLS LAST;
