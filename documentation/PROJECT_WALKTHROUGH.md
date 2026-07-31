# ART project walkthrough

This guide explains the Event-Driven Auto-Healing Recommendation Tool (ART) for
both non-technical and technical readers. It describes what the system does,
why each component exists, how data moves through it, where to find the code,
and how to operate or extend it safely.

For a diagram-first explanation, open the
[ART visual guide](VISUAL_GUIDE.md).

## 1. What this project does

ART converts failure events into explainable remediation suggestions.

A failure event can come from:

- A browser or UI automation test.
- An API test or application monitoring platform.
- Application logs or exception monitoring.
- PostgreSQL or another database monitoring source.
- Infrastructure, dependency, security, or performance monitoring.
- An HTTP client.
- A Kafka-compatible event backbone using CloudEvents.

ART then:

1. Validates the event.
2. Saves it in PostgreSQL.
3. Queues background work using a transactional outbox record.
4. Identifies the failure category.
5. Routes it to the appropriate specialist logic.
6. Retrieves relevant knowledge and previously accepted remediations.
7. Produces a structured suggestion.
8. Applies policy rules and calculates confidence.
9. Classifies the suggestion as Suppressed, Review, or Ready.
10. Shows the result and processing trace in the UI.
11. Records significant actions in the audit trail.
12. Stores human acceptance or rejection for future reference.

ART recommends a change. It does not directly edit source code, execute SQL
against a target application, deploy software, or restart production services.

## 2. Why the project exists

Monitoring products are good at reporting that something failed. They often do
not answer all of these questions:

- What kind of failure is this?
- Which evidence supports that classification?
- Which component or source identified it?
- What change is likely to address it?
- How confident is the recommendation?
- Does organizational policy permit the recommendation to proceed?
- Has the same remediation worked before?
- Who accepted or rejected it?
- How can an operator trace every processing step later?

ART provides that recommendation and traceability layer between failure
producers and the systems or people authorized to make real changes.

## 3. Example in plain language

Assume a checkout UI test reports:

```text
NoSuchElement: XPath did not match the Submit order button
```

The event includes the failed XPath, test name, test file, and nearby DOM
candidates. ART:

1. Records the failure and its correlation ID.
2. Recognizes UI locator evidence.
3. Selects the XPath/UI specialist.
4. Prefers a stable `data-testid` or accessible locator over the obsolete
   XPath.
5. Suggests the test-code change, validation steps, and rollback approach.
6. Scores the evidence.
7. Applies internal governance.
8. Shows the result, confidence class, and processing log.
9. Records whether an operator accepts or rejects it.

An API timeout, deadlock, logic exception, or infrastructure failure follows the
same overall flow but is routed to a different specialist.

## 4. Safety model

The most important design decision is the separation of recommendation and
execution.

ART is allowed to:

- Analyze failure evidence.
- Retrieve knowledge and prior accepted remediations.
- Propose code, configuration, test, database, or operational changes.
- Explain why it made a recommendation.
- Classify the result using confidence and policy.
- Publish a ready result to an authorized downstream integration.

ART is not allowed to:

- Approve its own production change.
- Modify the target application database.
- Commit a source-code change.
- Deploy or roll back an application.
- Bypass policy.
- Hide rejected or suppressed outcomes.

This boundary keeps deployment, approval, and change-management systems
authoritative.

## 5. System architecture

```text
Failure producer
(UI/API tests, APM, logs, monitoring, HTTP, Kafka)
                         |
                         v
                  Ingestion boundary
             Native event or CloudEvent 1.0
                         |
                         v
              PostgreSQL transaction
        event + audit record + outbox work item
                         |
                         v
                 Background worker
                         |
          +--------------+--------------+
          |                             |
          v                             v
  Knowledge and prior fixes      Failure router
                                        |
                                        v
                             Selected specialist
                                        |
                                        v
                         Optional AI enrichment
                                        |
                                        v
                      Policy and confidence gate
                         /       |        \
                        v        v         v
                 Suppressed    Review     Ready
                                        |
                                        v
                         Optional signed webhook

PostgreSQL is read back through the API by the ART browser console.
```

