from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class KnowledgeChunk(Base):
    __tablename__ = 'knowledge_chunks'
    __table_args__ = (
        UniqueConstraint('document_id', 'chunk_index', name='uq_knowledge_chunks_document_chunk_index'),
        CheckConstraint('chunk_index >= 0', name='ck_knowledge_chunks_chunk_index_nonnegative'),
        CheckConstraint('char_count IS NULL OR char_count >= 0', name='ck_knowledge_chunks_char_count_nonnegative'),
        CheckConstraint('token_count IS NULL OR token_count >= 0', name='ck_knowledge_chunks_token_count_nonnegative'),
        CheckConstraint('source_span_start IS NULL OR source_span_start >= 0', name='ck_knowledge_chunks_source_span_start_nonnegative'),
        CheckConstraint('source_span_end IS NULL OR source_span_end >= 0', name='ck_knowledge_chunks_source_span_end_nonnegative'),
        CheckConstraint(
            'embedding_dimension IS NULL OR embedding_dimension = 1536',
            name='ck_knowledge_chunks_embedding_dimension_1536',
        ),
        CheckConstraint(
            "((embedding IS NULL) = (embedding_provider IS NULL)) AND "
            "((embedding IS NULL) = (embedding_model IS NULL)) AND "
            "((embedding IS NULL) = (embedding_dimension IS NULL)) AND "
            "((embedding IS NULL) = (embedded_at IS NULL))",
            name='ck_knowledge_chunks_embedding_metadata_complete',
        ),
        Index('ix_knowledge_chunks_document_id', 'document_id'),
        Index('ix_knowledge_chunks_created_at', 'created_at'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('knowledge_documents.id', ondelete='CASCADE'),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    section_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_span_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_span_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON().with_variant(JSONB(), 'postgresql'), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536).with_variant(JSON(none_as_null=True), 'sqlite'), nullable=True)
    embedding_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    document = relationship('KnowledgeDocument', back_populates='chunks')
