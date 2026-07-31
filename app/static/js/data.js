/* Incident scenarios, labels, and shared UI state. */
const scenarios = {
  ui: {
    symbol: "⌖", name: "UI locator", summary: "Obsolete XPath after a DOM change",
    type: "ui.xpath.element_not_found", source: "ci://checkout-ui-tests",
    payload: {
      failure_category: "ui",
      test_file: "tests/ui/test_checkout.py",
      test_name: "test_submit_order",
      error: "NoSuchElement: XPath did not match any element",
      failed_locator: {strategy: "xpath", value: "//button[@id='submit-order']"},
      dom_candidates: [{
        tag: "button", text: "Submit order",
        attributes: {"data-testid": "submit-order", "aria-label": "Submit order"}
      }],
      build_id: "preprod-762"
    },
    route: [
      ["Evidence", "failed_locator and dom_candidates identify a browser locator failure."],
      ["Classification", "Explicit UI category receives the strongest routing weight."],
      ["Specialist", "XPath investigator compares stable locator candidates."],
      ["Expected fix", "Replace obsolete XPath with a unique data-testid selector."]
    ]
  },
  api: {
    symbol: "⇄", name: "API timeout", summary: "Orders endpoint exceeds its latency budget",
    type: "api.test.timeout", source: "ci://orders-integration-tests",
    payload: {
      failure_category: "api", test_file: "tests/api/test_orders.py",
      test_name: "test_create_order", source_file: "app/orders.py",
      method_name: "create_order", endpoint: "/orders", http_method: "POST",
      timeout_ms: 5000, response_time_ms: 8120, exception_type: "ReadTimeout",
      trace_id: "trace-preprod-42", error: "POST /orders timed out after 5000ms"
    },
    route: [
      ["Evidence", "Endpoint, HTTP method, timeout, and trace ID identify an API boundary."],
      ["Classification", "Structured API fields outweigh incidental text in logs."],
      ["Specialist", "API agent targets app/orders.py:create_order."],
      ["Expected fix", "Trace downstream latency before changing handler or timeout behavior."]
    ]
  },
  logic: {
    symbol: "ƒ", name: "Logic exception", summary: "Null state reaches a calculation branch",
    type: "application.logic.exception", source: "ci://pricing-unit-tests",
    payload: {
      failure_category: "logic", test_file: "tests/test_pricing.py",
      test_name: "test_discount_without_membership", source_file: "app/pricing.py",
      method_name: "calculate_discount", exception_type: "TypeError",
      stack_trace: "TypeError: unsupported operand for None\n  at app/pricing.py:74 in calculate_discount",
      expected_result: 0, actual_result: "exception",
      error: "membership discount was None"
    },
    route: [
      ["Evidence", "Exception type, stack trace, source file, and method locate the failing branch."],
      ["Classification", "Explicit logic category resolves competing functional signals."],
      ["Specialist", "Logic agent targets the first application stack frame."],
      ["Expected fix", "Restore the violated invariant and add a regression test."]
    ]
  },
  functional: {
    symbol: "⇥", name: "Workflow", summary: "Order state differs from the expected result",
    type: "business.workflow.assertion_failed", source: "ci://orders-functional-tests",
    payload: {
      failure_category: "functional", test_file: "tests/functional/test_orders.py",
      test_name: "test_paid_order_transitions_to_fulfilment",
      source_file: "app/workflows/orders.py", method_name: "advance_order",
      workflow: "order_fulfilment", expected_result: "ready_for_fulfilment",
      actual_result: "payment_confirmed", error: "order did not advance after payment"
    },
    route: [
      ["Evidence", "Expected/actual states and workflow name identify a business transition."],
      ["Classification", "Functional fields route away from generic logic handling."],
      ["Specialist", "Workflow agent targets advance_order."],
      ["Expected fix", "Correct the transition while preserving adjacent valid states."]
    ]
  },
  test_data: {
    symbol: "▦", name: "Test data", summary: "Fixture no longer matches the input schema",
    type: "test.fixture.validation_failed", source: "ci://customer-tests",
    payload: {
      failure_category: "test_data", test_file: "tests/fixtures/customers.py",
      test_name: "test_create_customer", fixture: "valid_customer",
      dataset: "customer-v3", expected_result: "email is required",
      actual_result: "email field absent", error: "ValidationError: email is required"
    },
    route: [
      ["Evidence", "Fixture, dataset, and schema expectation identify test data."],
      ["Classification", "Explicit test_data category routes to the data specialist."],
      ["Specialist", "Test-data agent inspects the smallest invalid fixture value."],
      ["Expected fix", "Update the fixture to the current schema and rerun consumers."]
    ]
  },
  database: {
    symbol: "◉", name: "Database", summary: "PostgreSQL deadlock aborts an order update",
    type: "database.transaction.deadlock", source: "apm://orders-database",
    payload: {
      failure_category: "database", database_system: "postgres",
      sql_state: "40P01", query_name: "update_order_status",
      query: "UPDATE orders SET status = $1 WHERE id = $2",
      source_file: "app/repositories/orders.py", method_name: "update_status",
      trace_id: "trace-db-preprod", error: "DeadlockDetected: deadlock detected"
    },
    route: [
      ["Evidence", "SQL state, query identity, and database engine identify transactional failure."],
      ["Classification", "Database fields outweigh the generic exception text."],
      ["Specialist", "Database agent targets the repository transaction boundary."],
      ["Expected fix", "Normalize lock ordering and validate transaction and query-plan behavior."]
    ]
  },
  infrastructure: {
    symbol: "△", name: "Infrastructure", summary: "Kubernetes workload is repeatedly OOM-killed",
    type: "kubernetes.pod.oomkilled", source: "monitoring://preprod-eu",
    payload: {
      failure_category: "infrastructure", cluster: "preprod-eu",
      namespace: "orders", pod: "orders-api-7d8f", container: "api",
      resource_metrics: {memory_limit_mb: 512, peak_memory_mb: 611},
      manifest_file: "deploy/orders-api.yaml", resource_name: "orders-api",
      error: "OOMKilled with exit code 137"
    },
    route: [
      ["Evidence", "Cluster, workload identity, exit reason, and resource metrics locate the failure."],
      ["Classification", "Kubernetes and OOM signals route to infrastructure."],
      ["Specialist", "Infrastructure agent targets the owning deployment manifest."],
      ["Expected fix", "Confirm leak versus capacity, then make a bounded manifest change."]
    ]
  },
  dependency: {
    symbol: "⛓", name: "Dependency", summary: "Payments service is unavailable upstream",
    type: "dependency.upstream.unavailable", source: "apm://orders-api",
    payload: {
      failure_category: "dependency", dependency_name: "payments-api",
      dependency_endpoint: "/authorize", upstream_status: 503,
      config_file: "config/orders-resilience.yaml", resource_name: "payments-client",
      trace_id: "trace-dependency-preprod", error: "upstream service unavailable"
    },
    route: [
      ["Evidence", "Dependency name, endpoint, status, and trace identify an upstream boundary."],
      ["Classification", "Explicit dependency evidence prevents misrouting as a local API bug."],
      ["Specialist", "Dependency agent inspects health and resilience configuration."],
      ["Expected fix", "Correct the boundary or resilience policy without masking persistent failure."]
    ]
  },
  security: {
    symbol: "◆", name: "Security", summary: "Service principal is denied an approved action",
    type: "security.authorization.forbidden", source: "security://access-control",
    payload: {
      failure_category: "security", security_control: "authorization",
      principal: "orders-worker", permission: "payments.authorize",
      source_file: "access/orders.rego", resource_name: "payments-authorization",
      error: "403 forbidden: required permission is absent"
    },
    route: [
      ["Evidence", "Security control, principal, and permission identify authorization failure."],
      ["Classification", "Security evidence takes precedence over the HTTP 403 symptom."],
      ["Specialist", "Security agent targets the least-privilege access definition."],
      ["Expected fix", "Restore only the required permission through an approved workflow."]
    ]
  },
  performance: {
    symbol: "⌁", name: "Performance", summary: "Endpoint p95 regresses far beyond baseline",
    type: "performance.latency.regression", source: "apm://orders-api",
    payload: {
      failure_category: "performance", endpoint: "/orders",
      baseline_ms: 180, observed_ms: 1450, p95_ms: 1700,
      profile: "orders-create-preprod", source_file: "app/orders.py",
      method_name: "create_order", trace_id: "trace-performance-preprod",
      error: "p95 latency regression above service objective"
    },
    route: [
      ["Evidence", "Baseline, observed latency, percentile, and profile quantify a regression."],
      ["Classification", "Explicit performance category avoids routing as a generic API timeout."],
      ["Specialist", "Performance agent targets the profiled endpoint method."],
      ["Expected fix", "Optimize the measured bottleneck and rerun representative benchmarks."]
    ]
  }
};

const titles = {
  dashboard: "Runtime overview", simulate: "Incident intake",
  suggestions: "Remediation suggestions", audit: "Audit trail",
  "api-explorer": "API explorer"
};
let activeScenario = "ui";
let suggestionFilter = "all";
let lastAudit = [];
let recentEvents = [];
let currentSuggestions = [];
let decisionRecords = [];
