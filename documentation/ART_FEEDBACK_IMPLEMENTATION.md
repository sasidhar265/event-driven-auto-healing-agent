# ART feedback implementation

This document maps `ART_Feedback.docx` to the implementation delivered in
migration `0008`.

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
- `data` containing the complete record

Each collection supports `POST` and tenant-scoped `GET`. Every resource also
supports `GET /{resource_id}`.

| Resource | Path |
|---|---|
| Failure events | `/v1/art/failure-events` |
| Agent workflows | `/v1/art/agent-runs` |
| Agent steps | `/v1/art/agent-run-steps` |
| Decision journals | `/v1/art/decision-journals` |
| Impact assessments | `/v1/art/impact-assessments` |
| Impact dependencies | `/v1/art/impact-dependencies` |
| Test selection decisions | `/v1/art/test-selection-decisions` |
| Execution intents | `/v1/art/execution-intents` |
| Execution result references | `/v1/art/execution-result-refs` |
| Self-heal proposals | `/v1/art/self-heal-proposals` |
| Outcome feedback | `/v1/art/outcome-feedback` |
| Event inbox | `/v1/art/event-inbox` |
| Event outbox | `/v1/art/event-outbox` |

Collection reads accept `correlation_id`, `environment`, and `limit` query
parameters. The complete lifecycle trace is:

```text
GET /v1/art/correlations/{correlation_id}
```

Agent runs, execution intents, and self-heal proposals support governed state
updates:

```text
PATCH /v1/art/{resource}/{resource_id}/state
```

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
make postgres-app-inspect
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
