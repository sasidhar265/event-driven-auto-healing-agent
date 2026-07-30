# Event-Driven Auto-Healing Suggestion Agent Runtime

## 1. Project overview

This project is a reference implementation of a governed, event-driven
remediation suggestion platform.

It receives operational incidents, application errors, or automated test
failures and analyzes them with a collection of specialist agents. The agents
produce structured suggestions describing how a problem might be fixed. Before
a suggestion can be delivered, the runtime applies confidence thresholds and
tenant-specific governance policies.

Despite the name "auto-healing," the current runtime does **not** execute
changes in production. It deliberately separates diagnosis and recommendation
from deployment and execution.

The project is therefore best understood as:

> An intelligent and governed recommendation layer between monitoring systems
> and enterprise change-management or remediation systems.

Its responsibilities include:

- Receiving incidents and CloudEvents.
- Persisting events reliably.
- Finding relevant internal knowledge or runbooks.
- Selecting specialist agents based on event content.
- Generating structured remediation candidates.
- Optionally enriching candidates through an approved AI gateway.
- Calculating confidence scores.
- Applying organizational policies.
- Suppressing unsafe or weak suggestions.
- Requiring review when appropriate.
- Delivering ready suggestions through signed webhooks.
- Recording an audit trail of significant actions.

## 2. The main business problem

Enterprise systems produce many alerts:

- An API starts timing out.
- A gateway returns errors.
- A UI test cannot find an element.
- Application code throws a null-related exception.
- A business workflow fails.
- Test fixtures become invalid.

Monitoring systems can report these failures, but they do not always explain
what should change. Fully autonomous remediation is also risky because a system
could execute an incorrect change without approval.

This runtime provides a controlled middle ground:

1. An external system reports a problem.
2. The runtime analyzes the problem.
3. It proposes one or more possible remediations.
4. Governance rules determine whether each suggestion is suppressed, sent for
   review, or marked ready.
5. Ready suggestions can be delivered to another authorized system.
6. The authorized downstream system or a human remains responsible for making
   the real change.

## 3. High-level architecture

```text
 Monitoring, APM, CI, test, or event system
                     |
                     | Incident event / CloudEvent 1.0
                     v
              FastAPI ingestion API
                     |
                     | One database transaction
                     v
        PostgreSQL event + outbox + audit log
                     |
                     | Polling
                     v
             Background worker
                     |
          +----------+-----------+
          |                      |
          v                      v
   Knowledge retrieval     Specialist agents
          |                      |
          +----------+-----------+
                     |
                     v
        Optional enterprise AI enrichment
                     |
                     v
          Policy and confidence gate
                     |
       +-------------+-------------+
       |             |             |
       v             v             v
   Suppressed      Review         Ready
   below 0.60     0.60-0.79      0.80+
                                   |
                                   v
                      Signed CloudEvent webhook
                                   |
                                   v
                   Change-management/remediation system
```

## 4. Important safety boundary

The runtime creates suggestions only.

It does not:

- Edit application source code.
- Commit changes to a repository.
- Deploy an application.
- Restart production services.
- Modify infrastructure.
- Change a database.
- Run a remediation script.
- Approve its own production change.

This boundary allows an organization to keep its existing approval, testing,
deployment, rollback, and change-management systems authoritative.

## 5. Technology stack

| Component | Technology |
|---|---|
| Programming language | Python 3.12 |
| REST API | FastAPI |
| Validation | Pydantic |
| Database | PostgreSQL 16 |
| Database access | Async SQLAlchemy and asyncpg |
| Schema migrations | Alembic |
| HTTP client | HTTPX |
| Event backbone | Kafka-compatible broker through aiokafka |
| Logging dependency | structlog |
| Packaging | Hatchling |
| Local orchestration | Make and Python virtual environment |
| Testing | Pytest and pytest-asyncio |

## 6. Repository structure

```text
.
├── app/
│   ├── api.py          # REST endpoints and event persistence
│   ├── config.py       # Environment-based configuration
│   ├── db.py           # Async database engine and sessions
│   ├── main.py         # FastAPI application entry point
│   ├── models.py       # SQLAlchemy database models
│   ├── processor.py    # Event-to-suggestion processing pipeline
│   ├── schemas.py      # API request and response validation
│   ├── security.py     # API key and tenant identity handling
│   ├── services.py     # Knowledge, agents, AI, and policy logic
│   ├── webhooks.py     # Signed webhook delivery and retry logic
│   └── worker.py       # Background polling worker
├── migrations/
│   └── versions/       # Alembic database migrations
├── tests/
│   └── test_agents.py  # Unit tests for agent behavior
├── Makefile            # Local setup, migration, API, and worker commands
├── pyproject.toml      # Python project and dependency definition
└── README.md           # Concise project introduction
```

## 7. Runtime components

### 7.1 FastAPI application

`app/main.py` creates the FastAPI application, registers the versioned API
router, and exposes a liveness endpoint:

