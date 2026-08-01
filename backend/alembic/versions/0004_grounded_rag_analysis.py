"""add grounded rag analysis fields

Revision ID: 0004_grounded_rag_analysis
Revises: 0003_embeddings
Create Date: 2026-07-20 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '0004_grounded_rag_analysis'
down_revision = '0003_embeddings'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('ai_analysis_logs', sa.Column('retrieval_status', sa.String(length=50), nullable=False, server_default='not_attempted'))
    op.add_column('ai_analysis_logs', sa.Column('retrieval_query', sa.Text(), nullable=True))
    op.add_column('ai_analysis_logs', sa.Column('knowledge_citations_json', sa.Text(), nullable=False, server_default='[]'))
    op.add_column('ai_analysis_logs', sa.Column('retrieval_error_code', sa.String(length=100), nullable=True))
    op.create_check_constraint(
        'ck_ai_analysis_logs_retrieval_status',
        'ai_analysis_logs',
        "retrieval_status IN ('not_attempted', 'succeeded', 'no_results', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint('ck_ai_analysis_logs_retrieval_status', 'ai_analysis_logs', type_='check')
    op.drop_column('ai_analysis_logs', 'retrieval_error_code')
    op.drop_column('ai_analysis_logs', 'knowledge_citations_json')
    op.drop_column('ai_analysis_logs', 'retrieval_query')
    op.drop_column('ai_analysis_logs', 'retrieval_status')
