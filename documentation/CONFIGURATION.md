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
app/resources/runtime_rules.json
```

It contains:

- Failure-domain keywords and weights.
- Structured evidence fields.
- Routing confidence and ambiguity rules.
- Specialist signals and proposed action names.
- Evidence requirements.
- Change-plan and validation instructions.
- Agent confidence bonuses and caps.
- XPath locator priorities.
- Knowledge retrieval limits.
- Lifecycle category/severity mappings.
- Worker and webhook batch sizes.
- Webhook retry timing and CloudEvent metadata.

Python loads this file through `app/runtime_config.py`. Pydantic validates the
complete structure. Missing categories, invalid confidence ranges, or invalid
numeric values fail clearly instead of silently changing runtime behavior.

To use a different rules file:

```bash
RUNTIME_RULES_PATH=app/resources/runtime_rules.preprod.json make api
```

Use the same setting for the worker:

```bash
RUNTIME_RULES_PATH=app/resources/runtime_rules.preprod.json make worker
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

1. Copy `app/resources/runtime_rules.json`.
2. Change one group of rules.
3. Point `RUNTIME_RULES_PATH` at the copy.
4. Run `make test`.
5. Submit representative incidents and inspect routing, confidence, and audit
   output.
6. Review the configuration change like source code.
7. Deploy the same rules file with both API and worker.