```text
GET /health/live
```

Successful response:

```json
{
  "status": "ok"
}
```

Interactive OpenAPI documentation is available at:

```text
http://localhost:8000/docs
```

### 7.1.1 Demonstration console

The runtime serves a responsive browser console at:

```text
http://localhost:8000/ui/
```

The root URL redirects to this console. It uses the real tenant-scoped APIs and
contains:

- Runtime metrics and recent event activity.
- Ten ready-to-run application and platform failure domains.
- Editable event envelopes and diagnostic payloads.
- Live polling while the worker classifies and processes a failure.
- Routing evidence, selected specialist, confidence, and proposed changes.
- Suggestion acceptance and rejection.
- Knowledge/runbook creation.
- Governance policy creation.
- Tenant audit history with JSON export.
- Browser-local API connection settings.

The presets demonstrate the quality of evidence expected from CI or an event
backbone. They are editable, so operators can also paste representative
failure payloads from their own systems.

The console is a dependency-free HTML/CSS/JavaScript application under
`app/static`. FastAPI serves it from the same origin as the API, avoiding a
separate frontend deployment and cross-origin configuration.

### 7.2 Ingestion API

The API accepts either the project's native event representation or a
CloudEvents 1.0 representation.

Native endpoint:

```text
POST /v1/events
```

CloudEvents endpoint:

```text
POST /v1/events/cloudevents
```

When an event is accepted, the service performs these operations:

1. Checks whether the tenant has already submitted the same external event ID.
2. Returns the existing event if it is a duplicate.
3. Otherwise creates a new event row.
4. Creates an `event.received` outbox row.
5. Creates an audit record.
6. Commits all records in one database transaction.
7. Returns HTTP `202 Accepted`.

The unique combination of `tenant_id` and `external_id` provides ingestion
idempotency.

### 7.3 Kafka event-backbone consumer

`app/backbone.py` directly consumes failures from a Kafka-compatible event
backbone. It accepts:

- Structured CloudEvents, where the Kafka value is the complete CloudEvent.
- Binary-mode CloudEvents, where attributes use `ce_*` Kafka headers and the
  value contains the JSON `data`.

Every event must include a trusted `tenantid` CloudEvent extension or
`ce_tenantid` header. The optional `actor` extension identifies the publisher;
otherwise the audit actor is `event-backbone`.

Example structured event:

```json
{
  "specversion": "1.0",
  "id": "failure-8421",
  "source": "ci://checkout-ui-tests",
  "type": "ui.xpath.element_not_found",
  "tenantid": "acme",
  "actor": "ci-runner",
  "severity": "error",
  "correlationid": "build-762",
  "data": {
    "failure_category": "ui",
    "test_file": "tests/ui/test_checkout.py",
    "test_name": "test_submit_order",
    "failed_locator": {
      "strategy": "xpath",
      "value": "//button[@id='submit-order']"
    },
    "dom_candidates": [
      {
        "tag": "button",
        "attributes": {"data-testid": "submit-order"}
      }
    ]
  }
}
```

The consumer uses manual Kafka offset commits:

1. Decode and validate the CloudEvent.
2. Persist the event, outbox work, and audit record in PostgreSQL.
3. Commit the Kafka offset only after the database transaction succeeds.
4. Send malformed or tenantless events to the dead-letter topic.
5. Commit an invalid message only after dead-letter publication succeeds.

This provides at-least-once ingestion. Redelivery is safe because the database
uniqueness constraint treats `(tenant_id, CloudEvent id)` as idempotent.
Unexpected database or broker failures remain uncommitted and are retried after
consumer recovery.

The local consumer is optional and expects an existing Kafka-compatible broker:

```bash
make backbone
```

### 7.4 Transactional outbox

The `outbox` table separates API ingestion from background processing.

Instead of attempting analysis during the API request, the API stores an
outbox message in the same transaction as the event. The worker later polls
unpublished messages.

This pattern helps avoid a common failure:

```text
Event saved successfully
        +
Message to worker lost
```

Because the event and outbox record are committed together, a successfully
created event remains discoverable by the worker.

The implementation is currently a PostgreSQL polling outbox. It can later be
replaced or extended with Kafka, Pulsar, or a managed cloud event bus.

### 7.5 Background worker

`app/worker.py` continuously:

1. Selects up to 20 unpublished outbox records.
2. Locks them using `FOR UPDATE SKIP LOCKED`.
3. Processes `event.received` messages.
4. Marks processed outbox rows as published.
5. Attempts any webhook deliveries that are due.
6. Commits the transaction.
7. Sleeps when there is no immediate work.

`SKIP LOCKED` allows multiple workers to select different jobs instead of
processing the same locked job simultaneously.

## 8. Event lifecycle

An event can have the following states:

| Status | Meaning |
|---|---|
| `received` | The API stored the event and queued it for processing. |
| `processing` | A worker has started analysis. |
| `completed` | Analysis finished, even if no agent produced a suggestion. |
| `failed` | Processing encountered an error. |

