"""knowledge base schema foundation

Revision ID: 0002_knowledge_base_schema
Revises: 0001_baseline_schema
Create Date: 2026-07-16 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0002_knowledge_base_schema'
down_revision = '0001_baseline_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'knowledge_documents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('scope_type', sa.String(length=20), nullable=False),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('doc_type', sa.String(length=50), nullable=False),
        sa.Column('source_kind', sa.String(length=50), nullable=False),
        sa.Column('source_uri', sa.Text(), nullable=True),
        sa.Column('source_name', sa.String(length=255), nullable=True),
        sa.Column('content_text', sa.Text(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('version_label', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('ingested_at', sa.DateTime(), nullable=True),
        sa.Column('last_indexed_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "(scope_type = 'global' AND customer_id IS NULL AND project_id IS NULL) OR "
            "(scope_type = 'customer' AND customer_id IS NOT NULL AND project_id IS NULL) OR "
            "(scope_type = 'project' AND project_id IS NOT NULL AND customer_id IS NULL)",
            name='ck_knowledge_documents_scope_relation',
        ),
        sa.CheckConstraint("scope_type IN ('global', 'customer', 'project')", name='ck_knowledge_documents_scope_type_allowed'),
        sa.CheckConstraint(
            "doc_type IN ('api_doc', 'deployment_guide', 'troubleshooting_guide', 'solution_note', 'product_guide')",
            name='ck_knowledge_documents_doc_type_allowed',
        ),
        sa.CheckConstraint(
            "source_kind IN ('manual', 'uploaded', 'internal_wiki', 'generated')",
            name='ck_knowledge_documents_source_kind_allowed',
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'failed', 'archived')",
            name='ck_knowledge_documents_status_allowed',
        ),
    )
    op.create_index('ix_knowledge_documents_scope_type', 'knowledge_documents', ['scope_type'], unique=False)
    op.create_index('ix_knowledge_documents_customer_id', 'knowledge_documents', ['customer_id'], unique=False)
    op.create_index('ix_knowledge_documents_project_id', 'knowledge_documents', ['project_id'], unique=False)
    op.create_index('ix_knowledge_documents_status', 'knowledge_documents', ['status'], unique=False)
    op.create_index('ix_knowledge_documents_doc_type', 'knowledge_documents', ['doc_type'], unique=False)
    op.create_index('ix_knowledge_documents_content_hash', 'knowledge_documents', ['content_hash'], unique=False)
    op.create_index('ix_knowledge_documents_created_at', 'knowledge_documents', ['created_at'], unique=False)

    op.create_table(
        'knowledge_chunks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('document_id', sa.Integer(), sa.ForeignKey('knowledge_documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('chunk_title', sa.String(length=255), nullable=True),
        sa.Column('section_path', sa.String(length=500), nullable=True),
        sa.Column('page_number', sa.Integer(), nullable=True),
        sa.Column('token_count', sa.Integer(), nullable=True),
        sa.Column('char_count', sa.Integer(), nullable=True),
        sa.Column('source_span_start', sa.Integer(), nullable=True),
        sa.Column('source_span_end', sa.Integer(), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('chunk_index >= 0', name='ck_knowledge_chunks_chunk_index_nonnegative'),
        sa.CheckConstraint('char_count IS NULL OR char_count >= 0', name='ck_knowledge_chunks_char_count_nonnegative'),
        sa.CheckConstraint('token_count IS NULL OR token_count >= 0', name='ck_knowledge_chunks_token_count_nonnegative'),
        sa.CheckConstraint('source_span_start IS NULL OR source_span_start >= 0', name='ck_knowledge_chunks_source_span_start_nonnegative'),
        sa.CheckConstraint('source_span_end IS NULL OR source_span_end >= 0', name='ck_knowledge_chunks_source_span_end_nonnegative'),
        sa.UniqueConstraint('document_id', 'chunk_index', name='uq_knowledge_chunks_document_chunk_index'),
    )
    op.create_index('ix_knowledge_chunks_document_id', 'knowledge_chunks', ['document_id'], unique=False)
    op.create_index('ix_knowledge_chunks_created_at', 'knowledge_chunks', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_knowledge_chunks_created_at', table_name='knowledge_chunks')
    op.drop_index('ix_knowledge_chunks_document_id', table_name='knowledge_chunks')
    op.drop_table('knowledge_chunks')

    op.drop_index('ix_knowledge_documents_created_at', table_name='knowledge_documents')
    op.drop_index('ix_knowledge_documents_content_hash', table_name='knowledge_documents')
    op.drop_index('ix_knowledge_documents_doc_type', table_name='knowledge_documents')
    op.drop_index('ix_knowledge_documents_status', table_name='knowledge_documents')
    op.drop_index('ix_knowledge_documents_project_id', table_name='knowledge_documents')
    op.drop_index('ix_knowledge_documents_customer_id', table_name='knowledge_documents')
    op.drop_index('ix_knowledge_documents_scope_type', table_name='knowledge_documents')
    op.drop_table('knowledge_documents')