The API and worker are separate processes:

- The API responds quickly after safely accepting an event.
- The worker performs analysis asynchronously.
- PostgreSQL is the shared source of truth.

## 6. End-to-end data flow

### Stage 1: ingestion

`POST /v1/events` accepts the native event shape. In the integration API
profile, `POST /v1/events/cloudevents` accepts CloudEvents.

The ingestion transaction writes:

- One `events` record.
- One `outbox` work item.
- One `audit_logs` record.

The `(tenant_id, external_id)` uniqueness rule makes repeated delivery safe.
The existing event is returned instead of creating a duplicate.

### Stage 2: worker pickup

`app/worker.py` polls unpublished outbox records. It uses database row locking
with `SKIP LOCKED`, allowing more than one worker to process different work
without taking the same row.

### Stage 3: identification and routing

`app/services.py` evaluates explicit categories, structured fields, and text
signals. Supported domains include:

- UI
- API
- Logic
- Functional workflow
- Test data
- Database
- Infrastructure
- Dependency
- Security
- Performance

Structured evidence is weighted more strongly than vague text. Ambiguous
failures are routed toward evidence collection instead of inventing a precise
fix.

### Stage 4: knowledge and prior outcomes

The worker retrieves tenant-scoped knowledge and accepted remediation
references. Rejected suggestions remain auditable but are not treated as
positive fix evidence.

### Stage 5: suggestion

The selected specialist returns:

- A title.
- A human-readable rationale.
- Structured proposed changes.
- Evidence.
- An initial confidence value.
- Routing details.

The optional enterprise AI provider may enrich this candidate. It cannot set
the final status or bypass governance.

### Stage 6: confidence and governance

Default confidence thresholds are:

| Classification | Rule | Meaning |
|---|---|---|
| Suppressed | Below `0.60`, or policy blocked | Evidence is insufficient or the action is not permitted. |
| Review | `0.60` through `0.79`, or approval required | A person must review it. |
| Ready | `0.80` or above and policy eligible | Eligible for downstream delivery. |

Thresholds are configured with
`CONFIDENCE_REVIEW_THRESHOLD` and
`CONFIDENCE_DELIVERY_THRESHOLD`.

The Decision Model on the Overview screen calculates and displays these
classifications even after a suggestion has later been accepted or rejected.
Its compact table can be filtered by state and ranked by confidence or age.

### Stage 7: outcome and learning

An operator can accept or reject an eligible suggestion. The decision is stored
in `suggestion_decisions`. Accepted results are also added to the remediation
reference library for similar future failures.

### Stage 8: audit and trace

The event trace explains ingestion, identification, classification, change
context, suggestion, confidence, and outcome. The Audit Trail stores durable
actions and supports:

- Environment filtering.
- Correlation ID search.
- Preset time ranges from 30 minutes through four weeks.
- Custom pop-up calendar and timestamp ranges.
- Separate correlation ID and failure ID columns.
- JSON export of the filtered records.

## 7. Understanding the identifiers

| Identifier | Purpose |
|---|---|
| Event database ID | Internal UUID for one `events` row. |
| Failure ID / external ID | Identifier supplied by the source system for the reported incident. |
| Correlation ID / correlation key | Connects records belonging to the same build, request, release, or incident journey. |
| Suggestion ID | Internal UUID for one recommendation. |
| Tenant ID | Isolation boundary supplied through the trusted API header; intentionally not shown as a normal UI field. |
| Environment | `dev`, `test`, `preprod`, or `prod`; stored in the event envelope and available as a filter. |

A correlation ID is not an environment prefix. The environment is a separate
field, allowing the same console to trace records across environments.

## 8. Browser console

The UI is served from `app/static` by the FastAPI application. It uses
Bootstrap foundations and plain JavaScript, so there is no separate frontend
build process.

### Overview

Shows:

- Total ingested events.
- Events currently queued or processing.
- Total suggestions.
- Suggestions currently in Ready status.
- Recent events filtered by environment.
- The live Decision Model with confidence-classified records.

