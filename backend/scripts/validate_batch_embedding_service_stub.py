from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.embeddings.base import BaseEmbeddingProvider
from app.embeddings.openai_provider import (
    EmbeddingConfigurationError,
    EmbeddingProviderError,
)
from app.embeddings.schemas import EmbeddingResult
from app.models import Base, KnowledgeChunk, KnowledgeDocument
from app.services.embedding_service import EmbeddingService


class SequencedStubProvider(BaseEmbeddingProvider):
    def __init__(self, outcomes: list[EmbeddingResult | Exception]) -> None:
        self.provider_name = 'aliyun_model_studio'
        self.model_name = 'text-embedding-v4'
        self.dimension = 1536
        self.outcomes = outcomes
        self.calls = 0

    def embed_text(self, text: str) -> EmbeddingResult:
        if self.calls >= len(self.outcomes):
            raise AssertionError('unexpected additional provider call')

        outcome = self.outcomes[self.calls]
        self.calls += 1

        if isinstance(outcome, Exception):
            raise outcome

        return outcome


def build_result(
    value: float = 0.1,
    *,
    dimension: int = 1536,
) -> EmbeddingResult:
    return EmbeddingResult(
        embedding=[value] * dimension,
        provider='aliyun_model_studio',
        model='text-embedding-v4',
        dimension=dimension,
    )


def create_session() -> Session:
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def add_document(
    db: Session,
    chunk_texts: list[str],
) -> tuple[KnowledgeDocument, list[KnowledgeChunk]]:
    document = KnowledgeDocument(
        scope_type='global',
        title='Batch embedding stub document',
        doc_type='troubleshooting_guide',
        source_kind='manual',
        content_text='\n'.join(chunk_texts),
        content_hash='a' * 64,
        status='ready',
    )
    db.add(document)
    db.flush()

    chunks = [
        KnowledgeChunk(
            document_id=document.id,
            chunk_index=index,
            chunk_text=text,
            char_count=len(text),
        )
        for index, text in enumerate(chunk_texts)
    ]

    db.add_all(chunks)
    db.commit()
    db.refresh(document)

    for chunk in chunks:
        db.refresh(chunk)

    return document, chunks


def set_existing_embedding(
    chunk: KnowledgeChunk,
    value: float,
) -> None:
    chunk.embedding = [value] * 1536
    chunk.embedding_provider = 'aliyun_model_studio'
    chunk.embedding_model = 'text-embedding-v4'
    chunk.embedding_dimension = 1536
    chunk.embedded_at = datetime(2026, 1, 1, 0, 0, 0)


def assert_count_invariant(result) -> None:
    assert result.total == result.succeeded + result.skipped + result.failed


def test_all_success() -> None:
    db = create_session()
    try:
        document, chunks = add_document(
            db,
            ['chunk zero', 'chunk one', 'chunk two'],
        )
        provider = SequencedStubProvider(
            [
                build_result(0.1),
                build_result(0.2),
                build_result(0.3),
            ]
        )

        result = EmbeddingService(provider=provider).embed_document(
            document.id,
            db,
        )

        assert result.total == 3
        assert result.succeeded == 3
        assert result.skipped == 0
        assert result.failed == 0
        assert result.status == 'completed'
        assert result.failures == []
        assert provider.calls == 3
        assert_count_invariant(result)

        stored = (
            db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.document_id == document.id)
            .order_by(KnowledgeChunk.chunk_index.asc())
            .all()
        )

        assert len(stored) == 3
        assert all(chunk.embedding is not None for chunk in stored)
        assert all(len(chunk.embedding) == 1536 for chunk in stored)
        assert all(chunk.embedding_dimension == 1536 for chunk in stored)
        assert all(chunk.embedded_at is not None for chunk in stored)
    finally:
        db.close()


def test_partial_failure_and_retry() -> None:
    db = create_session()
    try:
        document, chunks = add_document(
            db,
            ['first succeeds', 'second fails', 'third succeeds'],
        )
        provider = SequencedStubProvider(
            [
                build_result(0.1),
                EmbeddingProviderError('simulated provider failure'),
                build_result(0.3),
            ]
        )

        result = EmbeddingService(provider=provider).embed_document(
            document.id,
            db,
        )

        assert result.total == 3
        assert result.succeeded == 2
        assert result.skipped == 0
        assert result.failed == 1
        assert result.status == 'partial_success'
        assert provider.calls == 3
        assert_count_invariant(result)

        assert len(result.failures) == 1
        assert result.failures[0].chunk_id == chunks[1].id
        assert result.failures[0].status_code == 502
        assert result.failures[0].detail == 'Embedding provider failed'

        stored = (
            db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.document_id == document.id)
            .order_by(KnowledgeChunk.chunk_index.asc())
            .all()
        )

        assert stored[0].embedding is not None
        assert stored[1].embedding is None
        assert stored[1].embedding_provider is None
        assert stored[1].embedding_model is None
        assert stored[1].embedding_dimension is None
        assert stored[1].embedded_at is None
        assert stored[2].embedding is not None

        retry_provider = SequencedStubProvider([build_result(0.2)])
        retry_result = EmbeddingService(
            provider=retry_provider
        ).embed_document(
            document.id,
            db,
        )

        assert retry_result.total == 3
        assert retry_result.succeeded == 1
        assert retry_result.skipped == 2
        assert retry_result.failed == 0
        assert retry_result.status == 'completed'
        assert retry_provider.calls == 1
        assert_count_invariant(retry_result)

        retried_chunk = (
            db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.id == chunks[1].id)
            .first()
        )
        assert retried_chunk is not None
        assert retried_chunk.embedding is not None
        assert len(retried_chunk.embedding) == 1536
    finally:
        db.close()


