"""Add the enterprise ART lifecycle schema and correlation views."""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS art")
    op.execute("""
        CREATE OR REPLACE FUNCTION art.set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
          NEW.updated_at = now();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TABLE art.failure_events (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          correlation_id UUID NOT NULL,
          tenant_id VARCHAR(100) NOT NULL,
          environment VARCHAR(20) NOT NULL,
          source_event_id UUID,
          execution_run_id VARCHAR(150),
          test_id VARCHAR(150),
          request_id VARCHAR(150),
          source_system VARCHAR(150) NOT NULL,
          failure_category VARCHAR(30) NOT NULL DEFAULT 'UNKNOWN',
          failure_subtype VARCHAR(150),
          severity VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',
          api_endpoint TEXT,
          status_code INTEGER,
          error_message TEXT,
          trace_id VARCHAR(200),
          payload_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
          payload_ref TEXT,
          artifact_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
          raw_failure_ref TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CHECK (environment IN ('dev','test','preprod','prod')),
          CHECK (failure_category IN (
            'UI','API','FUNCTIONAL','DATA','PERFORMANCE','SECURITY',
            'BATCH','MAINFRAME','INFRA','UNKNOWN'
          )),
          CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
          CHECK (status_code IS NULL OR status_code BETWEEN 100 AND 599)
        )
    """)
    op.execute("""
        CREATE TABLE art.agent_runs (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          correlation_id UUID NOT NULL,
          tenant_id VARCHAR(100) NOT NULL,
          environment VARCHAR(20) NOT NULL,
          workflow_type VARCHAR(50) NOT NULL,
          trigger_event_type VARCHAR(100),
          source_event_id UUID,
          status VARCHAR(30) NOT NULL DEFAULT 'RECEIVED',
          started_at TIMESTAMPTZ,
          completed_at TIMESTAMPTZ,
          execution_time_ms INTEGER,
          input_context_ref TEXT,
          output_decision_ref TEXT,
          policy_decision_id UUID,
          policy_version VARCHAR(100),
          approval_required BOOLEAN NOT NULL DEFAULT FALSE,
          approval_id UUID,
          failure_reason TEXT,
          retry_count INTEGER NOT NULL DEFAULT 0,
          created_by VARCHAR(150),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CHECK (environment IN ('dev','test','preprod','prod')),
          CHECK (workflow_type IN (
            'CHANGE_ANALYSIS','FAILURE_ANALYSIS','IMPACT_ANALYSIS',
            'TEST_SELECTION','EXECUTION_ORCHESTRATION','SELF_MAINTENANCE'
          )),
          CHECK (execution_time_ms IS NULL OR execution_time_ms >= 0),
          CHECK (retry_count >= 0)
        )
    """)
    op.execute("""
        CREATE TABLE art.agent_run_steps (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          agent_run_id UUID NOT NULL REFERENCES art.agent_runs(id) ON DELETE CASCADE,
          correlation_id UUID NOT NULL,
          tenant_id VARCHAR(100) NOT NULL,
          environment VARCHAR(20) NOT NULL,
          agent_name VARCHAR(150) NOT NULL,
          step_name VARCHAR(150) NOT NULL,
          step_sequence INTEGER NOT NULL,
          status VARCHAR(30) NOT NULL DEFAULT 'RECEIVED',
          confidence_score DOUBLE PRECISION,
          confidence_reason TEXT,
          started_at TIMESTAMPTZ,
          completed_at TIMESTAMPTZ,
          execution_time_ms INTEGER,
          input_ref TEXT,
          output_ref TEXT,
          error_message TEXT,
          model_version VARCHAR(100),
          prompt_template_version VARCHAR(100),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CHECK (environment IN ('dev','test','preprod','prod')),
          CHECK (step_sequence > 0),
          CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1),
          CHECK (execution_time_ms IS NULL OR execution_time_ms >= 0)
        )
    """)
    op.execute("""
        CREATE TABLE art.agent_decision_journals (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          correlation_id UUID NOT NULL,
          tenant_id VARCHAR(100) NOT NULL,
          environment VARCHAR(20) NOT NULL,
          agent_run_id UUID REFERENCES art.agent_runs(id) ON DELETE SET NULL,
          agent_step_id UUID REFERENCES art.agent_run_steps(id) ON DELETE SET NULL,
          decision_type VARCHAR(50) NOT NULL,
          decision_summary TEXT NOT NULL,
          rationale TEXT,
          inputs_ref TEXT,
          context_ref TEXT,
          output_ref TEXT,
          confidence_score DOUBLE PRECISION,
          confidence_reason TEXT,
          evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
          policy_decision_id UUID,
          policy_version VARCHAR(100),
          model_version VARCHAR(100),
          prompt_template_version VARCHAR(100),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CHECK (environment IN ('dev','test','preprod','prod')),
          CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1)
        )
    """)
    op.execute("""
        CREATE TABLE art.impact_assessments (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          correlation_id UUID NOT NULL,
          tenant_id VARCHAR(100) NOT NULL,
          environment VARCHAR(20) NOT NULL,
          agent_run_id UUID REFERENCES art.agent_runs(id) ON DELETE SET NULL,
          impact_source VARCHAR(30) NOT NULL,
          source_event_id UUID,
          component_id VARCHAR(150),
          component_name VARCHAR(250) NOT NULL,
          component_type VARCHAR(100),
          service_name VARCHAR(250),
          business_capability_id VARCHAR(150),
          business_capability_name VARCHAR(250),
          impact_level VARCHAR(20) NOT NULL,
          risk_score DOUBLE PRECISION,
          confidence_score DOUBLE PRECISION,
          description TEXT,
          affected_test_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
          evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
          knowledge_graph_ref TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CHECK (environment IN ('dev','test','preprod','prod')),
          CHECK (impact_source IN ('code','config','infra','data','failure')),
          CHECK (impact_level IN ('LOW','MEDIUM','HIGH','CRITICAL')),
          CHECK (risk_score IS NULL OR risk_score BETWEEN 0 AND 1),
          CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1)
        )
    """)
    op.execute("""
        CREATE TABLE art.impact_dependencies (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          impact_assessment_id UUID NOT NULL
            REFERENCES art.impact_assessments(id) ON DELETE CASCADE,
          correlation_id UUID NOT NULL,
          tenant_id VARCHAR(100) NOT NULL,
          environment VARCHAR(20) NOT NULL,
          dependent_component_id VARCHAR(150),
          dependent_component_name VARCHAR(250) NOT NULL,
          dependency_direction VARCHAR(50) NOT NULL,
          dependency_type VARCHAR(100),
          dependency_confidence DOUBLE PRECISION,
          source_of_dependency VARCHAR(100),
          knowledge_graph_ref TEXT,
          description TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CHECK (environment IN ('dev','test','preprod','prod')),
          CHECK (dependency_direction IN ('UPSTREAM','DOWNSTREAM','LATERAL','UNKNOWN')),
          CHECK (
            dependency_confidence IS NULL OR dependency_confidence BETWEEN 0 AND 1
          )
        )
    """)
    op.execute("""
        CREATE TABLE art.test_selection_decisions (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          correlation_id UUID NOT NULL,
          tenant_id VARCHAR(100) NOT NULL,
          environment VARCHAR(20) NOT NULL,
          agent_run_id UUID REFERENCES art.agent_runs(id) ON DELETE SET NULL,
          selection_strategy VARCHAR(100) NOT NULL,
          risk_score DOUBLE PRECISION,
          confidence_score DOUBLE PRECISION,
          selected_tests JSONB NOT NULL,
          skipped_tests JSONB NOT NULL DEFAULT '[]'::jsonb,
          mandatory_tests JSONB NOT NULL DEFAULT '[]'::jsonb,
          affected_components JSONB NOT NULL DEFAULT '[]'::jsonb,
          affected_capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
          risk_coverage DOUBLE PRECISION,
          estimated_duration_ms INTEGER,
          rationale TEXT,
          evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
          policy_decision_id UUID,
          policy_version VARCHAR(100),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CHECK (environment IN ('dev','test','preprod','prod')),
          CHECK (risk_score IS NULL OR risk_score BETWEEN 0 AND 1),
          CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1),
          CHECK (risk_coverage IS NULL OR risk_coverage BETWEEN 0 AND 1),
          CHECK (estimated_duration_ms IS NULL OR estimated_duration_ms >= 0)
        )
    """)
    op.execute("""
        CREATE TABLE art.execution_intents (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          correlation_id UUID NOT NULL,
          tenant_id VARCHAR(100) NOT NULL,
          environment VARCHAR(20) NOT NULL,
          agent_run_id UUID REFERENCES art.agent_runs(id) ON DELETE SET NULL,
          test_selection_decision_id UUID
            REFERENCES art.test_selection_decisions(id) ON DELETE SET NULL,
          execution_target VARCHAR(150) NOT NULL,
          execution_mode VARCHAR(100) NOT NULL DEFAULT 'ORCHESTRATED',
          selected_tests JSONB NOT NULL,
          sequence_plan JSONB NOT NULL DEFAULT '[]'::jsonb,
          constraints JSONB NOT NULL DEFAULT '{}'::jsonb,
          status VARCHAR(30) NOT NULL DEFAULT 'RECEIVED',
          policy_decision_id UUID,
          policy_version VARCHAR(100),
          approval_required BOOLEAN NOT NULL DEFAULT FALSE,
          approval_id UUID,
          approval_status VARCHAR(30) NOT NULL DEFAULT 'NOT_REQUIRED',
          requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          dispatched_at TIMESTAMPTZ,
          completed_at TIMESTAMPTZ,
          external_run_id VARCHAR(150),
          execution_result_ref TEXT,
          evidence_requirements JSONB NOT NULL DEFAULT '[]'::jsonb,
          evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CHECK (environment IN ('dev','test','preprod','prod')),
          CHECK (
            approval_status IN (
              'NOT_REQUIRED','PENDING','APPROVED','REJECTED','EXPIRED','CANCELLED'
            )
          )
        )
    """)
    op.execute("""
        CREATE TABLE art.execution_result_refs (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          correlation_id UUID NOT NULL,
          tenant_id VARCHAR(100) NOT NULL,
          environment VARCHAR(20) NOT NULL,
          execution_intent_id UUID
            REFERENCES art.execution_intents(id) ON DELETE SET NULL,
          external_run_id VARCHAR(150),
          status VARCHAR(30) NOT NULL,
          passed_count INTEGER,
          failed_count INTEGER,
          skipped_count INTEGER,
          failures_summary JSONB NOT NULL DEFAULT '[]'::jsonb,
          artifact_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
          result_ref TEXT,
          received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CHECK (environment IN ('dev','test','preprod','prod')),
          CHECK (passed_count IS NULL OR passed_count >= 0),
          CHECK (failed_count IS NULL OR failed_count >= 0),
          CHECK (skipped_count IS NULL OR skipped_count >= 0)
        )
    """)
    op.execute("""
        CREATE TABLE art.self_heal_proposals (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          correlation_id UUID NOT NULL,
          tenant_id VARCHAR(100) NOT NULL,
          environment VARCHAR(20) NOT NULL,
          agent_run_id UUID REFERENCES art.agent_runs(id) ON DELETE SET NULL,
          failure_event_id UUID REFERENCES art.failure_events(id) ON DELETE SET NULL,
          proposal_type VARCHAR(50) NOT NULL,
          proposal_summary TEXT NOT NULL,
          suggested_change JSONB NOT NULL,
          proposed_diff JSONB NOT NULL DEFAULT '{}'::jsonb,
          confidence_score DOUBLE PRECISION,
          confidence_reason TEXT,
          approval_required BOOLEAN NOT NULL DEFAULT TRUE,
          approval_id UUID,
          approval_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
          applied_status VARCHAR(30) NOT NULL DEFAULT 'RECEIVED',
          applied_at TIMESTAMPTZ,
          applied_by VARCHAR(150),
          rollback_ref TEXT,
          evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
          policy_decision_id UUID,
          policy_version VARCHAR(100),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CHECK (environment IN ('dev','test','preprod','prod')),
          CHECK (
            proposal_type IN (
              'LOCATOR','TEST_DATA','ASSERTION','MINOR_LOGIC','CONFIG_DEPENDENCY'
            )
          ),
          CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1)
        )
    """)
    op.execute("""
        CREATE TABLE art.outcome_feedback (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          correlation_id UUID NOT NULL,
          tenant_id VARCHAR(100) NOT NULL,
          environment VARCHAR(20) NOT NULL,
          agent_run_id UUID REFERENCES art.agent_runs(id) ON DELETE SET NULL,
          execution_intent_id UUID
            REFERENCES art.execution_intents(id) ON DELETE SET NULL,
          execution_result_ref_id UUID
            REFERENCES art.execution_result_refs(id) ON DELETE SET NULL,
          feedback_type VARCHAR(100) NOT NULL,
          feedback_summary TEXT,
          test_effectiveness JSONB NOT NULL DEFAULT '{}'::jsonb,
          flakiness_signals JSONB NOT NULL DEFAULT '{}'::jsonb,
          defect_detection_signals JSONB NOT NULL DEFAULT '{}'::jsonb,
          model_drift_signals JSONB NOT NULL DEFAULT '{}'::jsonb,
          recommended_action TEXT,
          published_to_kai BOOLEAN NOT NULL DEFAULT FALSE,
          published_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CHECK (environment IN ('dev','test','preprod','prod'))
        )
    """)
    op.execute("""
        CREATE TABLE art.event_inbox (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          event_id UUID NOT NULL UNIQUE,
          correlation_id UUID NOT NULL,
          tenant_id VARCHAR(100) NOT NULL,
          environment VARCHAR(20) NOT NULL,
          topic_name VARCHAR(150) NOT NULL,
          event_type VARCHAR(100) NOT NULL,
          payload JSONB NOT NULL,
          processing_status VARCHAR(30) NOT NULL DEFAULT 'RECEIVED',
          received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          processed_at TIMESTAMPTZ,
          error_message TEXT,
          CHECK (environment IN ('dev','test','preprod','prod'))
        )
    """)
    op.execute("""
        CREATE TABLE art.event_outbox (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          correlation_id UUID NOT NULL,
          tenant_id VARCHAR(100) NOT NULL,
          environment VARCHAR(20) NOT NULL,
          topic_name VARCHAR(150) NOT NULL,
          event_type VARCHAR(100) NOT NULL,
          payload JSONB NOT NULL,
          publish_status VARCHAR(30) NOT NULL DEFAULT 'RECEIVED',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          published_at TIMESTAMPTZ,
          error_message TEXT,
          CHECK (environment IN ('dev','test','preprod','prod'))
        )
    """)

    for table in (
        "failure_events",
        "agent_runs",
        "agent_run_steps",
        "agent_decision_journals",
        "impact_assessments",
        "impact_dependencies",
        "test_selection_decisions",
        "execution_intents",
        "execution_result_refs",
        "self_heal_proposals",
        "outcome_feedback",
        "event_inbox",
        "event_outbox",
    ):
        op.execute(f"CREATE INDEX ix_art_{table}_correlation ON art.{table} (correlation_id)")
        op.execute(
            f"CREATE INDEX ix_art_{table}_tenant_environment "
            f"ON art.{table} (tenant_id, environment)"
        )

    for table in (
        "failure_events",
        "agent_runs",
        "agent_run_steps",
        "execution_intents",
        "self_heal_proposals",
    ):
        op.execute(f"""
            CREATE TRIGGER trg_{table}_updated_at
            BEFORE UPDATE ON art.{table}
            FOR EACH ROW EXECUTE FUNCTION art.set_updated_at()
        """)

    op.execute("""
        CREATE VIEW art.v_agent_run_summary AS
        SELECT
          ar.id AS agent_run_id,
          ar.correlation_id,
          ar.tenant_id,
          ar.environment,
          ar.workflow_type,
          ar.status,
          ar.started_at,
          ar.completed_at,
          ar.execution_time_ms,
          ar.policy_decision_id,
          ar.policy_version,
          ar.approval_required,
          COUNT(ars.id) AS total_steps,
          COUNT(ars.id) FILTER (WHERE ars.status = 'SUCCESS') AS successful_steps,
          COUNT(ars.id) FILTER (WHERE ars.status = 'FAILED') AS failed_steps
        FROM art.agent_runs ar
        LEFT JOIN art.agent_run_steps ars ON ar.id = ars.agent_run_id
        GROUP BY ar.id
    """)
    op.execute("""
        CREATE VIEW art.v_correlation_trace AS
        SELECT
          ar.correlation_id,
          ar.tenant_id,
          ar.environment,
          ar.workflow_type,
          ar.status AS agent_run_status,
          tsd.id AS test_selection_decision_id,
          ei.id AS execution_intent_id,
          ei.status AS execution_status,
          shp.id AS self_heal_proposal_id,
          shp.approval_status AS self_heal_approval_status
        FROM art.agent_runs ar
        LEFT JOIN art.test_selection_decisions tsd
          ON ar.correlation_id = tsd.correlation_id
          AND ar.tenant_id = tsd.tenant_id
        LEFT JOIN art.execution_intents ei
          ON ar.correlation_id = ei.correlation_id
          AND ar.tenant_id = ei.tenant_id
        LEFT JOIN art.self_heal_proposals shp
          ON ar.correlation_id = shp.correlation_id
          AND ar.tenant_id = shp.tenant_id
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS art.v_correlation_trace")
    op.execute("DROP VIEW IF EXISTS art.v_agent_run_summary")
    for table in (
        "event_outbox",
        "event_inbox",
        "outcome_feedback",
        "self_heal_proposals",
        "execution_result_refs",
        "execution_intents",
        "test_selection_decisions",
        "impact_dependencies",
        "impact_assessments",
        "agent_decision_journals",
        "agent_run_steps",
        "agent_runs",
        "failure_events",
    ):
        op.execute(f"DROP TABLE IF EXISTS art.{table} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS art.set_updated_at")
    op.execute("DROP SCHEMA IF EXISTS art")