### Incident intake

Provides failure profiles for common domains. A profile only prepares the event
envelope; the resulting incident and suggestion are still created through the
real API and PostgreSQL.

### Suggestions

Shows ART remediation recommendations and their evidence. The simplified
outcome filters are All, Accepted, and Rejected. Suppressed, Review, and Ready
remain visible through All and are separately explained in the Decision Model.

### Audit Trail

Reads durable audit data from PostgreSQL through `GET /v1/audit`. The data area
scrolls independently, and the table heading remains visible.

### Connection

The Connection popup displays:

- Runtime reachability.
- API endpoint and active API profile.
- PostgreSQL reachability.
- Safe database host, port, database name, and username.
- Browser-local API configuration.

Passwords and API keys are not displayed in the connection summary.

## 9. Code walkthrough

### Application entry point: `app/main.py`

Start here to understand which API profile is active, which routers are
registered, how the UI is mounted, and how `/health/live` reports safe
connection details.

### Configuration: `app/config.py`

Defines environment variables and defaults using Pydantic settings. Application
code calls `get_settings()` rather than reading environment variables directly.

### Database session: `app/db.py`

Creates the asynchronous SQLAlchemy engine and session factory. API requests
receive a short-lived session through dependency injection. The worker creates
sessions around each polling cycle.

### Core persistence: `app/models.py`

Defines operational tables such as events, suggestions, audit logs, outbox,
decisions, subscriptions, deliveries, and remediation references.

### Request/response validation: `app/schemas.py`

Contains typed Pydantic contracts for operational API requests and responses.
Invalid payloads are rejected before business processing begins.

### Authentication and tenant scope: `app/security.py`

Validates `X-API-Key` and requires `X-Tenant-Id`. It constructs the trusted
principal used by API queries. `X-Actor` identifies the calling person or
system in audit records.

### Operational API: `app/api.py`

Contains event, trace, overview, suggestion, decision, audit, integration, and
internal-service handlers. Read it alongside `app/schemas.py` and
`app/models.py`.

### Ingestion: `app/ingestion.py`

Owns native/CloudEvent conversion, idempotency, event creation, outbox creation,
and initial audit creation. Keeping this in one service lets HTTP and Kafka use
the same persistence behavior.

### Processing: `app/processor.py`

Coordinates knowledge retrieval, routing, specialist execution, optional AI
enrichment, policy evaluation, suggestion persistence, lifecycle recording,
and ready-webhook creation.

### Domain services: `app/services.py`

Contains the failure router, specialist implementations, knowledge retrieval,
AI provider boundary, and Policy Engine.

### Worker: `app/worker.py`

Continuously processes outbox work and due webhook deliveries. It also invokes
the optional external PostgreSQL bridge when configured.

### Decisions: `app/decisions.py`

Stores accept/reject actions and updates the reusable remediation reference
library.

### Webhooks and event backbone

- `app/webhooks.py` signs and retries outbound ready-suggestion delivery.
- `app/backbone.py` consumes structured or binary CloudEvents from Kafka.

### Enterprise ART lifecycle

- `app/art_models.py`: normalized enterprise lifecycle tables.
- `app/art_schemas.py`: lifecycle request and response contracts.
- `app/art_repository.py`: tenant-scoped lifecycle persistence.
- `app/art_lifecycle.py`: records the operational pipeline into lifecycle
  resources.
- `app/art_api.py`: admin/full-profile lifecycle endpoints.

### UI source

- `app/static/index.html`: page structure and Bootstrap controls.
- `app/static/app.js`: API calls, rendering, filtering, modals, and interaction.
- `app/static/styles.css`: ART appearance and responsive layout.

### Migrations and tests

- `migrations/versions`: ordered PostgreSQL schema history.
- `tests`: unit, service, lifecycle, API-inventory, integration, and UI contract
  tests.

## 10. PostgreSQL data model

### Operational tables