The event also records:

- The tenant.
- External event ID.
- Event type.
- Source system.
- Severity.
- Correlation key.
- Arbitrary JSON payload.
- Processing attempt count.
- Error message, if present.
- Creation and processing timestamps.

Allowed severity values are:

- `info`
- `warning`
- `error`
- `critical`

## 9. Knowledge retrieval

Knowledge items represent internal material such as:

- Operational runbooks.
- Troubleshooting instructions.
- Engineering standards.
- Known-issue descriptions.
- UI locator conventions.
- Rollback procedures.

Knowledge can be created with:

```text
POST /v1/knowledge
```

Example:

```json
{
  "title": "Orders API timeout runbook",
  "content": "Check upstream latency and connection-pool saturation.",
  "tags": ["api", "orders", "timeout"],
  "metadata": {
    "owner": "orders-platform",
    "version": "2"
  }
}
```

The current retrieval implementation:

1. Converts the event type and payload to lowercase words.
2. Loads up to 50 knowledge items belonging to the same tenant.
3. Compares event words with words in each item's title and tags.
4. Assigns a score based on the number of overlapping words.
5. Returns the five highest-scoring matching items.

The returned evidence is stored with the suggestion and can increase agent
confidence.

This is deliberately simple lexical retrieval. It does not yet search the
knowledge content semantically. A future implementation could use embeddings
and pgvector once approved by the organization.

## 10. Specialist agents

Before an agent runs, the failure router scores the event as `ui`, `api`,
`logic`, `functional`, `test_data`, `database`, `infrastructure`, `dependency`,
`security`, or `performance`. It gives the greatest weight to an explicit
`failure_category`, followed by domain-specific structured evidence fields.
Free-text signals provide additional evidence.

The router stores an explainable result with each suggestion:

```json
{
  "category": "api",
  "confidence": 0.91,
  "matched_signals": [
    "field:endpoint",
    "field:status_code",
    "endpoint",
    "status_code"
  ],
  "alternatives": [
    {"category": "logic", "score": 1.5}
  ],
  "ambiguous": false
}
```

Only the selected specialist is invoked. XPath-specific UI failures take the
specialized XPath path instead of also producing a generic UI suggestion. If
the top categories are tied or too close, the router selects an investigation
agent that asks for missing evidence and keeps confidence below the review
threshold.

Agents implement a common conceptual contract:

```text
Input: event + retrieved evidence
Output: remediation candidate or no candidate
```

An agent should abstain by returning no candidate when the event is outside its
area of expertise.

Each candidate contains:

- Agent type.
- Suggestion title.
- Rationale.
- Proposed changes as structured JSON.
- Base confidence from 0.0 to 1.0.

### 10.1 General pattern agents

Most included agents match known signals in the event type and payload.

| Agent | Example signals | Proposed action |
|---|---|---|
| UI | `ui`, `frontend`, `render`, `browser`, `layout` | `propose_ui_patch` |
| API | `api`, `http`, `timeout`, `endpoint`, `gateway` | `propose_api_change` |
| Logic | `exception`, `null`, `logic`, `calculation`, `state` | `propose_logic_patch` |
| Functional | `workflow`, `business`, `functional`, `process` | `propose_workflow_change` |
| Test data | `fixture`, `test data`, `seed`, `dataset`, `mock` | `propose_test_data_change` |
| Database | `postgres`, `SQL`, `deadlock`, `migration`, pool | `propose_database_change` |
| Infrastructure | Kubernetes, OOM, CPU, memory, capacity | `propose_infrastructure_change` |
| Dependency | upstream, DNS, unavailable, circuit breaker | `propose_dependency_change` |
| Security | authorization, certificate, permission, CVE | `propose_security_change` |
| Performance | latency, p95/p99, profile, bottleneck | `propose_performance_change` |

The same event may match more than one agent. Each matching agent can generate
its own suggestion.

The general confidence formula begins at `0.62` and adds:

- `0.06` for every matched signal.
- Up to `0.12` based on matching knowledge items.
- `0.08` for critical severity.
- `0.05` for error severity.
- `0.02` for warning severity.

The result is capped at `0.97` before policy adjustments.

### 10.2 XPath investigation agent

The XPath investigation agent handles UI automation failures containing signals
such as:

- `xpath`
- `nosuchelement`
- `element_not_found`

For useful analysis, an event can include:

```json
{
  "failed_locator": {
    "strategy": "xpath",
    "value": "//button[@id='submit-order']"
  },
  "dom_candidates": [
    {
      "tag": "button",
      "text": "Submit order",
      "attributes": {
        "data-testid": "submit-order"
      }
    }
  ],
  "test_file": "tests/ui/test_checkout.py",
  "test_name": "test_submit_order"
}
```

The agent ranks possible replacement locators:

