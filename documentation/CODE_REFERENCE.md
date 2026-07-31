# Code and method reference

This guide maps each executable file to its responsibility and shows how the
important methods call one another. The normal runtime uses one PostgreSQL
database. pgAdmin is a database administration and reporting client; it does
not sit in the application's request path.

## 1. End-to-end correlation

```text
Browser or monitoring system
  -> app/main.py: create_application()
  -> app/security.py: principal()
  -> app/api.py: ingest_event()
  -> app/ingestion.py: persist_event()
  -> PostgreSQL: events + outbox + audit_logs
  -> app/worker.py: run()
  -> app/processor.py: process_event()
     -> KnowledgeService.search()
     -> routed_agents() / FailureRouter.classify()
     -> Agent.suggest()
     -> AIService.enrich()
     -> PolicyEngine.evaluate()
     -> _create_suggestion()
     -> LifecycleRecorder methods
  -> PostgreSQL: suggestions + audit + ART lifecycle records
  -> app/api.py: list_suggestions(), decide(), audit()
  -> app/static/app.js: render the result

pgAdmin -> the same PostgreSQL database (inspection/reporting only)
```

## 2. Application bootstrap and configuration

### `app/main.py`

Creates the FastAPI process and selects its exposed API surface.

- `lifespan()` disposes the shared SQLAlchemy engine during shutdown.
- `create_application(api_profile=None)` creates FastAPI, loads runtime rules,
  mounts routers for the selected profile, and serves the browser UI.
- `root()` redirects `/` to `/ui/`.
- `live()` checks PostgreSQL with `SELECT 1` and returns safe connection/status
  details without exposing the password.
- `app` is the ASGI application imported by Uvicorn.

### `app/config.py`

Defines environment-driven process settings.

- `Settings` maps `.env`/environment variables to validated Python fields.
  `database_url` is the direct application-to-PostgreSQL connection.
- `get_settings()` returns a cached `Settings` instance so configuration is
  parsed once per process.

### `app/db.py`

Owns the shared async SQLAlchemy engine and session factory.

- `engine` is created from `Settings.database_url`.
- `SessionLocal` creates transactional `AsyncSession` objects.
- `get_session()` yields a session to FastAPI endpoints and closes it after the
  request.

### `app/runtime_config.py` and `app/resources/runtime_rules.json`

The JSON file contains editable routing weights, specialist templates,
confidence rules, lifecycle limits, and delivery settings. The Python file
validates and exposes those rules.

- `RoutingScoreConfig`, `RoutingConfig`, `ConfidenceConfig`,
  `SpecialistConfig`, `XPathConfig`, `InvestigationConfig`, `AgentConfig`,
  `KnowledgeConfig`, `LifecycleConfig`, and `DeliveryConfig` validate sections
  of the JSON document.
- `categories_match()`, `validate_templates()`, and
  `specialist_categories_match_routing()` perform cross-field validation.
- `RuntimeRules` is the validated root configuration model.
- `get_runtime_rules()` reads and caches the configured JSON file.

## 3. Authentication and request schemas

### `app/security.py`

- `Principal` carries the authenticated `tenant_id` and `actor` through the
  service.
- `principal()` validates `X-API-Key`, requires `X-Tenant-Id`, reads the
  optional `X-Actor`, and returns a `Principal` FastAPI dependency.

### `app/schemas.py`

Defines the public API request/response contracts; these classes contain field
validation and serialization rather than business logic.

- `EventCreate` / `EventRead`: native incident intake and persisted response.
- `SuggestionRead`: suggestion returned to a caller.
- `DecisionCreate`: accept/reject request.
- `PolicyCreate` and `KnowledgeCreate`: internal administration requests.
- `CloudEventCreate`: CloudEvents 1.0 input.
- `SubscriptionCreate` / `SubscriptionRead`: webhook integration contracts.

### `app/art_schemas.py`

Defines the larger governed ART lifecycle contracts.

