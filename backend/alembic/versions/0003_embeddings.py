"""add knowledge chunk embeddings

Revision ID: 0003_embeddings
Revises: 0002_knowledge_base_schema
Create Date: 2026-07-16 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = '0003_embeddings'
down_revision = '0002_knowledge_base_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text('CREATE EXTENSION IF NOT EXISTS vector'))
    op.add_column('knowledge_chunks', sa.Column('embedding', Vector(1536), nullable=True))
    op.add_column('knowledge_chunks', sa.Column('embedding_provider', sa.String(length=50), nullable=True))
    op.add_column('knowledge_chunks', sa.Column('embedding_model', sa.String(length=100), nullable=True))
    op.add_column('knowledge_chunks', sa.Column('embedding_dimension', sa.Integer(), nullable=True))
    op.add_column('knowledge_chunks', sa.Column('embedded_at', sa.DateTime(), nullable=True))
    op.create_check_constraint(
        'ck_knowledge_chunks_embedding_dimension_1536',
        'knowledge_chunks',
        'embedding_dimension IS NULL OR embedding_dimension = 1536',
    )
    op.create_check_constraint(
        'ck_knowledge_chunks_embedding_metadata_complete',
        'knowledge_chunks',
        '((embedding IS NULL) = (embedding_provider IS NULL)) AND '
        '((embedding IS NULL) = (embedding_model IS NULL)) AND '
        '((embedding IS NULL) = (embedding_dimension IS NULL)) AND '
        '((embedding IS NULL) = (embedded_at IS NULL))',
    )


def downgrade() -> None:
    op.drop_constraint('ck_knowledge_chunks_embedding_metadata_complete', 'knowledge_chunks', type_='check')
    op.drop_constraint('ck_knowledge_chunks_embedding_dimension_1536', 'knowledge_chunks', type_='check')
    op.drop_column('knowledge_chunks', 'embedded_at')
    op.drop_column('knowledge_chunks', 'embedding_dimension')
    op.drop_column('knowledge_chunks', 'embedding_model')
    op.drop_column('knowledge_chunks', 'embedding_provider')
    op.drop_column('knowledge_chunks', 'embedding')