| Priority | Attribute | Resulting locator |
|---|---|---|
| 1 | `data-testid` | CSS attribute selector |
| 2 | `id` | ID locator |
| 3 | `name` | CSS attribute selector |
| 4 | `aria-label` | CSS attribute selector |

Stable test IDs receive the highest score because they are normally less
dependent on DOM layout than an absolute or deeply nested XPath.

The proposed change includes:

- The target test file.
- The test name.
- The obsolete locator.
- The recommended locator.
- The matched DOM element.
- Validation instructions.
- A rollback instruction.

Example recommendation:

```json
{
  "action": "replace_test_locator",
  "target_file": "tests/ui/test_checkout.py",
  "test_name": "test_submit_order",
  "current_locator": {
    "strategy": "xpath",
    "value": "//button[@id='submit-order']"
  },
  "recommended_locator": {
    "strategy": "css-selector",
    "value": "[data-testid=\"submit-order\"]"
  },
  "validation": [
    "assert locator resolves exactly one element",
    "run failed test",
    "run owning UI regression suite"
  ],
  "rollback": "restore the previous test locator"
}
```

If the event does not contain DOM candidates, the agent avoids inventing a
replacement. It recommends collecting:

- A sanitized DOM snapshot near the target.
- A screenshot.
- Successful locator history.

That evidence-collection recommendation begins with confidence `0.58`, which is
below the default review threshold.

## 11. Optional AI enrichment

The default provider is `deterministic`, so no external AI call is required.

An approved enterprise AI gateway can be configured using:

```text
AI_PROVIDER=enterprise
AI_ENDPOINT=https://approved-ai-gateway.example/analyze
AI_API_KEY=...
```

The runtime sends the gateway:

- Event type, severity, and payload.
- The deterministic candidate.
- Retrieved evidence.

The gateway may enrich:

- The explanation.
- Proposed change details.
- Candidate confidence.

The gateway cannot provide or override the final delivery status. After AI
enrichment, the local policy engine still decides whether the suggestion is
suppressed, requires review, or is ready.

This prevents an external model from bypassing organizational governance.

## 12. Confidence and suggestion lifecycle

The default confidence thresholds are:

| Final confidence | Default outcome |
|---|---|
| Below `0.60` | `suppressed` |
| `0.60` to below `0.80` | `review` |
| `0.80` and above | `ready` |

Suggestion statuses are:

| Status | Meaning |
|---|---|
| `suppressed` | Too uncertain or blocked by policy; not delivered. |
| `review` | Requires a human decision before being treated as approved. |
| `ready` | Passed the confidence and policy gate and can be delivered. |
| `accepted` | A human accepted the recommendation. |
| `rejected` | A human rejected the recommendation. |

The thresholds can be changed through environment variables:

```text
CONFIDENCE_REVIEW_THRESHOLD=0.60
CONFIDENCE_DELIVERY_THRESHOLD=0.80
```

## 13. Policy engine

Policies belong to a tenant and are created with:

```text
POST /v1/policies
```

Example:

```json
{
  "name": "Production remediation policy",
  "rules": {
    "human_review_severities": ["critical"],
    "blocked_agent_types": ["test_data"],
    "confidence_adjustments": {
      "api": 0.05,
      "ui": -0.03
    }
  }
}
```

The supported rule behavior is:

### Blocked agent types

If the candidate's agent type is listed in `blocked_agent_types`, the policy
adds a violation and the suggestion becomes `suppressed`.

### Human-review severities

If the event severity is listed in `human_review_severities`, the policy records
that approval is required. A candidate with enough confidence for review will
become `review` rather than `ready`.

### Confidence adjustments

Policies may increase or decrease confidence for a given agent type. The final
result is clamped to the range `0.0` through `1.0`.

If multiple active policies exist, their violations, review requirements, and
confidence adjustments are accumulated.

## 14. Suggestion creation

For every candidate returned by an agent, the processor:

1. Optionally enriches it through the enterprise AI service.
2. Evaluates it using active tenant policies.
3. Calculates final confidence.
4. Stores a suggestion.
5. Stores the supporting evidence.
6. Stores the policy result.
7. Writes a `suggestion.created` audit entry.
8. Creates webhook delivery records if the status is `ready`.

The stored policy result contains:

```json
{
  "violations": [],
  "approvals": [],
  "policies": 1
}
```

## 15. Human decisions

A reviewer can accept or reject a suggestion:

```text
POST /v1/suggestions/{suggestion_id}/decision
```

Example request:

```json
{
  "decision": "accepted",
  "reason": "Validated in staging and approved by the service owner."
}
```

Or:

```json
{
  "decision": "rejected",
  "reason": "The timeout originates upstream; changing this API is not appropriate."
}
```

The decision changes the suggestion status and creates an audit entry containing
the actor and reason.

Acceptance records approval but still does not execute the proposed change.

## 16. Webhook subscriptions

Downstream systems register callback endpoints with:

