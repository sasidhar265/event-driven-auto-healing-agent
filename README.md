# Event-Driven Auto-Healing Suggestion Agent Runtime

Python 3.12/PostgreSQL reference implementation for governed enterprise remediation suggestions. It proposes changes; it intentionally does not execute production changes.

For a detailed explanation of the architecture, runtime flow, agents, policies,
API endpoints, database model, security, examples, limitations, and recommended
improvements, see [the complete project guide](documentation/README.md).
For moving the application to another machine or mapping existing PostgreSQL
tables, see [the portability and integration guide](documentation/PORTABILITY.md).
For database administration, reporting views, and the prepared query workbook,
see [the pgAdmin 4 guide](documentation/PGADMIN.md).

## Runtime flow

`Enterprise event -> HTTP or Kafka CloudEvent ingestion -> PostgreSQL event + outbox -> worker -> knowledge + failure router -> selected specialist agent -> policy + confidence gate -> suggestion API + audit log`

The failure router uses explicit categories, structured fields, and weighted
signals to select the relevant UI, API, logic, functional, test-data, database,
infrastructure, dependency, security, or performance specialist. Ambiguous
failures are routed to evidence collection instead of a guessed code change.

Confidence below `0.60` is suppressed, `0.60–0.79` requires review, and `0.80+` is ready for delivery. Tenant policies can block agent types, require human review by severity, and adjust confidence. All rows and queries are tenant scoped.

Set `AI_PROVIDER=enterprise`, `AI_ENDPOINT` and optionally `AI_API_KEY` to enrich candidates through an approved AI gateway. The gateway cannot set delivery status or bypass policy; deterministic mode is the default.

## Run

```bash
cp .env.example .env
make setup
make postgres-app-setup
make migrate
```

Start the API and worker in separate terminals:

```bash
make api
```

```bash
make worker
```

OpenAPI is at `http://127.0.0.1:8000/docs`. Requests require `X-API-Key`, `X-Tenant-Id`, and optionally `X-Actor`.

The demonstration console is at `http://localhost:8000/ui/`. It includes ten
interactive application and platform failure scenarios and shows their real
routing, agent suggestion, confidence, policy, and audit results.

### Run against local PostgreSQL

```bash
make postgres-app-setup
make migrate
make api
```

Run the worker in a second terminal:

```bash
make worker
```

The local `.env` connection is:

```text
postgresql+asyncpg://healing:healing@127.0.0.1:5432/healing
```

Open `http://127.0.0.1:8000/ui/`. UI requests persist events and outbox work in
PostgreSQL; the worker reads that outbox, writes suggestions and audit records,
and the UI reads those results back through the tenant-scoped API.

### Git workflow

Local configuration and generated files are excluded through `.gitignore`.
Commit source code, migrations, tests, scripts, examples, and documentation;
do not commit `.env`, `.venv`, Python caches, coverage output, or log files.

```bash
git status
git add app migrations tests scripts documentation README.md Makefile pyproject.toml
git commit -m "Describe the change"
```

```bash
curl -X POST http://localhost:8000/v1/events \
  -H 'Content-Type: application/json' -H 'X-API-Key: change-me' \
  -H 'X-Tenant-Id: acme' -H 'X-Actor: monitoring' \
  -d '{"external_id":"inc-42","event_type":"api.timeout","source":"apm","severity":"error","correlation_key":"orders-api","payload":{"endpoint":"/orders","timeout_ms":5000}}'
```

Use `POST /v1/knowledge` for runbooks, `POST /v1/policies` for governance, `GET /v1/suggestions?event_id=...` for results, and `POST /v1/suggestions/{id}/decision` for a human decision. `GET /v1/audit` provides the tenant audit trail.

Human decisions are stored in `suggestion_decisions` and
`remediation_references`. Accepted remediations are automatically retrieved as
evidence for similar future failures; rejected suggestions remain recorded but
are excluded from positive reference retrieval. Inspect them through
`GET /v1/references` or the pgAdmin `art_reporting.reference_library` view.

## Direct event-system integration

ART accepts CloudEvents 1.0 through `POST /v1/events/cloudevents` or directly
from a Kafka event backbone. Kafka messages may use structured or binary
CloudEvents mode and must provide the `tenantid` extension. Start the optional
consumer against an existing locally reachable Kafka-compatible backbone with:

```bash
make backbone
```

The consumer reads `enterprise.failures` by default, commits offsets only after
database ingestion, and publishes invalid messages to
`enterprise.failures.dead-letter`. Replayed messages are safe because event
ingestion is idempotent per tenant and CloudEvent ID.

Register a result consumer with `POST /v1/subscriptions`; every
policy-approved `suggestion.ready` result is pushed back as a structured
CloudEvent. Delivery uses exponential retries, a dead-letter state, manual retry
through `POST /v1/deliveries/{id}/retry`, and status visibility through
`GET /v1/deliveries`.

Every callback includes `X-ART-Delivery` and `X-ART-Signature-256: sha256=<HMAC>`. Consumers must calculate HMAC-SHA256 over the exact request body using the subscription secret, compare it in constant time, and deduplicate on the CloudEvent `id` or delivery header.

For UI test failures, include `failed_locator`, `dom_candidates`, `test_file`, and `test_name` in CloudEvent `data`. The XPath investigator prefers stable test IDs, supplies validation and rollback steps, and abstains or requests DOM evidence when a safe fix cannot be established.

Example policy rules:

```json
{"human_review_severities":["critical"],"blocked_agent_types":["test_data"],"confidence_adjustments":{"api":0.05}}
```

## Enterprise extension points

- Add another inbound adapter for Pulsar or a managed cloud event bus using the shared ingestion service.
- Implement additional `Agent` adapters or an approved AI service behind the same candidate contract.
- Replace API-key authentication with OIDC/JWT at the gateway; preserve tenant and actor claims.
- Export audit data to the enterprise SIEM and use PostgreSQL row-level security for defence in depth.
- Add pgvector for semantic knowledge retrieval when embeddings are approved.

The service separates suggestions from execution so change-management, approval, rollback, and deployment systems remain authoritative.
