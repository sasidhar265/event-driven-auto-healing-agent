# ART visual guide

This guide explains the main ART functionality through diagrams. GitHub renders
these Mermaid diagrams directly, so they remain readable and maintainable with
the source code.

## 1. ART in one picture

```mermaid
flowchart LR
    A["Failure detected<br/>UI · API · Logic · Database · Platform"] --> B["ART receives event"]
    B --> C[("PostgreSQL<br/>event + audit + outbox")]
    C --> D["Worker identifies<br/>failure domain"]
    D --> E["Specialist proposes<br/>a remediation"]
    E --> F{"Confidence and<br/>governance"}
    F -->|Low or blocked| G["Suppressed"]
    F -->|Needs approval| H["Review"]
    F -->|Strong and eligible| I["Ready"]
    G --> J["ART UI and audit trail"]
    H --> J
    I --> J
    J --> K{"Operator decision"}
    K -->|Accept| L["Reusable remediation reference"]
    K -->|Reject| M["Rejected outcome retained"]
```

The important boundary is that ART proposes and explains a fix. It does not
directly change or deploy the target application.

## 2. System architecture

```mermaid
flowchart TB
    subgraph Producers["Failure producers"]
        UI["UI and automated tests"]
        API["API and application monitoring"]
        DB["Database monitoring"]
        OPS["Infrastructure, security, dependency, performance"]
        KAFKA["Kafka-compatible event backbone"]
    end

    subgraph Runtime["ART runtime"]
        HTTP["FastAPI ingestion"]
        BACKBONE["CloudEvent consumer"]
        STORE[("PostgreSQL")]
        WORKER["Background worker"]
        ROUTER["Failure router"]
        KNOWLEDGE["Internal knowledge and prior fixes"]
        SPECIALIST["Selected specialist"]
        AI["Optional approved AI enrichment"]
        GATE["Policy and confidence gate"]
        WEBHOOK["Signed webhook delivery"]
    end

    subgraph Experience["Operator experience"]
        CONSOLE["ART browser console"]
        OPENAPI["OpenAPI documentation"]
        PGADMIN["pgAdmin reporting"]
    end

    UI --> HTTP
    API --> HTTP
    DB --> HTTP
    OPS --> HTTP
    KAFKA --> BACKBONE
    BACKBONE --> HTTP
    HTTP --> STORE
    STORE --> WORKER
    WORKER --> ROUTER
    STORE --> KNOWLEDGE
    ROUTER --> SPECIALIST
    KNOWLEDGE --> SPECIALIST
    SPECIALIST --> AI
    AI --> GATE
    GATE --> STORE
    GATE --> WEBHOOK
    STORE --> CONSOLE
    HTTP --> OPENAPI
    STORE --> PGADMIN
```

## 3. What happens after an incident is submitted

```mermaid
sequenceDiagram
    autonumber
    actor Operator
    participant UI as ART UI
    participant API as FastAPI
    participant DB as PostgreSQL
    participant Worker
    participant Router
    participant Specialist
    participant Gate as Policy/Confidence

    Operator->>UI: Submit failure event
    UI->>API: POST /v1/events
    API->>DB: Save event, audit, and outbox
    DB-->>API: Transaction committed
    API-->>UI: 202 Accepted + event ID
    Worker->>DB: Lock unpublished outbox item
    Worker->>Router: Classify structured evidence
    Router-->>Worker: Domain, signals, alternatives
    Worker->>Specialist: Request remediation candidate
    Specialist-->>Worker: Rationale, proposed changes, confidence
    Worker->>Gate: Apply policy and confidence thresholds
    Gate-->>Worker: Suppressed, Review, or Ready
    Worker->>DB: Save suggestion, lifecycle, and audit
    UI->>API: GET /v1/events/{id}/trace
    API->>DB: Read processing records
    DB-->>API: Trace and suggestion
    API-->>UI: Explainable stage-by-stage result
    UI-->>Operator: Show logs, confidence, and proposed fix
```

## 4. How ART recognizes the failure type

