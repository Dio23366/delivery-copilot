from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class KnowledgeDocument(Base):
    __tablename__ = 'knowledge_documents'
    __table_args__ = (
        CheckConstraint(
            "(scope_type = 'global' AND customer_id IS NULL AND project_id IS NULL) OR "
            "(scope_type = 'customer' AND customer_id IS NOT NULL AND project_id IS NULL) OR "
            "(scope_type = 'project' AND project_id IS NOT NULL AND customer_id IS NULL)",
            name='ck_knowledge_documents_scope_relation',
        ),
        CheckConstraint("scope_type IN ('global', 'customer', 'project')", name='ck_knowledge_documents_scope_type_allowed'),
        CheckConstraint(
            "doc_type IN ('api_doc', 'deployment_guide', 'troubleshooting_guide', 'solution_note', 'product_guide')",
            name='ck_knowledge_documents_doc_type_allowed',
        ),
        CheckConstraint(
            "source_kind IN ('manual', 'uploaded', 'internal_wiki', 'generated')",
            name='ck_knowledge_documents_source_kind_allowed',
        ),
        CheckConstraint(
            "status IN ('pending', 'ready', 'failed', 'archived')",
            name='ck_knowledge_documents_status_allowed',
        ),
        Index('ix_knowledge_documents_scope_type', 'scope_type'),
        Index('ix_knowledge_documents_customer_id', 'customer_id'),
        Index('ix_knowledge_documents_project_id', 'project_id'),
        Index('ix_knowledge_documents_status', 'status'),
        Index('ix_knowledge_documents_doc_type', 'doc_type'),
        Index('ix_knowledge_documents_content_hash', 'content_hash'),
        Index('ix_knowledge_documents_created_at', 'created_at'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('customers.id'), nullable=True)
    project_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('projects.id'), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending', server_default='pending')
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    customer = relationship('Customer')
    project = relationship('Project')
    chunks = relationship('KnowledgeChunk', back_populates='document', cascade='all, delete-orphan', passive_deletes=True)
