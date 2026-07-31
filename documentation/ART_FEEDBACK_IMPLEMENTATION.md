# ART feedback implementation

This document maps `ART_Feedback.docx` to the implementation delivered in
migrations `0008` and `0009`.

## Requirement coverage

| Requirement | Implementation |
|---|---|
| Mandatory correlation | Every `art` record and `/v1/art` create request requires `correlation_id` |
| Tenant isolation | Tenant comes from authenticated `X-Tenant-Id`; clients cannot submit or override it |
| Environment awareness | Controlled `dev`, `test`, `preprod`, or `prod` value on every ART resource |
| General failure model | `art.failure_events` supports UI, API, functional, data, performance, security, batch, mainframe, infrastructure, and unknown failures |
| Payload minimisation | Normalized `payload_summary`; large bodies require `payload_ref`; automatic recording removes common credential/body fields |
| Severity | Controlled `LOW`, `MEDIUM`, `HIGH`, and `CRITICAL` values |
| Multi-agent workflows | Separate `art.agent_runs` and `art.agent_run_steps` resources |
| Explainability | `art.agent_decision_journals` stores rationale, confidence reason, evidence, model, prompt, and policy provenance |
| Impact analysis | `art.impact_assessments` supports proactive changes and reactive failures |
| Dependency analysis | `art.impact_dependencies` records direction, type, confidence, source, and knowledge-graph reference |
| Test selection | `art.test_selection_decisions` records selected, skipped, and mandatory tests, risk coverage, duration, and rationale |
| Sequencing | `sequence_plan` is persisted on `art.execution_intents` |
| Governance | Policy decision/version and approval fields are present; approved or executed intents require a policy decision |
| Execution intent | `art.execution_intents` records the governed plan sent to an external execution plane |
| Execution outcomes | `art.execution_result_refs` stores counts and references while artifacts remain external |
| Self-healing | `art.self_heal_proposals` implements suggest → approve → apply → evidence with rollback references |
| Learning feedback | `art.outcome_feedback` stores effectiveness, flakiness, defect, and model-drift signals |
| Event idempotency | `art.event_inbox` has a unique source `event_id` |
| Reliable publishing | `art.event_outbox` records publish state independently of transport |
| Traceability | `art.v_agent_run_summary`, `art.v_correlation_trace`, audit logs, and the correlation API |
| Standard naming | Lowercase snake_case tables, fields, paths, and identifiers |
| Standard timestamps | UTC `created_at`, `updated_at`, `started_at`, and `completed_at` as applicable |

## Database contract compliance

Migration `0009_align_art_feedback_schema.py` aligns the deployed schema with
the SQL contract embedded in `ART_Feedback.docx`. It introduces the document's
nine native PostgreSQL enum types, converts confidence and risk values to
`NUMERIC(5,4)`, and adds the recommended lookup, governance, status, component,
and external-run indexes without discarding existing records.

Automated contract tests verify all 13 ART tables, mandatory tenant and
correlation context, enum-backed controlled values, and numeric precision. The
optional inbox and outbox retain `environment` as an additional isolation field
because the narrative requirements mandate environment awareness across
ART-owned records, even though those two sample table definitions omit it.

## API conventions

All endpoints are under `/v1/art`. They require:

```text
X-API-Key: <configured key>
X-Tenant-Id: <tenant>
X-Actor: <service or user identity>
```

Every create response includes:

- `resource_id`
- `correlation_id`
- `tenant_id`
- `environment`
- `status`
- `created_at`
- `updated_at` when the resource supports updates
- `data` containing the complete record and a `related` object populated from
  the supporting PostgreSQL tables for the same tenant and correlation

The public contract now follows the four resource paths explicitly recommended
in `ART_Feedback.docx`. Each path supports `POST` and tenant-scoped `GET`.

| Public resource | Path | Supporting table data returned by `GET` |
|---|---|---|
| Failure events | `/v1/art/failure-events` | `event_inbox`, `event_outbox` |
| Agent workflows | `/v1/art/agent-runs` | `agent_run_steps`, `agent_decision_journals` |
| Impact assessments | `/v1/art/impact-assessments` | `impact_dependencies` |
| Execution intents | `/v1/art/execution-intents` | `test_selection_decisions`, `execution_result_refs`, `self_heal_proposals`, `outcome_feedback`, `event_outbox` |

Collection reads accept `correlation_id`, `environment`, and `limit` query
parameters. Use `correlation_id` to retrieve one lifecycle without calling
separate table-level APIs:

```text
GET /v1/art/agent-runs?correlation_id=<uuid>
```

The former table-level routes remain available internally for workers and
backwards compatibility, but are intentionally omitted from Swagger and the UI
API Explorer. PostgreSQL tables remain separate for referential integrity and
maintainability; only the external API surface is consolidated.

## Automatic lifecycle recording

The original `POST /v1/events` and CloudEvents ingestion flows remain
compatible. When the worker processes an event, it now automatically records:

1. A normalized `failure_event`.
2. A `FAILURE_ANALYSIS` agent run.
3. The failure-router step.
4. Each specialist remediation step.
5. A decision journal with explanation and evidence.
6. A self-heal proposal for supported proposal types.
7. Final workflow status and execution time.

Legacy string correlation keys are converted to deterministic UUIDs. Existing
UUID correlation keys are preserved.

## Local verification

Apply and inspect the database:

```bash
make migrate
make db-inspect
```

Run the API and exercise all resources:

```bash
make api
make verify-art
```

Interactive API documentation is available at:

```text
http://127.0.0.1:8000/docs
```