```text
POST /v1/subscriptions
```

Example:

```json
{
  "name": "Change-management intake",
  "callback_url": "https://changes.example.com/hooks/art",
  "event_types": ["suggestion.ready"],
  "secret": "a-long-subscription-specific-secret"
}
```

Subscriptions can listen for:

- `suggestion.ready`
- `*` for all supported outbound types

The current runtime creates outbound deliveries only for ready suggestions.

Subscriptions can be listed:

```text
GET /v1/subscriptions
```

They can be deactivated:

```text
DELETE /v1/subscriptions/{subscription_id}
```

The delete endpoint performs a soft deactivation rather than removing the
database row.

## 17. Outbound CloudEvents

A ready suggestion is delivered as a structured CloudEvent 1.0 message.

Simplified example:

```json
{
  "specversion": "1.0",
  "id": "suggestion-uuid",
  "source": "/auto-healing-agent-runtime",
  "type": "suggestion.ready",
  "subject": "event-uuid",
  "time": "2026-07-30T10:00:00+00:00",
  "datacontenttype": "application/json",
  "tenantid": "acme",
  "data": {
    "suggestion_id": "suggestion-uuid",
    "event_id": "event-uuid",
    "agent_type": "api",
    "title": "Api remediation for api.timeout",
    "rationale": "Matched signals: timeout, api.",
    "proposed_changes": {},
    "evidence": [],
    "confidence": 0.85,
    "policy_result": {
      "violations": [],
      "approvals": [],
      "policies": 1
    },
    "status": "ready"
  }
}
```

## 18. Webhook signing and consumer verification

Every webhook request includes:

```text
Content-Type: application/cloudevents+json
Ce-Specversion: 1.0
Ce-Type: suggestion.ready
Ce-Id: <suggestion-id>
X-ART-Delivery: <delivery-id>
X-ART-Signature-256: sha256=<hex-digest>
```

The signature is calculated as:

```text
HMAC-SHA256(subscription secret, exact HTTP request body)
```

A consumer should:

1. Read the raw request body without changing it.
2. Calculate HMAC-SHA256 using the configured secret.
3. Compare the calculated value with the received signature using a
   constant-time comparison.
4. Reject the request if the values do not match.
5. Deduplicate requests using the CloudEvent `id` or `X-ART-Delivery`.

If a subscription does not provide its own secret, the runtime uses the global
`WEBHOOK_SIGNING_SECRET`.

## 19. Delivery retry and dead-letter behavior

Webhook delivery can have these states:

| Status | Meaning |
|---|---|
| `pending` | Waiting for the first attempt. |
| `retry` | A previous attempt failed and another is scheduled. |
| `delivered` | The callback returned a successful HTTP response. |
| `dead_letter` | The maximum number of attempts was reached. |
| `cancelled` | The subscription or suggestion was no longer available. |

Failed deliveries use exponential backoff:

```text
delay = min(2 ^ attempt_number, 3600 seconds)
```

The maximum number of attempts defaults to eight:

```text
WEBHOOK_MAX_ATTEMPTS=8
```

Delivery status can be inspected:

```text
GET /v1/deliveries
GET /v1/deliveries?suggestion_id=<uuid>
```

A dead-lettered or failed delivery can be manually queued again:

```text
POST /v1/deliveries/{delivery_id}/retry
```

## 20. Authentication and tenant isolation

Every `/v1` request requires:

```text
X-API-Key: <configured API key>
X-Tenant-Id: <tenant identifier>
X-Actor: <optional actor name>
```

If `X-Actor` is omitted, it defaults to `api`.

Example:

```bash
curl http://localhost:8000/v1/audit \
  -H 'X-API-Key: change-me' \
  -H 'X-Tenant-Id: acme' \
  -H 'X-Actor: platform-operator'
```

Tenant IDs scope:

- Events.
- Suggestions.
- Policies.
- Knowledge items.
- Webhook subscriptions.
- Webhook deliveries.
- Audit records.

This provides application-level tenant isolation.

For a real enterprise deployment, the shared API key and caller-provided tenant
header should be replaced by OIDC or JWT authentication. Tenant and actor
identities should come from verified claims rather than arbitrary headers.
PostgreSQL row-level security can provide additional defense in depth.

## 21. Audit trail

Audit records contain:

- Tenant ID.
- Actor.
- Action.
- Resource type.
- Resource ID.
- JSON details.
- Timestamp.

Examples of audited actions include:

- `event.received`
- `event.processed`
- `suggestion.created`
- `suggestion.accepted`
- `suggestion.rejected`
- `subscription.created`
- `subscription.deactivated`
- `webhook.delivered`
- `webhook.retry`
- `webhook.dead_letter`
- `webhook.retry_requested`

Audit records can be retrieved with:

```text
GET /v1/audit
GET /v1/audit?limit=200
```

The maximum permitted limit is 500 records per request.

An enterprise deployment could additionally export these records to a SIEM.