| Table | What it stores |
|---|---|
| `events` | Original normalized failure envelope and processing state. |
| `suggestions` | Recommendation, evidence, policy result, confidence, and current outcome. |
| `audit_logs` | Durable actor/action/resource history. |
| `outbox` | Reliable background work created in the ingestion transaction. |
| `knowledge_items` | Internal tenant-scoped guidance and runbooks. |
| `policies` | Internal governance rules. |
| `suggestion_decisions` | Human or system accept/reject actions. |
| `remediation_references` | Reusable accepted-remediation evidence. |
| `webhook_subscriptions` | Downstream consumers of ready suggestions. |
| `webhook_deliveries` | Delivery attempt, retry, and dead-letter state. |
| `integration_ingestions` | External PostgreSQL bridge input tracking. |
| `integration_publications` | External PostgreSQL bridge output tracking. |

### Enterprise lifecycle tables

The migration `0008_enterprise_art_lifecycle.py` adds normalized tables for
failure events, agent runs and steps, decision journals, impact analysis,
dependencies, test selection, execution intents and references, self-heal
proposals, feedback, and lifecycle inbox/outbox records.

Use pgAdmin for inspection and reporting, but let Alembic own schema changes.
See [PGADMIN.md](PGADMIN.md).

## 11. API guide

Every protected request needs:

```text
X-API-Key: <configured key>
X-Tenant-Id: <trusted tenant>
X-Actor: <person or publishing system>
```

The operations profile contains the UI-facing surface:

| Method and path | Purpose |
|---|---|
| `POST /v1/events` | Submit a native failure event. |
| `GET /v1/events` | Retrieve tenant events. |
| `GET /v1/events/{event_id}` | Retrieve one event. |
| `GET /v1/events/{event_id}/trace` | Retrieve the ART processing story. |
| `GET /v1/overview` | Retrieve metrics, activity, and Decision Model data. |
| `GET /v1/suggestions` | Retrieve suggestions, optionally by event. |
| `POST /v1/suggestions/{id}/decision` | Accept or reject a suggestion. |
| `GET /v1/audit` | Retrieve filtered audit records. |
| `GET /health/live` | Check runtime and safe database connection details. |

Optional profiles:

| Profile | Adds |
|---|---|
| `integration` | CloudEvent ingestion, webhook subscriptions, deliveries, retry. |
| `admin` | Internal knowledge/policy/reference APIs and enterprise ART lifecycle APIs. |
| `full` | Operations, integration, internal, and lifecycle APIs together. |

OpenAPI documentation always reflects the selected profile:

```text
http://127.0.0.1:8000/docs
```

## 12. Running locally

### Requirements

- macOS or another supported Unix-like environment.
- Python 3.12.
- PostgreSQL.
- Git.
- `make`.

### First setup

```bash
cp .env.example .env
make setup
make postgres-app-setup
make migrate
```

Run the API:

```bash
make api
```

Run the worker in another terminal:

```bash
make worker
```

Open:

```text
UI:      http://127.0.0.1:8000/ui/
OpenAPI: http://127.0.0.1:8000/docs
Health:  http://127.0.0.1:8000/health/live
```

### Why both API and worker are required

The API accepts and stores the event. The worker transforms queued work into a
suggestion. If the API is running without the worker, new events remain
received/queued and no new suggestion appears.

## 13. Configuration

Copy `.env.example` and change environment-specific values in `.env`. Never
commit `.env`.

Important variables:

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | ART PostgreSQL connection. |
| `API_KEY` | Shared local API credential. Replace outside local development. |
| `API_PROFILE` | `operations`, `integration`, `admin`, or `full`. |
| `CONFIDENCE_REVIEW_THRESHOLD` | Minimum confidence for Review. |
| `CONFIDENCE_DELIVERY_THRESHOLD` | Minimum confidence for Ready. |
| `AI_PROVIDER` | Deterministic default or approved enterprise provider. |
| `WORKER_POLL_SECONDS` | Worker idle polling interval. |
| `EXTERNAL_POSTGRES_ENABLED` | Enables the generic external-table bridge. |
| `KAFKA_*` | Optional event-backbone configuration. |

