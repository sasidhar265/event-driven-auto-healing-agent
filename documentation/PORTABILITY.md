# Portable deployment and PostgreSQL integration

## Goal

ART keeps its governed internal data model stable while adapting to different
machines, environments, and existing PostgreSQL schemas through configuration.

This avoids editing agent, API, worker, or policy code for every organization.

```text
Existing event table
        |
        | Configured table/column mapping
        v
PostgreSQL bridge
        |
        v
ART event + outbox + agents + governance
        |
        +-----------------------+
        |                       |
        v                       v
Existing result table     Allow-listed columns
(insert mode)             on event table
                          (update_event mode)
```

## Supported environments

ART can run:

- As local Python processes against Postgres.app or another local PostgreSQL server.
- As local Python processes against an external PostgreSQL server.
- Against one PostgreSQL database for ART and another for legacy integration.
- Against the same database for both ART and existing tables.

Only configuration differs between these environments.

## New-machine setup

### Local setup

Requirements:

- PostgreSQL 16 or a compatible supported PostgreSQL version.
- Python 3.12.
- Git.
- A database and role for ART.

Create local Python tooling:

```bash
make setup
```

Copy and customize configuration:

```bash
cp .env.integration.example .env
```

Validate migrations and mappings:

```bash
make migrate
make validate-integration
```

Run in two terminals:

```bash
make api
```

```bash
make worker
```

## ART database versus external database

`DATABASE_URL` identifies ART's governed internal database. It contains:

- Events and the transactional outbox.
- Suggestions and confidence/policy results.
- Knowledge and policies.
- Audit logs.
- Webhook state.
- Integration ingestion/publication tracking.

`EXTERNAL_POSTGRES_URL` identifies the existing database being integrated. It
may equal `DATABASE_URL`, but it does not have to.

Both URLs use SQLAlchemy's async PostgreSQL form:

```text
postgresql+asyncpg://username:password@hostname:5432/database
```

Store real passwords in a secret manager or injected environment variable, not
in committed files.

## Mapping an existing event table

Enable the bridge:

```text
EXTERNAL_POSTGRES_ENABLED=true
```

Map the table:

```text
EXTERNAL_EVENT_TABLE=operations.incidents
```

Map its columns:

```text
EXTERNAL_EVENT_ID_COLUMN=incident_number
EXTERNAL_EVENT_TYPE_COLUMN=category
EXTERNAL_EVENT_SOURCE_COLUMN=origin
EXTERNAL_EVENT_SEVERITY_COLUMN=priority
EXTERNAL_EVENT_CORRELATION_COLUMN=trace_key
EXTERNAL_EVENT_PAYLOAD_COLUMN=diagnostics
EXTERNAL_EVENT_TENANT_COLUMN=customer
EXTERNAL_EVENT_ACTOR_COLUMN=reported_by
EXTERNAL_EVENT_CREATED_COLUMN=reported_at
EXTERNAL_EVENT_PROCESSED_COLUMN=art_ingested_at
```

The mapped fields must provide:

- A stable external ID.
- Event type.
- Source.
- Severity: `info`, `warning`, `error`, or `critical`.
- Correlation key.
- A JSON object payload.
- Tenant.
- Optional actor.
- Creation timestamp.
- A nullable timestamp ART may update after durable ingestion.

ART validates table and column existence before the worker begins polling.
Unsafe SQL identifiers are rejected.

## Result mode: insert

Use this when an existing integration supports a separate recommendation table:

```text
EXTERNAL_RESULT_MODE=insert
EXTERNAL_RESULT_TABLE=operations.remediation_recommendations
```

Map the result columns:

```text
EXTERNAL_RESULT_SUGGESTION_ID_COLUMN=recommendation_id
EXTERNAL_RESULT_EVENT_ID_COLUMN=incident_number
EXTERNAL_RESULT_STATUS_COLUMN=governance_status
EXTERNAL_RESULT_CONFIDENCE_COLUMN=confidence
EXTERNAL_RESULT_AGENT_COLUMN=specialist
EXTERNAL_RESULT_PAYLOAD_COLUMN=recommendation
EXTERNAL_RESULT_CREATED_COLUMN=created_at
```

The suggestion ID column must have a unique or primary-key constraint. ART uses
`ON CONFLICT DO NOTHING` to make publication idempotent.

## Result mode: update_event

Use this when the originating event row should receive ART's result:

```text
EXTERNAL_RESULT_MODE=update_event
EXTERNAL_EVENT_RESULT_COLUMN=art_suggestion
EXTERNAL_EVENT_RESULT_STATUS_COLUMN=art_status
```

Only those two configured columns and the ingestion timestamp are updated.
There is no arbitrary table-update API and no user-provided SQL fragment.

The recommended column types are:

```sql
art_suggestion JSONB,
art_status TEXT,
art_ingested_at TIMESTAMPTZ
```

## Safe database permissions

Use separate roles in production.

ART internal role:

- Full DML on ART-owned tables.
- Schema migration permission only for the migration job.

External bridge role:

- `SELECT` on the mapped event table.
- `UPDATE` only on the mapped ingestion/result/status columns.
- `INSERT` on the mapped result table when using insert mode.
- No `DROP`, `ALTER`, or unrelated table permissions.

Example:

```sql
GRANT SELECT ON operations.incidents TO art_bridge;
GRANT UPDATE (art_ingested_at, art_suggestion, art_status)
  ON operations.incidents TO art_bridge;
GRANT INSERT ON operations.remediation_recommendations TO art_bridge;
```

## Delivery semantics

Inbound bridge:

1. Selects unprocessed rows with `FOR UPDATE SKIP LOCKED`.
2. Persists the ART event and outbox transaction.
3. Records which integration ingested the event.
4. Updates the configured ingestion timestamp.
5. Relies on tenant plus external event ID for redelivery idempotency.

Outbound bridge:

1. Selects only ready suggestions for events ingested by that bridge.
2. Inserts or updates the configured external destination.
3. Records publication in `integration_publications`.
4. Does not publish unrelated API or Kafka events to that mapping.

Unexpected failures leave work eligible for retry.

## Validation

Run the read-only validator before starting a worker:

```bash
make validate-integration
```

Example success:

```json
{
  "valid": true,
  "event_table": "operations.failure_events",
  "result_mode": "insert",
  "result_table": "operations.art_suggestions",
  "missing_event_columns": [],
  "missing_result_columns": []
}
```

The worker also performs this validation at startup and refuses to poll an
invalid mapping.

## Adding another database engine

The current bridge is intentionally PostgreSQL-specific because it uses JSONB,
`SKIP LOCKED`, and PostgreSQL identifier rules. To add another engine:

1. Implement another adapter under `app/integrations`.
2. Preserve the `EventCreate` ingestion contract.
3. Keep identifier validation and value parameterization.
4. Track ingestion and publication using the internal integration tables.
5. Add startup validation and idempotency tests.

Agent, policy, UI, and webhook code should not need to change.

## Maintenance checklist

Before deployment:

1. Copy the appropriate environment template.
2. Inject credentials through the target secret manager.
3. Run `alembic upgrade head`.
4. Run the bridge validator.
5. Run tests.
6. Start one worker and verify ingestion/publication.
7. Scale workers only after `SKIP LOCKED` behavior is verified.
8. Monitor pending outbox rows and integration publication lag.

Before changing a mapping:

1. Stop bridge workers.
2. Validate the new table/columns with a read-only role.
3. Confirm external IDs remain stable.
4. Confirm JSON payloads are objects.
5. Confirm the result destination has its uniqueness constraint.
6. Restart one worker and inspect audit/integration state.
