# pgAdmin 4 integration

## Registered server

The reusable server definition is:

```text
Name: ART PostgreSQL
Group: ART Local
Host: 127.0.0.1
Port: 5432
Maintenance database: healing
Username: healing
SSL mode: prefer
```

The definition is stored in `examples/pgadmin-servers.json`. Passwords are not
stored in that file. Enter the database password when pgAdmin first connects.

## Connect

1. Open pgAdmin 4.
2. Expand `Servers`.
3. Expand `ART Local`.
4. Select `ART PostgreSQL`.
5. Enter the `healing` role password.
6. Optionally select **Save Password** for this local development connection.

## Browse ART

Navigate to:

```text
ART PostgreSQL
└── Databases
    └── healing
        └── Schemas
            ├── public
            │   └── Tables
            ├── operations
            │   └── Tables
            └── art_reporting
                └── Views
```

The `public` schema contains ART's governed operational tables.

The `operations` schema contains the configured example existing-table bridge.

The `art_reporting` schema contains read-only operational views:

- `event_pipeline`: event, outbox, routing, and suggestion in one row.
- `tenant_summary`: event/suggestion counts and average confidence.
- `integration_activity`: external ingestion and publication state.
- `reference_library`: accepted/rejected decisions and future reuse counts.

The underlying history tables are:

- `suggestion_decisions`
- `remediation_references`

The `art` schema contains the enterprise lifecycle requested in
`ART_Feedback.docx`, including failure events, agent runs and steps, decision
journals, impact records, test selection, execution intents/results,
self-healing proposals, outcome feedback, and event inbox/outbox tables.
Use `art.v_agent_run_summary` for workflow health and
`art.v_correlation_trace` for end-to-end correlation.

When a suggestion is accepted, ART activates its remediation reference. Similar
future events retrieve that record as `accepted_remediation` evidence and
increment its `use_count`. A rejected decision remains queryable but inactive.

## Query workbook

Open pgAdmin's Query Tool for the `healing` database, then load:

```text
examples/pgadmin_art_dashboard.sql
```

It contains queries for:

- Tenant health.
- End-to-end event processing.
- Existing-table integration.
- Failed or pending events.
- Review/suppressed suggestions.
- Outbox backlog.
- Webhook retry/dead-letter state.
- Audit history.
- Human decisions and reusable remediation history.

## Import on another machine

In pgAdmin:

```text
Tools -> Import/Export Servers -> Import
```

Choose `examples/pgadmin-servers.json`.

Or use the pgAdmin `setup.py load-servers` command documented for the installed
platform package. Passwords must be supplied separately.