- `ArtCreate` supplies shared enterprise context.
- `FailureEventCreate`, `AgentRunCreate`, `AgentRunStepCreate`,
  `DecisionJournalCreate`, `ImpactAssessmentCreate`,
  `ImpactDependencyCreate`, `TestSelectionCreate`, `ExecutionIntentCreate`,
  `ExecutionResultCreate`, `SelfHealProposalCreate`, `OutcomeFeedbackCreate`,
  `EventInboxCreate`, and `EventOutboxCreate` validate each lifecycle resource.
- `require_external_payload_reference()` prevents oversized failure payloads
  from being stored without an external reference.
- `require_governance_for_dispatchable_intent()` prevents a dispatchable
  execution intent without a governance decision.
- `LifecycleStateUpdate` validates state-transition requests.
- `ArtResourceResponse` provides one uniform lifecycle response shape.

## 4. HTTP API files

### `app/api.py`

Implements the normal operations API plus optional integration/admin routes.
Every database query is scoped by the authenticated tenant.

Operations methods:

- `ingest_event()` delegates native intake to `persist_event()`.
- `get_event()` retrieves one incident.
- `get_event_trace()` assembles ingestion, classification, suggestion,
  confidence, and outcome records into a readable processing timeline.
- `list_events()` returns recent incidents.
- `overview()` calculates UI totals, recent incidents, and confidence buckets.
- `list_suggestions()` returns suggestions, optionally for one event.
- `decide()` locks a suggestion and calls `record_suggestion_decision()`.
- `audit()` filters audit rows by tenant, time, environment, and correlation ID.

Optional integration methods, exposed by the `integration` or `full` profile:

- `ingest_cloud_event()` converts and persists a CloudEvent.
- `create_subscription()`, `list_subscriptions()`, and
  `deactivate_subscription()` manage webhook destinations.
- `list_deliveries()` reports webhook delivery attempts.
- `retry_delivery()` makes a failed delivery immediately eligible for retry.

Optional internal methods, exposed by the `admin` or `full` profile:

- `list_references()` returns reusable accepted-remediation knowledge.
- `create_policy()` / `list_policies()` manage tenant governance rules.
- `create_knowledge()` / `list_knowledge()` manage tenant knowledge records.

### `app/art_api.py`

Exposes generic governed-lifecycle CRUD routes in admin/full mode.

- `repository()` creates a tenant-scoped `ArtRepository` for a request.
- Each `create_*` method creates its named resource: failure event, agent run,
  run step, decision journal, impact assessment/dependency, test selection,
  execution intent/result, self-heal proposal, outcome feedback, or event
  inbox/outbox record.
- Each matching `list_*` method lists that tenant's records.
- `update_agent_run()`, `update_execution_intent()`, and
  `update_self_heal_proposal()` request governed state changes.
- `_register_resource_read_route()` registers consistent single-resource GET
  routes; its nested `read_resource()` delegates to the repository.
- `correlation_trace()` returns all lifecycle records for one correlation UUID.

## 5. Persistence models and repositories

### `app/models.py`

Contains SQLAlchemy mappings for the core PostgreSQL tables.

- `Event`: incoming incident and processing state.
- `Suggestion`: proposed remediation, confidence, policy result, and state.
- `Policy`: tenant governance configuration.
- `KnowledgeItem`: searchable tenant knowledge.
- `AuditLog`: immutable action history.
- `Outbox`: transactional work queue consumed by the worker.
- `WebhookSubscription` / `WebhookDelivery`: downstream delivery state.
- `IntegrationIngestion` / `IntegrationPublication`: optional external-table
  bridge checkpoints.
- `SuggestionDecision`: operator acceptance or rejection.
- `RemediationReference`: reusable learning derived from decisions.
- `EventStatus` and `SuggestionStatus`: allowed state values.

### `app/art_models.py`

Contains mappings for the enterprise lifecycle tables under the `art` schema.

- Shared mixins: `ArtRecord`, `TimestampedRecord`, and `ArtStatus`.
- Lifecycle records: `FailureEvent`, `AgentRun`, `AgentRunStep`,
  `AgentDecisionJournal`, `ImpactAssessment`, `ImpactDependency`,
  `TestSelectionDecision`, `ExecutionIntent`, `ExecutionResultRef`,
  `SelfHealProposal`, `OutcomeFeedback`, `ArtEventInbox`, and `ArtEventOutbox`.

