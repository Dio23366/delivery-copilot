"""baseline application schema

Revision ID: 0001_baseline_schema
Revises:
Create Date: 2026-07-15 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '0001_baseline_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute(sa.text('CREATE EXTENSION IF NOT EXISTS vector'))

    op.create_table(
        'customers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('industry', sa.String(length=100), nullable=True),
        sa.Column('contact', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('owner', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_customers_id', 'customers', ['id'], unique=False)

    op.create_table(
        'projects',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('health', sa.String(length=50), nullable=False),
        sa.Column('risk_level', sa.String(length=50), nullable=True),
        sa.Column('delivery_stage', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_projects_id', 'projects', ['id'], unique=False)

    op.create_table(
        'requirements',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('priority', sa.String(length=50), nullable=False),
        sa.Column('owner', sa.String(length=255), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_requirements_id', 'requirements', ['id'], unique=False)

    op.create_table(
        'issues',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('issue_type', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=50), nullable=False),
        sa.Column('owner', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_issues_id', 'issues', ['id'], unique=False)

    op.create_table(
        'ai_analysis_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('issue_id', sa.Integer(), sa.ForeignKey('issues.id'), nullable=False),
        sa.Column('analysis_type', sa.String(length=100), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('model_name', sa.String(length=255), nullable=True),
        sa.Column('prompt_version', sa.String(length=100), nullable=True),
        sa.Column('issue_summary', sa.Text(), nullable=False),
        sa.Column('possible_root_cause', sa.Text(), nullable=False),
        sa.Column('recommended_actions_json', sa.Text(), nullable=False),
        sa.Column('customer_update_draft', sa.Text(), nullable=False),
        sa.Column('risk_level', sa.String(length=50), nullable=False),
        sa.Column('project_impact', sa.Text(), nullable=False),
        sa.Column('feedback_status', sa.String(length=50), nullable=False),
        sa.Column('feedback_note', sa.Text(), nullable=True),
        sa.Column('edited_output', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_ai_analysis_logs_id', 'ai_analysis_logs', ['id'], unique=False)
    op.create_index('ix_ai_analysis_logs_issue_id', 'ai_analysis_logs', ['issue_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_ai_analysis_logs_issue_id', table_name='ai_analysis_logs')
    op.drop_index('ix_ai_analysis_logs_id', table_name='ai_analysis_logs')
    op.drop_table('ai_analysis_logs')

    op.drop_index('ix_issues_id', table_name='issues')
    op.drop_table('issues')

    op.drop_index('ix_requirements_id', table_name='requirements')
    op.drop_table('requirements')

    op.drop_index('ix_projects_id', table_name='projects')
    op.drop_table('projects')

    op.drop_index('ix_customers_id', table_name='customers')
    op.drop_table('customers')