```mermaid
flowchart TD
    EVENT["Failure event"] --> EXPLICIT{"Explicit<br/>failure_category?"}
    EXPLICIT -->|Yes| STRUCTURED["Give strong weight to category"]
    EXPLICIT -->|No| FIELDS["Inspect structured evidence fields"]
    STRUCTURED --> FIELDS
    FIELDS --> SIGNALS["Inspect event type and text signals"]
    SIGNALS --> SCORE["Calculate explainable domain scores"]
    SCORE --> CLEAR{"Clear strongest<br/>domain?"}
    CLEAR -->|No| INVESTIGATE["Evidence collection / investigation"]
    CLEAR -->|Yes| ROUTE["Select one specialist"]

    ROUTE --> UI["UI / XPath"]
    ROUTE --> API["API"]
    ROUTE --> LOGIC["Logic"]
    ROUTE --> FUNCTIONAL["Functional workflow"]
    ROUTE --> TESTDATA["Test data"]
    ROUTE --> DATABASE["Database"]
    ROUTE --> INFRA["Infrastructure"]
    ROUTE --> DEP["Dependency"]
    ROUTE --> SECURITY["Security"]
    ROUTE --> PERF["Performance"]
```

Structured fields have more influence than vague error text. If the evidence is
ambiguous, ART asks for better evidence rather than guessing a precise change.

## 5. Confidence Decision Model

```mermaid
flowchart LR
    S["Suggestion candidate"] --> V{"Policy violation?"}
    V -->|Yes| SUP["Suppressed"]
    V -->|No| C{"Confidence"}
    C -->|Below 60%| SUP
    C -->|60% to 79%| REV["Review"]
    C -->|80% or above| A{"Approval required?"}
    A -->|Yes| REV
    A -->|No| READY["Ready"]

    SUP --> SUPNOTE["Insufficient evidence<br/>or blocked action"]
    REV --> REVNOTE["Human decision required"]
    READY --> READNOTE["Eligible for controlled delivery"]
```

```mermaid
pie showData
    title Example confidence classifications
    "Suppressed" : 15
    "Review" : 25
    "Ready" : 60
```

The pie chart is illustrative. The real Overview screen reads current counts
from PostgreSQL and can filter Decision Model records by state and ranking.

## 6. UI, API, and database interaction

```mermaid
flowchart LR
    subgraph Browser["ART browser console"]
        O["Overview"]
        I["Incident intake"]
        S["Suggestions"]
        A["Audit Trail"]
        C["Connection details"]
    end

    subgraph OperationsAPI["Operations API"]
        OE["/v1/overview"]
        EV["/v1/events"]
        TR["/v1/events/{id}/trace"]
        SG["/v1/suggestions"]
        DC["/v1/suggestions/{id}/decision"]
        AU["/v1/audit"]
        HL["/health/live"]
    end

    DB[("PostgreSQL source of truth")]

    O --> OE
    I --> EV
    I --> TR
    S --> SG
    S --> DC
    A --> AU
    C --> HL

    OE --> DB
    EV --> DB
    TR --> DB
    SG --> DB
    DC --> DB
    AU --> DB
    HL --> DB
```

The console does not directly query PostgreSQL. It calls the API, which applies
authentication and tenant isolation before reading or writing the database.

## 7. UI navigation map

```mermaid
flowchart TB
    HOME["ART console"] --> OVERVIEW["Overview"]
    HOME --> INTAKE["Incident intake"]
    HOME --> SUGGESTIONS["Suggestions"]
    HOME --> AUDIT["Audit Trail"]
    HOME --> CONNECTION["Connection popup"]

    OVERVIEW --> METRICS["Metrics and recent incidents"]
    OVERVIEW --> DECISION["Decision Model table<br/>state + ranking filters"]

    INTAKE --> PROFILE["Choose failure domain"]
    INTAKE --> ENVELOPE["Review event envelope"]
    INTAKE --> SUBMIT["Submit and watch processing logs"]

    SUGGESTIONS --> ALL["All outcomes"]
    SUGGESTIONS --> ACCEPTED["Accepted"]
    SUGGESTIONS --> REJECTED["Rejected"]
    SUGGESTIONS --> DETAIL["Details popup"]

    AUDIT --> ENV["Environment filter"]
    AUDIT --> TIME["Preset/custom time filter"]
    AUDIT --> CORR["Correlation search"]
    AUDIT --> EXPORT["Filtered JSON export"]

    CONNECTION --> APISTATUS["API status/profile"]
    CONNECTION --> DBSTATUS["Safe PostgreSQL details"]
```

Internal Knowledge/AI and Policy Governance influence ART processing but do not
appear as primary navigation screens.