## 22. Database model

### `events`

Stores incoming incidents and their processing state.

Important constraint:

```text
UNIQUE (tenant_id, external_id)
```

### `suggestions`

Stores agent recommendations, evidence, confidence, policy results, and status.
Each suggestion belongs to one event.

### `policies`

Stores tenant-specific governance rules and versions.

### `knowledge_items`

Stores internal reference material and tags used during evidence retrieval.

### `audit_logs`

Stores the immutable-style application audit history.

### `outbox`

Stores work that needs to be processed asynchronously.

### `webhook_subscriptions`

Stores tenant callback registrations and signing secrets.

### `webhook_deliveries`

Stores each suggestion/subscription delivery and its retry state.

Important constraint:

```text
UNIQUE (subscription_id, suggestion_id)
```

This prevents duplicate delivery records for the same ready suggestion and
subscription.

### `suggestion_decisions`

Stores the latest human decision, reason, actor, and decision timestamp for each
suggestion. This keeps review feedback queryable without extracting it from
audit JSON.

### `remediation_references`

Stores governed remediation history derived from human decisions. Accepted
references are active positive evidence for similar future failures. Rejected
references remain available as negative feedback but are not used as positive
evidence.

The table tracks:

- Event type and severity.
- Stable event/payload fingerprint.
- Specialist and proposed change.
- Original evidence and confidence.
- Human outcome and reason.
- Active status.
- Future reuse count and last-used timestamp.

### `integration_ingestions` and `integration_publications`

Track which configured external PostgreSQL bridge supplied an event and where
its ready suggestion was published.

## 23. API reference summary

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health/live` | Liveness check |
| GET | `/` | Redirect to the demonstration console |
| GET | `/ui/` | Demonstration console |
| GET | `/v1/overview` | Dashboard totals and recent events |
| POST | `/v1/events` | Ingest a native event |
| POST | `/v1/events/cloudevents` | Ingest CloudEvents 1.0 |
| GET | `/v1/events` | List recent tenant events |
| GET | `/v1/events/{event_id}` | Retrieve an event |
| GET | `/v1/suggestions` | List recent tenant suggestions |
| GET | `/v1/suggestions?event_id={id}` | List suggestions for one event |
| POST | `/v1/suggestions/{id}/decision` | Accept or reject a suggestion |
| GET | `/v1/references` | List active reusable remediation references |
| GET | `/v1/references?active_only=false` | List accepted and rejected references |
| POST | `/v1/policies` | Create a tenant policy |
| GET | `/v1/policies` | List tenant policies |
| POST | `/v1/knowledge` | Create a knowledge item |
| GET | `/v1/knowledge` | List tenant knowledge items |
| POST | `/v1/subscriptions` | Create a webhook subscription |
| GET | `/v1/subscriptions` | List webhook subscriptions |
| DELETE | `/v1/subscriptions/{id}` | Deactivate a subscription |
| GET | `/v1/deliveries` | List webhook deliveries |
| POST | `/v1/deliveries/{id}/retry` | Retry a delivery |
| GET | `/v1/audit` | Read the tenant audit trail |

## 24. Complete example workflow

### Local PostgreSQL interaction mode

The application runs entirely as local processes against Postgres.app. The
configured flow is:

```text
Browser UI
   -> FastAPI on 127.0.0.1:8000
   -> Postgres.app on 127.0.0.1:5432
      -> events + outbox + audit_logs
   -> local background worker
      -> suggestions + audit_logs + outbox completion
   -> FastAPI queries
   -> Browser UI refresh
```

Local database details:

```text
Database: healing
Role:     healing
Host:     127.0.0.1
Port:     5432
```

Prepare the virtual environment and Postgres.app database:

```bash
make setup
make postgres-app-setup
```

Apply migrations:

```bash
make migrate
```

Run the API and worker in separate terminals:

```bash
make api
```

```bash
make worker
```

Inspect stored interactions:

```bash
PGPASSWORD=healing /Applications/Postgres.app/Contents/Versions/latest/bin/psql \
  -h 127.0.0.1 -U healing -d healing
```

Useful queries:

```sql
SELECT external_id, event_type, status, attempts FROM events
ORDER BY created_at DESC;

SELECT topic, aggregate_id, published_at FROM outbox
ORDER BY available_at DESC;

SELECT agent_type, status, confidence,
       proposed_changes->'routing'->>'category' AS routed_to
FROM suggestions
ORDER BY created_at DESC;

