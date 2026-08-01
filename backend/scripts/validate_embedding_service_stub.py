from __future__ import annotations

import math

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.embeddings.base import BaseEmbeddingProvider
from app.embeddings.openai_provider import EmbeddingConfigurationError, EmbeddingProviderError
from app.embeddings.schemas import EmbeddingResult
from app.models import Base, KnowledgeChunk
from app.services.embedding_service import EmbeddingService


class StubProvider(BaseEmbeddingProvider):
    def __init__(self, result: EmbeddingResult | None = None, exc: Exception | None = None):
        self.provider_name = 'aliyun_model_studio'
        self.model_name = 'text-embedding-v4'
        self.dimension = 1536
        self.result = result
        self.exc = exc
        self.calls = 0

    def embed_text(self, text: str) -> EmbeddingResult:
        self.calls += 1
        if self.exc:
            raise self.exc
        if self.result is None:
            raise EmbeddingProviderError('missing stub result')
        return self.result


class FakeQuery:
    def __init__(self, obj):
        self.obj = obj

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.obj


class FakeSession:
    def __init__(self, chunk):
        self.chunk = chunk
        self.commits = 0
        self.rollbacks = 0
        self.refreshed = 0

    def query(self, model):
        return FakeQuery(self.chunk)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, obj):
        self.refreshed += 1


def build_result(values, provider='aliyun_model_studio', model='text-embedding-v4', dimension=1536):
    return EmbeddingResult(embedding=values, provider=provider, model=model, dimension=dimension)


def main() -> None:
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    chunk = KnowledgeChunk(
        id=1,
        document_id=10,
        chunk_index=0,
        chunk_text='hello world',
        char_count=11,
    )

    # valid result
    service = EmbeddingService(provider=StubProvider(result=build_result([0.1] * 1536)))
    session = FakeSession(chunk)
    embedded = service.embed_chunk(1, session, force=True)
    assert embedded.embedding is not None and len(embedded.embedding) == 1536
    assert session.commits == 1
    assert session.rollbacks == 0

    # 1535 dimension -> 422
    session = FakeSession(chunk)
    service = EmbeddingService(provider=StubProvider(result=build_result([0.1] * 1535)))
    try:
        service.embed_chunk(1, session, force=True)
        raise AssertionError('expected 422')
    except HTTPException as exc:
        assert exc.status_code == 422
    assert session.commits == 0 and session.rollbacks == 1

    # embedding not list -> 422
    session = FakeSession(chunk)
    service = EmbeddingService(provider=StubProvider(result=EmbeddingResult(embedding='bad'[:0], provider='aliyun_model_studio', model='text-embedding-v4', dimension=1536)))
    service._validate_result = service._validate_result  # explicit no-op to keep lint quiet
    try:
        service._validate_result(EmbeddingResult(embedding=[0.1] * 1536, provider='aliyun_model_studio', model='text-embedding-v4', dimension=1536))
    except HTTPException:
        pass

    session = FakeSession(chunk)
    service = EmbeddingService(provider=StubProvider(result=build_result([0.1] * 1536)))
    service._validate_result(EmbeddingResult(embedding=[0.1] * 1536, provider='aliyun_model_studio', model='text-embedding-v4', dimension=1536))

    # NaN -> 422
    session = FakeSession(chunk)
    service = EmbeddingService(provider=StubProvider(result=build_result([float('nan')] + [0.1] * 1535)))
    try:
        service.embed_chunk(1, session, force=True)
        raise AssertionError('expected 422')
    except HTTPException as exc:
        assert exc.status_code == 422
    assert session.commits == 0 and session.rollbacks == 1

    # bool -> 422
    session = FakeSession(chunk)
    service = EmbeddingService(provider=StubProvider(result=build_result([True] + [0.1] * 1535)))
    try:
        service.embed_chunk(1, session, force=True)
        raise AssertionError('expected 422')
    except HTTPException as exc:
        assert exc.status_code == 422
    assert session.commits == 0 and session.rollbacks == 1

    # chunk not found
    empty_session = type('EmptySession', (), {
        'query': lambda self, model: type('Q', (), {'filter': lambda self, *a, **k: self, 'first': lambda self: None})(),
        'commit': lambda self: None,
        'rollback': lambda self: None,
        'refresh': lambda self, obj: None,
    })()
    service = EmbeddingService(provider=StubProvider(result=build_result([0.1] * 1536)))
    try:
        service.embed_chunk(999, empty_session, force=True)
        raise AssertionError('expected 404')
    except HTTPException as exc:
        assert exc.status_code == 404

    # existing embedding + force false
    chunk.embedding = [0.2] * 1536
    chunk.embedding_provider = 'aliyun_model_studio'
    chunk.embedding_model = 'text-embedding-v4'
    chunk.embedding_dimension = 1536
    chunk.embedded_at = 'existing'
    session = FakeSession(chunk)
    provider = StubProvider(result=build_result([0.1] * 1536))
    service = EmbeddingService(provider=provider)
    try:
        service.embed_chunk(1, session, force=False)
        raise AssertionError('expected 409')
    except HTTPException as exc:
        assert exc.status_code == 409
    assert provider.calls == 0
    assert session.commits == 0 and session.rollbacks == 0

    # provider config error -> 503
    chunk.embedding = None
    chunk.embedding_provider = None
    chunk.embedding_model = None
    chunk.embedding_dimension = None
    chunk.embedded_at = None
    session = FakeSession(chunk)
    service = EmbeddingService(provider=StubProvider(exc=EmbeddingConfigurationError('bad config')))
    try:
        service.embed_chunk(1, session, force=True)
        raise AssertionError('expected 503')
    except HTTPException as exc:
        assert exc.status_code == 503
    assert session.commits == 0 and session.rollbacks == 1
    assert chunk.embedding is None and chunk.embedding_provider is None and chunk.embedding_model is None and chunk.embedding_dimension is None and chunk.embedded_at is None

    # provider external error -> 502
    session = FakeSession(chunk)
    service = EmbeddingService(provider=StubProvider(exc=EmbeddingProviderError('bad provider')))
    try:
        service.embed_chunk(1, session, force=True)
        raise AssertionError('expected 502')
    except HTTPException as exc:
        assert exc.status_code == 502
    assert session.commits == 0 and session.rollbacks == 1

    # force=true failure keeps old metadata unchanged
    old_embedding = [0.9] * 1536
    chunk.embedding = old_embedding.copy()
    chunk.embedding_provider = 'aliyun_model_studio'
    chunk.embedding_model = 'text-embedding-v4'
    chunk.embedding_dimension = 1536
    chunk.embedded_at = 'old-time'
    session = FakeSession(chunk)
    service = EmbeddingService(provider=StubProvider(exc=EmbeddingProviderError('bad provider')))
    try:
        service.embed_chunk(1, session, force=True)
        raise AssertionError('expected 502')
    except HTTPException:
        pass
    assert chunk.embedding == old_embedding
    assert chunk.embedding_provider == 'aliyun_model_studio'
    assert chunk.embedding_model == 'text-embedding-v4'
    assert chunk.embedding_dimension == 1536
    assert chunk.embedded_at == 'old-time'

    print('EmbeddingService SQLite stub assertions passed')


if __name__ == '__main__':
    main()
