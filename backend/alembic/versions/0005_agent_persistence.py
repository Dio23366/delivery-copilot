"""add agent persistence tables

Revision ID: 0005_agent_persistence
Revises: 0004_grounded_rag_analysis
Create Date: 2026-07-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0005_agent_persistence'
down_revision = '0004_grounded_rag_analysis'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'agent_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.String(length=36), nullable=False),
        sa.Column(
            'issue_id',
            sa.Integer(),
            sa.ForeignKey('issues.id'),
            nullable=False,
        ),
        sa.Column(
            'analysis_log_id',
            sa.Integer(),
            sa.ForeignKey('ai_analysis_logs.id'),
            nullable=True,
        ),
        sa.Column('graph_version', sa.String(length=100), nullable=False),
        sa.Column('current_node', sa.String(length=100), nullable=False),
        sa.Column(
            'run_status',
            sa.String(length=50),
            nullable=False,
            server_default='created',
        ),
        sa.Column(
            'step_count',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
        sa.Column(
            'tool_call_count',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
        sa.Column(
            'retry_count',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
        sa.Column(
            'state_json',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column('waiting_since', sa.DateTime(), nullable=True),
        sa.Column('resume_node', sa.String(length=100), nullable=True),
        sa.Column('error_code', sa.String(length=100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "run_status IN ("
            "'created', "
            "'running', "
            "'waiting_for_triage_confirmation', "
            "'waiting_for_clarification', "
            "'generating_analysis', "
            "'waiting_for_final_review', "
            "'completed', "
            "'failed', "
            "'cancelled', "
            "'limit_exceeded'"
            ")",
            name='ck_agent_runs_status_allowed',
        ),
        sa.CheckConstraint(
            'step_count >= 0',
            name='ck_agent_runs_step_count_nonnegative',
        ),
        sa.CheckConstraint(
            'tool_call_count >= 0',
            name='ck_agent_runs_tool_call_count_nonnegative',
        ),
        sa.CheckConstraint(
            'retry_count >= 0',
            name='ck_agent_runs_retry_count_nonnegative',
        ),
        sa.CheckConstraint(
            "run_status NOT IN ("
            "'waiting_for_triage_confirmation', "
            "'waiting_for_clarification', "
            "'waiting_for_final_review'"
            ') OR (waiting_since IS NOT NULL AND resume_node IS NOT NULL)',
            name='ck_agent_runs_waiting_resume_fields',
        ),
        sa.UniqueConstraint(
            'run_id',
            name='uq_agent_runs_run_id',
        ),
        sa.UniqueConstraint(
            'analysis_log_id',
            name='uq_agent_runs_analysis_log_id',
        ),
    )

    op.create_index(
        'ix_agent_runs_issue_id',
        'agent_runs',
        ['issue_id'],
        unique=False,
    )
    op.create_index(
        'ix_agent_runs_run_status',
        'agent_runs',
        ['run_status'],
        unique=False,
    )
    op.create_index(
        'ix_agent_runs_current_node',
        'agent_runs',
        ['current_node'],
        unique=False,
    )
    op.create_index(
        'ix_agent_runs_created_at',
        'agent_runs',
        ['created_at'],
        unique=False,
    )

    op.create_table(
        'agent_steps',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'agent_run_id',
            sa.Integer(),
            sa.ForeignKey('agent_runs.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('step_index', sa.Integer(), nullable=False),
        sa.Column('node_name', sa.String(length=100), nullable=False),
        sa.Column(
            'step_status',
            sa.String(length=50),
            nullable=False,
            server_default='running',
        ),
        sa.Column(
            'input_state_json',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            'output_state_json',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column('error_code', sa.String(length=100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            'step_index >= 1',
            name='ck_agent_steps_step_index_positive',
        ),
        sa.CheckConstraint(
            "step_status IN ("
            "'running', "
            "'completed', "
            "'interrupted', "
            "'failed', "
            "'cancelled'"
            ")",
            name='ck_agent_steps_status_allowed',
        ),
        sa.CheckConstraint(
            'completed_at IS NULL OR completed_at >= started_at',
            name='ck_agent_steps_completion_time_order',
        ),
        sa.CheckConstraint(
            "(step_status = 'running' AND completed_at IS NULL) OR "
            "(step_status IN ("
            "'completed', "
            "'interrupted', "
            "'failed', "
            "'cancelled'"
            ') AND completed_at IS NOT NULL)',
            name='ck_agent_steps_status_completion_consistency',
        ),
        sa.CheckConstraint(
            "step_status != 'failed' "
            'OR error_code IS NOT NULL '
            'OR error_message IS NOT NULL',
            name='ck_agent_steps_failed_error_present',
        ),
        sa.UniqueConstraint(
            'agent_run_id',
            'step_index',
            name='uq_agent_steps_run_step_index',
        ),
    )

    op.create_index(
        'ix_agent_steps_node_name',
        'agent_steps',
        ['node_name'],
        unique=False,
    )
    op.create_index(
        'ix_agent_steps_step_status',
        'agent_steps',
        ['step_status'],
        unique=False,
    )
    op.create_index(
        'ix_agent_steps_started_at',
        'agent_steps',
        ['started_at'],
        unique=False,
    )

    op.create_table(
        'agent_tool_calls',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'agent_step_id',
            sa.Integer(),
            sa.ForeignKey('agent_steps.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('tool_call_index', sa.Integer(), nullable=False),
        sa.Column('tool_name', sa.String(length=100), nullable=False),
        sa.Column('tool_version', sa.String(length=100), nullable=True),
        sa.Column(
            'call_status',
            sa.String(length=50),
            nullable=False,
            server_default='created',
        ),
        sa.Column(
            'arguments_json',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            'result_json',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            'read_only',
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            'requires_approval',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column('timeout_seconds', sa.Integer(), nullable=False),
        sa.Column('error_code', sa.String(length=100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            'tool_call_index >= 1',
            name='ck_agent_tool_calls_call_index_positive',
        ),
        sa.CheckConstraint(
            "call_status IN ("
            "'created', "
            "'running', "
            "'completed', "
            "'failed', "
            "'timed_out', "
            "'cancelled'"
            ")",
            name='ck_agent_tool_calls_status_allowed',
        ),
        sa.CheckConstraint(
            'completed_at IS NULL OR '
            '(started_at IS NOT NULL AND completed_at >= started_at)',
            name='ck_agent_tool_calls_completion_time_order',
        ),
        sa.CheckConstraint(
            "(call_status = 'created' "
            'AND started_at IS NULL '
            'AND completed_at IS NULL) OR '
            "(call_status = 'running' "
            'AND started_at IS NOT NULL '
            'AND completed_at IS NULL) OR '
            "(call_status IN ("
            "'completed', "
            "'failed', "
            "'timed_out', "
            "'cancelled'"
            ') '
            'AND started_at IS NOT NULL '
            'AND completed_at IS NOT NULL)',
            name='ck_agent_tool_calls_status_time_consistency',
        ),
        sa.CheckConstraint(
            "call_status != 'completed' OR result_json IS NOT NULL",
            name='ck_agent_tool_calls_completed_result_present',
        ),
        sa.CheckConstraint(
            "call_status NOT IN ('failed', 'timed_out') "
            'OR error_code IS NOT NULL '
            'OR error_message IS NOT NULL',
            name='ck_agent_tool_calls_failure_error_present',
        ),
        sa.CheckConstraint(
            'timeout_seconds > 0',
            name='ck_agent_tool_calls_timeout_positive',
        ),
        sa.UniqueConstraint(
            'agent_step_id',
            'tool_call_index',
            name='uq_agent_tool_calls_step_call_index',
        ),
    )

    op.create_index(
        'ix_agent_tool_calls_tool_name',
        'agent_tool_calls',
        ['tool_name'],
        unique=False,
    )
    op.create_index(
        'ix_agent_tool_calls_call_status',
        'agent_tool_calls',
        ['call_status'],
        unique=False,
    )
    op.create_index(
        'ix_agent_tool_calls_created_at',
        'agent_tool_calls',
        ['created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_agent_tool_calls_created_at',
        table_name='agent_tool_calls',
    )
    op.drop_index(
        'ix_agent_tool_calls_call_status',
        table_name='agent_tool_calls',
    )
    op.drop_index(
        'ix_agent_tool_calls_tool_name',
        table_name='agent_tool_calls',
    )
    op.drop_table('agent_tool_calls')

    op.drop_index(
        'ix_agent_steps_started_at',
        table_name='agent_steps',
    )
    op.drop_index(
        'ix_agent_steps_step_status',
        table_name='agent_steps',
    )
    op.drop_index(
        'ix_agent_steps_node_name',
        table_name='agent_steps',
    )
    op.drop_table('agent_steps')

    op.drop_index(
        'ix_agent_runs_created_at',
        table_name='agent_runs',
    )
    op.drop_index(
        'ix_agent_runs_current_node',
        table_name='agent_runs',
    )
    op.drop_index(
        'ix_agent_runs_run_status',
        table_name='agent_runs',
    )
    op.drop_index(
        'ix_agent_runs_issue_id',
        table_name='agent_runs',
    )
    op.drop_table('agent_runs')