SELECT actor, action, resource_type, created_at FROM audit_logs
ORDER BY created_at DESC;
```

### Step 1: Start the runtime

Create the environment file:

```bash
cp .env.example .env
```

Create the virtual environment, prepare PostgreSQL, and run migrations:

```bash
make setup
make postgres-app-setup
make migrate
```

Start the application processes in separate terminals:

```bash
make api
```

```bash
make worker
```

This starts:

1. The FastAPI service on port 8000.
2. The background worker that processes events and webhook deliveries.

### Step 2: Add knowledge

```bash
curl -X POST http://localhost:8000/v1/knowledge \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: change-me' \
  -H 'X-Tenant-Id: acme' \
  -H 'X-Actor: platform-team' \
  -d '{
    "title": "Orders API timeout runbook",
    "content": "Inspect upstream latency and connection pool saturation.",
    "tags": ["api", "orders", "timeout"],
    "metadata": {"owner": "orders-platform"}
  }'
```

### Step 3: Add a policy

```bash
curl -X POST http://localhost:8000/v1/policies \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: change-me' \
  -H 'X-Tenant-Id: acme' \
  -H 'X-Actor: governance-admin' \
  -d '{
    "name": "Production policy",
    "rules": {
      "human_review_severities": ["critical"],
      "blocked_agent_types": ["test_data"],
      "confidence_adjustments": {"api": 0.05}
    }
  }'
```

### Step 4: Register a result callback

```bash
curl -X POST http://localhost:8000/v1/subscriptions \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: change-me' \
  -H 'X-Tenant-Id: acme' \
  -H 'X-Actor: integration-admin' \
  -d '{
    "name": "Change system",
    "callback_url": "https://changes.example.com/hooks/art",
    "event_types": ["suggestion.ready"],
    "secret": "replace-with-a-strong-shared-secret"
  }'
```

### Step 5: Submit an incident

```bash
curl -X POST http://localhost:8000/v1/events \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: change-me' \
  -H 'X-Tenant-Id: acme' \
  -H 'X-Actor: monitoring' \
  -d '{
    "external_id": "inc-42",
    "event_type": "api.timeout",
    "source": "apm",
    "severity": "error",
    "correlation_key": "orders-api",
    "payload": {
      "endpoint": "/orders",
      "timeout_ms": 5000
    }
  }'
```

### Step 6: Retrieve the result

Use the event UUID returned by the ingestion call:

```bash
curl 'http://localhost:8000/v1/suggestions?event_id=<event-uuid>' \
  -H 'X-API-Key: change-me' \
  -H 'X-Tenant-Id: acme'
```

### Step 7: Review the audit history

```bash
curl http://localhost:8000/v1/audit \
  -H 'X-API-Key: change-me' \
  -H 'X-Tenant-Id: acme'