### `app/art_repository.py`

Provides one governed persistence implementation for all ART lifecycle models.

- `create()` validates parent references, adds tenant/correlation fields,
  persists a model, and adds an audit entry.
- `list()` returns tenant-scoped rows with optional correlation filtering.
- `get()` retrieves one tenant-scoped resource.
- `change_state()` locks a row, validates the requested state transition,
  updates it, and audits the change.
- `correlation_trace()` gathers related records from all lifecycle tables.
- `_find()` is the shared tenant-safe lookup.
- `_validate_parent_references()` ensures referenced lifecycle parents exist.
- `_add_audit_entry()` writes lifecycle audit data.
- `_as_response()` converts any lifecycle model to `ArtResourceResponse`.
- `_status_field()`, `_status_of()`, and `_timestamp_column()` normalize model
  differences for generic repository operations.

## 6. Intake, worker, and processing

### `app/ingestion.py`

- `persist_event()` idempotently inserts an `Event`, `Outbox`, and `AuditLog` in
  one transaction. Repeated tenant/external-ID requests return the existing
  event.
- `cloud_event_to_event()` converts CloudEvents into the native event contract.
- `persist_cloud_event()` validates raw CloudEvent data and calls
  `persist_event()`.

### `app/worker.py`

- `run()` continuously locks unpublished outbox rows with `SKIP LOCKED`, calls
  `process_event()`, delivers due webhooks, commits work, and sleeps when idle.
  If the optional external PostgreSQL bridge is enabled, it also pulls and
  publishes bridge records.
- `main()` guarantees database-engine disposal.

### `app/processor.py`

- `process_event()` is the central orchestration method: lock event, retrieve
  evidence, route it, run specialists, enrich candidates, apply policy, record
  lifecycle state, queue webhooks, and mark the event complete or failed.
- `_create_suggestion()` evaluates policy/confidence and persists a suggestion
  plus its audit record.
- `_queue_ready_webhooks()` creates delivery rows only for ready suggestions
  and matching active subscriptions.
- `_add_audit_log()` adds processing audit entries.

### `app/services.py`

Contains routing, evidence, agent, AI, and governance services.

- `Candidate` is an agent's proposed remediation.
- `FailureRoute` describes the selected category and routing evidence.
- `FailureRouter.classify()` scores structured fields and text signals.
- `KnowledgeService.search()` finds tenant knowledge and previously accepted
  remediation references.
- `Agent.suggest()` defines the specialist-agent interface.
- `AIService.enrich()` optionally calls an approved AI endpoint while keeping
  deterministic policy control in the application.
- `PatternAgent.suggest()` produces a configured pattern-based candidate.
- `TargetedRepairAgent.suggest()`, `_change_plan()`, and `_validation()` add
  structured repair and verification instructions.
- `XPathInvestigationAgent.suggest()` handles locator-specific failures.
- `specialist_agents()` constructs configured specialist implementations.
- `EvidenceRequestAgent.suggest()` requests evidence when routing is ambiguous.
- `route_details()` serializes routing evidence for audit/output.
- `routed_agents()` pairs classification with the applicable agents.
- `PolicyEngine.evaluate()` applies tenant policy and confidence thresholds to
  return suggestion status, policy details, and final confidence.

### `app/art_lifecycle.py`

Mirrors normal processing into the governed enterprise lifecycle model.

- `correlation_uuid()` produces a stable UUID from an event correlation key.
- `event_environment()` normalizes the event environment.
- `LifecycleRecorder.start()` creates the failure event, agent run, and initial
  processing steps.
- `record_candidate()` records the agent decision and self-heal proposal.
- `complete()` closes the run as completed or failed.
- `record_step()` creates a lifecycle step with bounded payload data.
- `_safe_payload_summary()` removes or truncates unsafe/large payload content.

### `app/decisions.py`

- `event_fingerprint()` creates a stable signature for matching similar events.
- `record_suggestion_decision()` updates suggestion status and coordinates the
  decision, reusable reference, and audit writes.
