"""add agent run terminal consistency constraints

Revision ID: 0007_agent_run_terminal
Revises: 0006_agent_tool_cancel
Create Date: 2026-07-25 00:00:00.000000
"""

from alembic import op


revision = '0007_agent_run_terminal'
down_revision = '0006_agent_tool_cancel'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        'ck_agent_runs_waiting_resume_fields',
        'agent_runs',
        type_='check',
    )

    op.create_check_constraint(
        'ck_agent_runs_completion_time_order',
        'agent_runs',
        (
            'completed_at IS NULL '
            'OR started_at IS NULL '
            'OR completed_at >= started_at'
        ),
    )

    op.create_check_constraint(
        'ck_agent_runs_status_time_consistency',
        'agent_runs',
        (
            "(run_status = 'created' "
            'AND completed_at IS NULL) OR '
            "(run_status IN ("
            "'running', "
            "'waiting_for_triage_confirmation', "
            "'waiting_for_clarification', "
            "'generating_analysis', "
            "'waiting_for_final_review'"
            ') '
            'AND started_at IS NOT NULL '
            'AND completed_at IS NULL) OR '
            "(run_status IN ("
            "'completed', "
            "'failed', "
            "'limit_exceeded'"
            ') '
            'AND started_at IS NOT NULL '
            'AND completed_at IS NOT NULL) OR '
            "(run_status = 'cancelled' "
            'AND completed_at IS NOT NULL)'
        ),
    )

    op.create_check_constraint(
        'ck_agent_runs_waiting_resume_fields',
        'agent_runs',
        (
            "(run_status IN ("
            "'waiting_for_triage_confirmation', "
            "'waiting_for_clarification', "
            "'waiting_for_final_review'"
            ') '
            'AND waiting_since IS NOT NULL '
            'AND resume_node IS NOT NULL) OR '
            "(run_status NOT IN ("
            "'waiting_for_triage_confirmation', "
            "'waiting_for_clarification', "
            "'waiting_for_final_review'"
            ') '
            'AND waiting_since IS NULL '
            'AND resume_node IS NULL)'
        ),
    )

    op.create_check_constraint(
        'ck_agent_runs_failure_error_present',
        'agent_runs',
        (
            "run_status NOT IN ('failed', 'limit_exceeded') "
            'OR error_code IS NOT NULL '
            'OR error_message IS NOT NULL'
        ),
    )

    op.create_check_constraint(
        'ck_agent_runs_terminal_error_absent',
        'agent_runs',
        (
            "run_status NOT IN ('completed', 'cancelled') "
            'OR ('
            'error_code IS NULL '
            'AND error_message IS NULL'
            ')'
        ),
    )


def downgrade() -> None:
    op.drop_constraint(
        'ck_agent_runs_terminal_error_absent',
        'agent_runs',
        type_='check',
    )
    op.drop_constraint(
        'ck_agent_runs_failure_error_present',
        'agent_runs',
        type_='check',
    )
    op.drop_constraint(
        'ck_agent_runs_waiting_resume_fields',
        'agent_runs',
        type_='check',
    )
    op.drop_constraint(
        'ck_agent_runs_status_time_consistency',
        'agent_runs',
        type_='check',
    )
    op.drop_constraint(
        'ck_agent_runs_completion_time_order',
        'agent_runs',
        type_='check',
    )

    op.create_check_constraint(
        'ck_agent_runs_waiting_resume_fields',
        'agent_runs',
        (
            "run_status NOT IN ("
            "'waiting_for_triage_confirmation', "
            "'waiting_for_clarification', "
            "'waiting_for_final_review'"
            ') OR ('
            'waiting_since IS NOT NULL '
            'AND resume_node IS NOT NULL'
            ')'
        ),
    )