The portability guide explains how to switch environments or map other
PostgreSQL tables without rewriting the core:
[PORTABILITY.md](PORTABILITY.md).

Routing keywords, weights, confidence bonuses, specialist instructions,
lifecycle mappings, batch sizes, and retry timing are maintained separately in
`app/resources/runtime_rules.json`. See the
[runtime configuration guide](CONFIGURATION.md).

## 14. Testing and verification

Run the complete suite:

```bash
make test
```

Run coverage:

```bash
make coverage
```

Validate the external PostgreSQL mapping:

```bash
make validate-integration
```

With the full API running, verify the enterprise lifecycle:

```bash
make api-full
make verify-art
```

The tests protect:

- Routing and specialist behavior.
- Processing and policy outcomes.
- Event ingestion and idempotency.
- Decision/reference behavior.
- Webhook selection and retry.
- Kafka/CloudEvent conversion.
- External PostgreSQL bridge mapping.
- Enterprise lifecycle state transitions.
- API-profile inventory.
- UI controls, modals, Bootstrap foundations, and critical API calls.

## 15. Maintenance guidance

### Adding a failure type

1. Define the expected structured evidence.
2. Add or extend routing signals in `app/services.py`.
3. Add the specialist behavior or safe abstention.
4. Add an incident profile only if it helps operators submit that evidence.
5. Add unit tests for strong, ambiguous, and incomplete evidence.
6. Document the event contract.

### Adding an API

1. Decide which profile owns it.
2. Define a Pydantic schema.
3. Enforce tenant scope in every query.
4. Keep business logic outside the route where practical.
5. Add it to `tests/test_api_inventory.py`.
6. Update this guide and OpenAPI description.

### Changing the database

1. Update the SQLAlchemy model.
2. Create a new Alembic migration; do not edit an applied migration.
3. Test upgrade behavior.
4. Update reporting views or pgAdmin documentation.
5. Keep credentials in environment configuration.

### Changing the UI

1. Use the existing Bootstrap control foundations.
2. Keep ART as the visible product boundary.
3. Retrieve operational data through the API, not hard-coded result records.
4. Prefer modals for record details.
5. Keep large tables independently scrollable.
6. Update UI contract tests.

## 16. Troubleshooting

### UI opens but no data appears

- Click Connection and confirm both runtime and PostgreSQL show Connected.
- Confirm the API key in the browser matches `.env`.
- Confirm the API is running on the configured base URL.

### Event remains received

- Start `make worker`.
- Inspect `outbox` for unpublished rows.
- Check worker output for processing errors.

### Suggestions filter looks empty

Accepted and Rejected are recorded outcomes. Confidence states are displayed in
the Overview Decision Model. Use All on the Suggestions screen to see every
current state.

### Database connection fails

- Confirm the PostgreSQL application is running.
- Verify host, port, database, and user in `DATABASE_URL`.
- Run `make postgres-app-inspect`.
- Use the Connection popup for the safe runtime view.

### API returns 401 or 422

- `401`: the API key is wrong.
- `422`: required headers or body fields are missing/invalid.
- Include both `X-API-Key` and `X-Tenant-Id`.

## 17. Production considerations

Before treating this reference runtime as production-ready:

- Replace the shared API key with gateway-managed OIDC/JWT identity.
- Manage secrets in a secret store.
- Enable TLS.
- Add PostgreSQL row-level security as defence in depth.
- Add metrics, traces, structured logs, and alerting.
- Define data retention and audit export.
- Run multiple workers and test failure recovery.
- Protect outbound webhooks with network controls and secret rotation.
- Review AI data handling and approved-model policies.
- Connect suggestions to an authorized change-management workflow rather than
  direct execution.

## 18. Related documents

- [ART visual guide](VISUAL_GUIDE.md)
- [Runtime configuration maintenance](CONFIGURATION.md)
- [Technical reference](README.md)
- [Portability and external-table integration](PORTABILITY.md)
- [pgAdmin 4 setup and reporting](PGADMIN.md)
- [ART requirement-to-implementation mapping](ART_FEEDBACK_IMPLEMENTATION.md)
