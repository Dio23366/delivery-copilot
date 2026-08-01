"""allow cancelling created agent tool calls

Revision ID: 0006_agent_tool_cancel
Revises: 0005_agent_persistence
Create Date: 2026-07-25 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '0006_agent_tool_cancel'
down_revision = '0005_agent_persistence'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        'ck_agent_tool_calls_status_time_consistency',
        'agent_tool_calls',
        type_='check',
    )
    op.drop_constraint(
        'ck_agent_tool_calls_completion_time_order',
        'agent_tool_calls',
        type_='check',
    )

    op.create_check_constraint(
        'ck_agent_tool_calls_completion_time_order',
        'agent_tool_calls',
        (
            'completed_at IS NULL '
            'OR started_at IS NULL '
            'OR completed_at >= started_at'
        ),
    )
    op.create_check_constraint(
        'ck_agent_tool_calls_status_time_consistency',
        'agent_tool_calls',
        (
            "(call_status = 'created' "
            'AND started_at IS NULL '
            'AND completed_at IS NULL) OR '
            "(call_status = 'running' "
            'AND started_at IS NOT NULL '
            'AND completed_at IS NULL) OR '
            "(call_status IN ("
            "'completed', "
            "'failed', "
            "'timed_out'"
            ') '
            'AND started_at IS NOT NULL '
            'AND completed_at IS NOT NULL) OR '
            "(call_status = 'cancelled' "
            'AND completed_at IS NOT NULL)'
        ),
    )


def downgrade() -> None:
    connection = op.get_bind()

    incompatible_count = connection.execute(
        sa.text(
            """
            SELECT count(*)
            FROM agent_tool_calls
            WHERE call_status = 'cancelled'
              AND started_at IS NULL
            """
        )
    ).scalar_one()

    if incompatible_count:
        raise RuntimeError(
            'Cannot downgrade to 0005_agent_persistence: '
            'agent_tool_calls contains cancelled records '
            'that never started'
        )

    op.drop_constraint(
        'ck_agent_tool_calls_status_time_consistency',
        'agent_tool_calls',
        type_='check',
    )
    op.drop_constraint(
        'ck_agent_tool_calls_completion_time_order',
        'agent_tool_calls',
        type_='check',
    )

    op.create_check_constraint(
        'ck_agent_tool_calls_completion_time_order',
        'agent_tool_calls',
        (
            'completed_at IS NULL OR '
            '(started_at IS NOT NULL '
            'AND completed_at >= started_at)'
        ),
    )
    op.create_check_constraint(
        'ck_agent_tool_calls_status_time_consistency',
        'agent_tool_calls',
        (
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
            'AND completed_at IS NOT NULL)'
        ),
    )