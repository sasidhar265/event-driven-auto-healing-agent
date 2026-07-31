# Event-Driven Auto-Healing Suggestion Agent Runtime

Python 3.12/PostgreSQL reference implementation for governed enterprise remediation suggestions. It proposes changes; it intentionally does not execute production changes.

## Start here

ART stands for **Auto-Healing Recommendation Tool** in this repository. An
application, automated test, monitoring platform, or event backbone reports a
failure. ART stores the incident, identifies its failure domain, selects a
specialist, gathers evidence, calculates confidence, applies governance, and
returns a proposed remediation. A person or an external change-management
system remains responsible for applying the change.

In plain language:

```text
Something fails
      ↓
ART receives and records the failure
      ↓
ART works out whether it is a UI, API, database, logic, or platform problem
      ↓
ART proposes a fix and explains its evidence
      ↓
Confidence and policy classify it as Suppressed, Review, or Ready
      ↓
An operator accepts or rejects the recommendation
```

The same records are visible in the browser and PostgreSQL. The UI is not
showing hard-coded incident results: it creates and retrieves them through the
API, and the API reads and writes PostgreSQL.

Choose the documentation path that matches what you need:

| Reader or goal | Start with |
|---|---|
| Non-technical overview | [Project walkthrough](documentation/PROJECT_WALKTHROUGH.md#1-what-this-project-does) |
| Pictures and flow diagrams | [ART visual guide](documentation/VISUAL_GUIDE.md) |
| Developer learning the code | [Code map](documentation/PROJECT_WALKTHROUGH.md#9-code-walkthrough) |
| File and method correlation | [Code and method reference](documentation/CODE_REFERENCE.md) |
| API or integration developer | [API guide](documentation/PROJECT_WALKTHROUGH.md#11-api-guide) |
| Database administrator | [pgAdmin 4 guide](documentation/PGADMIN.md) |
| Moving to another machine/environment | [Portability guide](documentation/PORTABILITY.md) |
| Maintaining routing and runtime configuration | [Configuration guide](documentation/CONFIGURATION.md) |
| Requirement traceability | [ART feedback implementation map](documentation/ART_FEEDBACK_IMPLEMENTATION.md) |
| Deep implementation reference | [Technical reference](documentation/README.md) |

## What you can do in the UI

The console at `http://127.0.0.1:8000/ui/` has four ART-focused areas:

| Screen | Purpose |
|---|---|
| Overview | See event totals, recent incidents, environment-filtered activity, and the live confidence Decision Model. |
| Incident intake | Submit structured UI, API, logic, database, security, performance, and other failures. |
| Suggestions | Read proposed remediations, confidence and evidence; accept or reject a suggestion. |
| Audit trail | Trace database-backed actions by environment, time range, correlation ID, and failure ID. |

Policy Governance and Knowledge/AI services are internal layers. They influence
classification and recommendations but are not exposed as primary ART screens.

For a detailed explanation of the architecture, data flow, terminology, UI,
APIs, PostgreSQL tables, code organization, testing, troubleshooting, and
maintenance, see the
[complete project walkthrough](documentation/PROJECT_WALKTHROUGH.md).
For moving the application to another machine or mapping existing PostgreSQL
tables, see [the portability and integration guide](documentation/PORTABILITY.md).
For database administration, reporting views, and the prepared query workbook,
see [the pgAdmin 4 guide](documentation/PGADMIN.md).
For the enterprise lifecycle requirements from `ART_Feedback.docx`, see the
[requirement-to-implementation map](documentation/ART_FEEDBACK_IMPLEMENTATION.md).

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
make db-setup
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

The pre-production operations console is at `http://localhost:8000/ui/`. It
provides ten operational incident profiles and shows their database-backed
routing, agent suggestion, confidence, policy, and audit results.

### API profiles

The default `operations` profile exposes only the endpoints used by the
operations console. Optional contracts remain available without expanding the
normal runtime surface:

| Profile | Start command | Exposed APIs |
|---|---|---|
| Operations | `make api` | ART incident intake, processing trace, suggestions, decisions, and audit |
| Integration | `make api-integration` | Operations plus CloudEvents, subscriptions, and deliveries |
| Admin | `make api-admin` | Operations plus internal KAI/governance management and detailed ART lifecycle administration |
| Full | `make api-full` | All operations, integration, internal-service, and ART lifecycle APIs |

Set `API_PROFILE` to `operations`, `integration`, `admin`, or `full` when
starting the service in another environment. API paths and typed schemas remain
unchanged whenever their profile is enabled.

### Run against PostgreSQL

```bash
make db-setup
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

`db-setup` uses the standard PostgreSQL command-line tools available on
`PATH`; it is not tied to Postgres.app. Set `POSTGRES_HOST`, `POSTGRES_PORT`,
`ART_ADMIN_USER`, and `ART_ADMIN_PASSWORD` when the server is not using the
local defaults. pgAdmin connects to this same database and is only used for
administration and reporting.

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

The ART UI uses `GET /v1/suggestions?event_id=...` for results,
`POST /v1/suggestions/{id}/decision` for a human decision, and `GET /v1/audit`
for the tenant audit trail. KAI knowledge, governance policy, and remediation
reference management are internal/admin APIs under `/v1/internal`.

Human decisions are stored in `suggestion_decisions` and
`remediation_references`. Accepted remediations are automatically retrieved as
evidence for similar future failures; rejected suggestions remain recorded but
are excluded from positive reference retrieval. Administrators can inspect
them through `GET /v1/internal/references` in the `admin` or `full` profile, or
through the pgAdmin `art_reporting.reference_library` view.

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

## Enterprise ART lifecycle API

The document-driven enterprise model is exposed under `/v1/art`. It includes
normalized failures, multi-agent runs and steps, explainability journals,
impact/dependency analysis, test selection, governed execution intents,
execution result references, self-heal proposals, outcome feedback, and
event inbox/outbox resources.

Every resource is tenant scoped and requires a correlation UUID and
environment. Use the generated OpenAPI documentation for complete request
schemas, or run the end-to-end verifier:

Start `make api-full`, then run `make verify-art`.