- `_upsert_decision()` creates or updates the operator decision record.
- `_upsert_reference()` activates accepted remediation learning and deactivates
  rejected learning.

## 7. External delivery and optional adapters

### `app/webhooks.py`

- `cloud_event()` converts a ready suggestion to a CloudEvents payload.
- `deliver_due()` locks eligible delivery rows, calls subscriber URLs, records
  success, schedules exponential retries, or marks dead letters.

### `app/backbone.py`

Optional Kafka-compatible CloudEvent consumer.

- `BackboneEnvelope` carries decoded event data and tenant identity.
- `_headers()` normalizes Kafka headers.
- `decode_backbone_event()` supports structured and binary CloudEvents.
- `dead_letter_record()` safely serializes invalid messages.
- `_kafka_security()` builds configured Kafka security options.
- `run()` consumes events, persists them, commits offsets, and publishes invalid
  records to the dead-letter topic.
- `main()` provides process startup and cleanup.

### `app/integrations/postgres_bridge.py`

Optional adapter for legacy PostgreSQL event/result tables. It is not needed
when callers use the ART HTTP API and the application uses its normal database.

- `quote_identifier()` / `quote_table()` validate and quote configured SQL
  identifiers.
- `BridgeColumns` holds the configured source-column mapping.
- `ExternalPostgresBridge.__init__()` validates identifiers and prepares state.
- `_ensure_sessions()` creates the external database session factory lazily.
- `validate()` verifies configured tables and required columns.
- `_columns()` reads PostgreSQL column metadata.
- `_table_parts()` splits a schema-qualified table safely.
- `pull_events()` claims external rows and persists them as ART events.
- `_payload()` normalizes an external JSON payload.
- `push_ready_suggestions()` finds unpublished results.
- `_insert_result()` writes a separate result table.
- `_update_event()` writes result columns back to the source event row.
- `close()` disposes the external engine.

### `app/integrations/postgres_bridge_cli.py`

- `validate()` prints bridge validation results and returns a shell exit code.
- `main()` runs validation from `make validate-integration`.

## 8. Browser UI

### `app/static/index.html`

Defines the operations-console pages, forms, modal dialogs, filters, and
Bootstrap component structure.

### `app/static/styles.css`

Defines the visual theme and responsive layout; it has no application or
database logic.

### `app/static/app.js`

- `$()` / `$$()` select DOM elements; `escapeHtml()` protects rendered text;
  `sleep()` supports polling.
- `settings()` reads the locally saved API URL/key/tenant/actor.
- `api()` is the shared authenticated HTTP client.
- `toast()`, `showDetails()`, and `detailJson()` provide shared UI feedback.
- `renderTraceStage()`, `showEventDetails()`, and `showSuggestionDetails()`
  render processing detail modals.
- `navigate()` switches console views.
- `renderScenarios()`, `selectScenario()`, and `validatePayload()` manage sample
  incident forms.
- `submitEvent()` posts an event and polls for its result.
- `showDisconnected()` displays database/API unavailability.
- `loadOverview()` refreshes operational metrics.
- `renderDecisionRecords()`, `eventIcon()`, and `formatDate()` format data.
- `loadSuggestions()` / `renderSuggestion()` retrieve and render suggestions.
- `decideSuggestion()` submits accept/reject decisions.
- `loadAudit()`, `updateCustomAuditRange()`, `initializeAuditCalendars()`,
  `openDateTimePicker()`, and `clearAuditFilters()` manage audit exploration.
- `openSettings()` / `saveSettings()` manage browser connection settings.
- `exportAudit()` downloads the displayed audit data.
- `bindEvents()` attaches browser event handlers and starts the UI.

## 9. PostgreSQL, migrations, and pgAdmin

### `alembic.ini` and `migrations/env.py`

`alembic.ini` points Alembic at the migration directory. `env.py` imports model
metadata and substitutes `DATABASE_URL`.

- `offline()` emits SQL without opening a database connection.
- `online()` runs migrations through the async PostgreSQL engine.