```

## 25. Configuration

The primary settings are:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | Local PostgreSQL URL | Async SQLAlchemy database connection |
| `API_KEY` | `change-me` | Shared API credential |
| `WORKER_POLL_SECONDS` | `1.0` | Worker sleep interval when idle |
| `CONFIDENCE_REVIEW_THRESHOLD` | `0.60` | Minimum confidence for review |
| `CONFIDENCE_DELIVERY_THRESHOLD` | `0.80` | Minimum confidence for ready delivery |
| `AI_PROVIDER` | `deterministic` | Candidate enrichment provider |
| `AI_ENDPOINT` | unset | Approved AI gateway URL |
| `AI_API_KEY` | unset | AI gateway credential |
| `WEBHOOK_SIGNING_SECRET` | development value | Default HMAC secret |
| `WEBHOOK_MAX_ATTEMPTS` | `8` | Maximum delivery attempts |
| `WEBHOOK_TIMEOUT_SECONDS` | `10` | Outbound webhook timeout |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker addresses |
| `KAFKA_INPUT_TOPIC` | `enterprise.failures` | Incoming failure topic |
| `KAFKA_DEAD_LETTER_TOPIC` | `enterprise.failures.dead-letter` | Invalid-event topic |
| `KAFKA_CONSUMER_GROUP` | `auto-healing-agent-runtime` | Consumer group |
| `KAFKA_AUTO_OFFSET_RESET` | `earliest` | Start policy without an offset |
| `KAFKA_SECURITY_PROTOCOL` | `PLAINTEXT` | Kafka transport/auth protocol |
| `KAFKA_SASL_MECHANISM` | unset | Optional SASL mechanism |
| `KAFKA_SASL_USERNAME` | unset | Optional SASL username |
| `KAFKA_SASL_PASSWORD` | unset | Optional SASL password |

Development defaults such as `change-me` and `change-webhook-secret` must be
replaced before using the runtime outside a local environment.

## 26. Current tests

The included unit tests verify that:

1. The API agent recognizes an API timeout and proposes an API change.
2. All agents abstain for an unrelated capacity event.
3. The XPath agent prefers a unique `data-testid` locator.
4. UI XPath failures route only to the XPath specialist.
5. Structured API failures route to an API file/method plan.
6. Ambiguous failures route to evidence collection.
7. Structured and binary Kafka CloudEvents are decoded.
8. Tenantless backbone events are rejected.
9. Dead-letter records preserve arbitrary original message bytes.

These tests validate useful agent behavior, but they do not yet cover:

- API authentication.
- Event ingestion idempotency.
- Live Kafka broker consumption and offset recovery.
- Database persistence.
- Worker processing.
- Policy combinations.
- AI gateway failures.
- Webhook signing.
- Retry and dead-letter behavior.
- Tenant isolation.
- Human decisions.
- Full end-to-end operation.

## 27. Current limitations

### Suggestions are not executable patches

General agents return structured actions such as `propose_api_change`; they do
not create a real Git diff or infrastructure plan.

### Classification cannot prove root cause

Routing now combines explicit categories, structured evidence, and weighted
signals instead of broadcasting every event to every agent. This identifies the
appropriate specialist more reliably, but classification alone cannot prove a
root cause. Correct file-level changes still depend on accurate stack traces,
source/test locations, logs, traces, expected/actual values, and validation.

### Event correlation is not implemented

The event model stores and indexes `correlation_key`, but the processor does not
currently group multiple events into a shared incident or use historical
correlated events during analysis.

### Knowledge search is lexical

Only title and tag word overlap is scored. Knowledge content is returned as
evidence but is not semantically searched.

### No user interface

The runtime provides REST APIs and OpenAPI documentation, but no operator
dashboard.

### Authentication is suitable mainly for a reference implementation

A shared API key and trusted tenant header are less secure than verified
identity-provider claims.

### Policy schema is flexible but not formally typed

Policy rules are stored as arbitrary JSON. Misspelled or unsupported policy
fields may be silently ineffective.

### Event failure recovery is limited

The event model records failure information, but there is no dedicated API for
retrying a failed event.

### Delivery occurs only for `ready`

Suggestions requiring review are not automatically delivered when later
accepted. The current decision endpoint records the decision, but it does not
create a new webhook delivery.

### Observability is incomplete

The dependencies include structured logging support, but the current code does
not yet provide comprehensive metrics, traces, dashboards, or alerting.

## 28. Recommended production improvements

### Security

- Replace API keys with OIDC/JWT.
- Derive tenant and actor from verified claims.
- Add role-based authorization.
- Store secrets in a secret manager.
- Require HTTPS for callbacks in production.
- Restrict callback destinations to prevent server-side request forgery.
- Add PostgreSQL row-level security.
- Encrypt sensitive event payload fields.

### Reliability

- Add event retry and poison-message handling.
- Add explicit transaction rollback and recovery tests.
- Add worker graceful shutdown.
- Add delivery idempotency documentation and tests.
- Add database connection and migration readiness checks.
- Move to Kafka, Pulsar, or a managed queue if throughput requires it.

### Agent quality

- Add typed contracts for every proposed action.
- Generate real patches in an isolated workspace.
- Add validation agents that critique candidates.
- Correlate current events with related historical incidents.
- Add semantic knowledge retrieval.
- Track whether accepted suggestions resolved the incident.
- Use resolution outcomes to calibrate confidence.

### Governance

- Validate policy JSON with a formal schema.
- Add policy priority and conflict-resolution rules.
- Add policy effective dates and approval workflows.
- Record immutable policy versions used for each decision.
- Separate "ready for delivery" from "approved for execution."

### Observability

- Add structured logs throughout the pipeline.
- Export Prometheus metrics.
- Add OpenTelemetry traces.
- Measure processing latency and agent abstention rates.
- Alert on outbox backlog and dead-letter deliveries.

### Testing

- Add database integration tests with PostgreSQL.
- Add API contract tests.
- Add tenant-isolation tests.
- Test concurrent workers.
- Test webhook signatures byte-for-byte.
- Test retry timing and maximum attempts.
- Add full local PostgreSQL end-to-end tests.

## 29. How to interpret the term "auto-healing"

In this project, auto-healing describes the automated analysis and suggestion
pipeline, not automatic production execution.

The current maturity level is:

```text
Automatic detection input
        -> automatic analysis
        -> automatic recommendation
        -> automatic governance classification
        -> controlled delivery
        -> human or external system executes the change
```

A future system could add automatic execution for a small set of pre-approved,
low-risk actions. Such execution should require:

- A strictly typed remediation.
- Strong policy approval.
- Pre-change validation.
- A tested rollback.
- Blast-radius controls.
- Time and environment restrictions.
- Complete audit logging.
- Post-change health verification.

That execution layer is intentionally outside the current implementation.

## 30. Summary

This runtime safely converts enterprise events into governed remediation
suggestions.

Its key strengths are:

- Asynchronous event processing.
- Reliable database-backed ingestion.
- Specialist agent separation.
- Agent abstention when evidence is insufficient.
- Confidence-based gating.
- Tenant-specific governance.
- Optional enterprise AI enrichment with local policy authority.
- Signed webhook delivery with retries.
- Tenant-scoped data access.
- A detailed audit trail.

Its most important design decision is that suggestions and execution remain
separate. The runtime can help engineers and automation systems understand what
might fix an incident while leaving approval, deployment, and rollback under
enterprise control.
