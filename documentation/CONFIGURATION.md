# Runtime configuration maintenance

ART separates configuration into two layers.

## Environment configuration

Environment-specific connections, credentials, process settings, API limits,
and optional integrations are defined by `app/config.py` and supplied through
`.env` or process environment variables. Start from `.env.example`.

Examples:

- `DATABASE_URL`
- `API_KEY`
- `API_PROFILE`
- `CONFIDENCE_REVIEW_THRESHOLD`
- `CONFIDENCE_DELIVERY_THRESHOLD`
- `AI_*`
- `KAFKA_*`
- `EXTERNAL_POSTGRES_*`
- API list limits and worker polling settings

Never commit a real `.env` file or secret.

## Runtime business rules

Maintainable classification and remediation behavior lives in:

```text
app/resources/runtime/
├── routing.json
├── agents.json
├── knowledge.json
├── lifecycle.json
└── delivery.json
```

The files are grouped by their runtime consumers:

- `routing.json`: failure-domain signals, structured hints, scoring, and
  ambiguity rules used by `FailureRouter`.
- `agents.json`: specialists, evidence requirements, change plans, confidence,
  XPath behavior, and investigation fallback used by agent services.
- `knowledge.json`: scan and result limits used by `KnowledgeService`.
- `lifecycle.json`: environment, severity, category, and proposal mappings used
  by `LifecycleRecorder`.
- `delivery.json`: worker/webhook batches, retries, CloudEvent metadata, and
  error limits used by the worker and delivery services.

Python combines these files through `app/runtime_config.py` into one
`RuntimeRules` object. Pydantic validates the complete structure, including
cross-file relationships. Missing categories, invalid confidence ranges, or
invalid numeric values fail clearly instead of silently changing behavior.

To use a different rules directory:

```bash
RUNTIME_RULES_PATH=deploy/preprod/runtime make api
```

Use the same setting for the worker:

```bash
RUNTIME_RULES_PATH=deploy/preprod/runtime make worker
```

The API and worker must use the same rules version.

## Values intentionally kept in Python

Some constants are contracts rather than maintenance data and should remain in
code:

- Database column sizes and constraints.
- Enum values stored in PostgreSQL.
- HTTP status codes.
- CloudEvents protocol field names.
- API paths.
- Legal lifecycle state transitions.
- Pydantic request-field validation limits.

Changing these values can require an API version or database migration, so they
must not be silently replaced by a runtime JSON edit.

## Safe change process

1. Copy `app/resources/runtime/`.
2. Change the relevant responsibility-based file.
3. Point `RUNTIME_RULES_PATH` at the copy.
4. Run `make test`.
5. Submit representative incidents and inspect routing, confidence, and audit
   output.
6. Review the configuration change like source code.
7. Deploy the same rules directory with both API and worker.