### `migrations/versions/*.py`

Every migration has `upgrade()` to apply a schema change and `downgrade()` to
reverse it.

- `0001_initial.py`: core event, suggestion, policy, knowledge, audit, and outbox
  tables.
- `0002_enterprise_delivery.py`: webhook subscriptions/deliveries.
- `0003_integration_publications.py`: optional bridge publication tracking.
- `0004_integration_ingestions.py`: optional bridge ingestion tracking.
- `0005_pgadmin_reporting_views.py`: `art_reporting` operational views.
- `0006_remediation_references.py`: decisions and reusable remediation history.
- `0007_reference_reporting.py`: reference-library reporting view.
- `0008_enterprise_art_lifecycle.py`: complete governed `art` schema and views.

### Database and pgAdmin scripts

- `scripts/db_setup.sh` creates the PostgreSQL role and database using standard
  `psql`/`createdb`. It does not create tables; `make migrate` does that.
- `scripts/db_inspect.sh` queries migration, reporting, reference, and lifecycle
  views from the terminal.
- `scripts/pgadmin_register.sh` imports the prepared server definition into a
  local pgAdmin installation.
- `examples/pgadmin-servers.json` is the importable pgAdmin connection metadata;
  it deliberately contains no password.
- `examples/pgadmin_art_dashboard.sql` is the pgAdmin Query Tool workbook.
- `examples/external_postgres_tables.sql` creates only the optional legacy
  bridge demonstration tables.
- `scripts/verify_art_lifecycle.py`: `create()` calls one lifecycle endpoint;
  `main()` performs an end-to-end lifecycle API verification.

## 10. Project and command files

### `pyproject.toml`

Defines Python version, runtime/dev dependencies, package build configuration,
pytest behavior, and Ruff formatting/lint rules.

### `Makefile`

- `setup`: creates `.venv` and installs the project plus development tools.
- `test` / `coverage`: run automated verification.
- `db-setup` / `migrate` / `db-inspect`: create, migrate, and inspect PostgreSQL.
- `api`, `api-integration`, `api-admin`, `api-full`: run API profiles.
- `worker`: process outbox events and webhook deliveries.
- `backbone`: run the optional Kafka consumer.
- `validate-integration`: validate the optional legacy PostgreSQL bridge.
- `verify-art`: run the lifecycle verification script.
- `pgadmin-register`: import the pgAdmin server definition.

## 11. Tests

Tests mirror the runtime areas and are the best place to find usage examples.

- `test_agents.py`: routing and specialist-agent behavior.
- `test_api_inventory.py`: route profiles and OpenAPI contracts.
- `test_art_lifecycle.py`: lifecycle request validation and API inventory.
- `test_art_runtime.py`: lifecycle recorder and repository behavior.
- `test_backbone.py`: Kafka CloudEvent decoding and dead-letter handling.
- `test_decisions_and_ingestion.py`: idempotent intake and decision learning.
- `test_postgres_bridge.py`: optional bridge identifier/mapping validation.
- `test_runtime_config.py`: checked-in JSON rules and cross-field validation.
- `test_runtime_services.py`: processor, policy, webhook, and worker behavior.
- `test_ui_assets.py`: browser workflow and UI contract checks.

## 12. Where to start for a change

| Desired change | Primary file | Usually correlated with |
|---|---|---|
| Add an incident input field | `app/schemas.py` | `app/models.py`, migration, UI |
| Add/change an endpoint | `app/api.py` | schema, test, UI |
| Change routing | `runtime_rules.json` | `services.py`, agent tests |
| Change suggestion generation | `app/services.py` | `processor.py`, service tests |
| Change confidence/governance | `PolicyEngine.evaluate()` | settings, API overview, tests |
| Change persistence | model file | Alembic migration, repository/API |
| Change worker behavior | `app/worker.py` | `processor.py`, worker tests |
| Change operator decisions | `app/decisions.py` | models, API, reporting views |
| Change browser behavior | `app/static/app.js` | HTML/CSS, UI tests |
| Add a pgAdmin report | migration/reporting view | dashboard SQL, pgAdmin guide |