def test_all_failed() -> None:
    db = create_session()
    try:
        document, chunks = add_document(
            db,
            ['config failure', 'invalid provider result'],
        )
        provider = SequencedStubProvider(
            [
                EmbeddingConfigurationError('simulated missing config'),
                build_result(0.1, dimension=1535),
            ]
        )

        result = EmbeddingService(provider=provider).embed_document(
            document.id,
            db,
        )

        assert result.total == 2
        assert result.succeeded == 0
        assert result.skipped == 0
        assert result.failed == 2
        assert result.status == 'failed'
        assert provider.calls == 2
        assert_count_invariant(result)

        assert [failure.chunk_id for failure in result.failures] == [
            chunks[0].id,
            chunks[1].id,
        ]
        assert [failure.status_code for failure in result.failures] == [
            503,
            422,
        ]

        stored = (
            db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.document_id == document.id)
            .all()
        )
        assert all(chunk.embedding is None for chunk in stored)
        assert all(chunk.embedding_provider is None for chunk in stored)
        assert all(chunk.embedding_model is None for chunk in stored)
        assert all(chunk.embedding_dimension is None for chunk in stored)
        assert all(chunk.embedded_at is None for chunk in stored)
    finally:
        db.close()


def test_skip_existing_embeddings() -> None:
    db = create_session()
    try:
        document, chunks = add_document(
            db,
            ['already embedded zero', 'missing embedding', 'already embedded two'],
        )

        set_existing_embedding(chunks[0], 0.7)
        set_existing_embedding(chunks[2], 0.9)
        db.commit()

        provider = SequencedStubProvider([build_result(0.8)])
        result = EmbeddingService(provider=provider).embed_document(
            document.id,
            db,
            force=False,
        )

        assert result.total == 3
        assert result.succeeded == 1
        assert result.skipped == 2
        assert result.failed == 0
        assert result.status == 'completed'
        assert provider.calls == 1
        assert_count_invariant(result)

        stored = (
            db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.document_id == document.id)
            .order_by(KnowledgeChunk.chunk_index.asc())
            .all()
        )

        assert stored[0].embedding == [0.7] * 1536
        assert stored[1].embedding == [0.8] * 1536
        assert stored[2].embedding == [0.9] * 1536
    finally:
        db.close()


def test_force_failure_preserves_existing_embedding() -> None:
    db = create_session()
    try:
        document, chunks = add_document(
            db,
            ['existing embedding must survive'],
        )
        set_existing_embedding(chunks[0], 0.6)
        db.commit()

        original_embedded_at = chunks[0].embedded_at

        provider = SequencedStubProvider(
            [EmbeddingProviderError('simulated force failure')]
        )
        result = EmbeddingService(provider=provider).embed_document(
            document.id,
            db,
            force=True,
        )

        assert result.total == 1
        assert result.succeeded == 0
        assert result.skipped == 0
        assert result.failed == 1
        assert result.status == 'failed'
        assert provider.calls == 1
        assert_count_invariant(result)

        stored = (
            db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.id == chunks[0].id)
            .first()
        )

        assert stored is not None
        assert stored.embedding == [0.6] * 1536
        assert stored.embedding_provider == 'aliyun_model_studio'
        assert stored.embedding_model == 'text-embedding-v4'
        assert stored.embedding_dimension == 1536
        assert stored.embedded_at == original_embedded_at
    finally:
        db.close()


def test_document_not_found() -> None:
    db = create_session()
    try:
        provider = SequencedStubProvider([])
        service = EmbeddingService(provider=provider)

        try:
            service.embed_document(999, db)
            raise AssertionError('expected 404')
        except HTTPException as exc:
            assert exc.status_code == 404
            assert exc.detail == 'Knowledge document not found'

        assert provider.calls == 0
    finally:
        db.close()


def main() -> None:
    test_all_success()
    test_partial_failure_and_retry()
    test_all_failed()
    test_skip_existing_embeddings()
    test_force_failure_preserves_existing_embedding()
    test_document_not_found()

    print('BatchEmbeddingService SQLite stub assertions passed')


if __name__ == '__main__':
    main()