## 8. Main database relationships

```mermaid
erDiagram
    EVENTS ||--o{ SUGGESTIONS : produces
    EVENTS ||--o{ OUTBOX : queues
    EVENTS ||--o{ FAILURE_EVENTS : normalizes
    SUGGESTIONS ||--o{ SUGGESTION_DECISIONS : receives
    SUGGESTIONS ||--o{ REMEDIATION_REFERENCES : informs
    SUGGESTIONS ||--o{ WEBHOOK_DELIVERIES : delivers
    WEBHOOK_SUBSCRIPTIONS ||--o{ WEBHOOK_DELIVERIES : receives
    EVENTS ||--o{ AGENT_RUNS : traces
    AGENT_RUNS ||--o{ AGENT_RUN_STEPS : contains
    AGENT_RUNS ||--o{ AGENT_DECISION_JOURNALS : explains
    EVENTS ||--o{ AUDIT_LOGS : records

    EVENTS {
        uuid id PK
        string external_id
        string correlation_key
        json payload
        string status
    }
    SUGGESTIONS {
        uuid id PK
        uuid event_id FK
        float confidence
        json proposed_changes
        string status
    }
    SUGGESTION_DECISIONS {
        uuid id PK
        uuid suggestion_id FK
        string decision
        string actor
    }
    AUDIT_LOGS {
        uuid id PK
        string action
        string resource_type
        string resource_id
    }
```

Every operational query is tenant scoped. The environment is stored inside the
event payload, while the correlation ID is stored independently.

## 9. API profile boundaries

```mermaid
flowchart LR
    OPERATIONS["Operations<br/>UI-facing ART APIs"]
    INTEGRATION["Integration<br/>CloudEvents + webhooks"]
    ADMIN["Admin<br/>internal services + lifecycle"]
    FULL["Full<br/>all contracts"]

    OPERATIONS --> INTEGRATION
    OPERATIONS --> ADMIN
    INTEGRATION --> FULL
    ADMIN --> FULL
```

| Profile | Intended audience |
|---|---|
| Operations | ART console and normal operators |
| Integration | Event publishers and result consumers |
| Admin | Internal governance, knowledge, and lifecycle administrators |
| Full | Development, verification, and controlled combined deployments |

## 10. Deployment and environment portability

```mermaid
flowchart TB
    CODE["Same Git repository"] --> ENV["Environment-specific .env"]
    ENV --> APPDB["ART PostgreSQL tables"]
    ENV --> PROFILE["Selected API profile"]
    ENV --> OPTIONAL["Optional Kafka / AI / external DB bridge"]

    EXT[("Existing PostgreSQL tables")] --> MAP["Configured external-table mapping"]
    MAP --> BRIDGE["Generic PostgreSQL bridge"]
    BRIDGE --> APPDB
    APPDB --> BRIDGE
    BRIDGE --> RESULT[("Existing result table")]
```

Environment-specific connection strings and table mappings belong in
configuration. Core routing, suggestion, audit, and UI code should not be
rewritten when moving the application.

## 11. Safety and responsibility boundary

```mermaid
flowchart LR
    subgraph ART["ART responsibility"]
        RECEIVE["Receive"]
        IDENTIFY["Identify"]
        EXPLAIN["Explain"]
        SUGGEST["Suggest"]
        GOVERN["Govern"]
        AUDIT["Audit"]
    end

    subgraph External["Authorized external responsibility"]
        APPROVE["Approve"]
        CHANGE["Apply change"]
        TEST["Validate"]
        DEPLOY["Deploy"]
        ROLLBACK["Rollback if needed"]
    end

    RECEIVE --> IDENTIFY --> EXPLAIN --> SUGGEST --> GOVERN --> AUDIT
    GOVERN --> APPROVE --> CHANGE --> TEST --> DEPLOY
    TEST --> ROLLBACK
```

## 12. Where to read next

- [Main README](../README.md): project entry point and commands.
- [Detailed project walkthrough](PROJECT_WALKTHROUGH.md): prose explanation and
  code map.
- [Technical reference](README.md): deep implementation details.
- [Portability guide](PORTABILITY.md): other machines, environments, and
  PostgreSQL schemas.
- [pgAdmin guide](PGADMIN.md): database inspection and reporting.
- [Requirement map](ART_FEEDBACK_IMPLEMENTATION.md): document-to-code
  traceability.

