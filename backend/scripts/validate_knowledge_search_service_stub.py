from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.embeddings.schemas import EmbeddingResult
from app.schemas.knowledge import (
    KnowledgeSearchContext,
    KnowledgeSearchRequest,
    ScopeType,
)
from app.services.knowledge_search_service import KnowledgeSearchService


class StubProvider:
    def __init__(self, result=None, exc=None):
        self.result = result
        self.exc = exc
        self.calls = 0
        self.last_text = None

    def embed_text(self, text: str):
        self.calls += 1
        self.last_text = text
        if self.exc:
            raise self.exc
        return self.result


class StubResolver:
    def __init__(self, context):
        self.context = context
        self.calls = 0

    def resolve(self, payload, db):
        self.calls += 1
        return self.context


class FakeQuery:
    def __init__(self, rows=None, raises=None):
        self.rows = rows or []
        self.raises = raises
        self.joins = []
        self.filters = []
        self.order_bys = []
        self.limits = []

    def join(self, *args, **kwargs):
        self.joins.append((args, kwargs))
        return self

    def filter(self, *clauses):
        self.filters.extend(clauses)
        return self

    def order_by(self, *clauses):
        self.order_bys.extend(clauses)
        return self

    def limit(self, value):
        self.limits.append(value)
        return self

    def all(self):
        if self.raises:
            raise self.raises
        return self.rows


class FakeSession:
    def __init__(self, query):
        self.query_obj = query
        self.rollback_calls = 0

    def query(self, *args, **kwargs):
        return self.query_obj

    def rollback(self):
        self.rollback_calls += 1


class Row:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class CompileSession(Session):
    pass


def make_result(vector, provider='aliyun_model_studio', model='text-embedding-v4', dimension=1536):
    return EmbeddingResult(embedding=vector, provider=provider, model=model, dimension=dimension)


def assert_valid_result(response, expected_count):
    assert response.result_count == expected_count
    assert len(response.results) == expected_count
    assert [item.rank for item in response.results] == list(range(1, expected_count + 1))
    for item in response.results:
        assert item.similarity_score == 1 - item.distance
        assert item.chunk_text is not None


def main() -> None:
    context = KnowledgeSearchContext(
        customer_id=None,
        project_id=None,
        issue_id=None,
        resolved_scope_types=[ScopeType.global_scope],
    )

    rows = [
        Row(chunk_id=1, document_id=10, document_title='Doc A', scope_type='global', customer_id=None, project_id=None, doc_type='solution_note', source_kind='manual', source_name='a.txt', source_uri='u1', chunk_index=0, chunk_text='chunk a', distance=0.05),
        Row(chunk_id=2, document_id=11, document_title='Doc B', scope_type='global', customer_id=None, project_id=None, doc_type='solution_note', source_kind='manual', source_name='b.txt', source_uri='u2', chunk_index=1, chunk_text='chunk b', distance=0.1),
    ]
    provider = StubProvider(result=make_result([0.1] * 1536))
    resolver = StubResolver(context)
    service = KnowledgeSearchService(provider=provider, context_resolver=resolver)
    payload = KnowledgeSearchRequest(query='  hello world  ', top_k=5)
    response = service.search(payload, FakeSession(FakeQuery(rows=rows)))
    assert provider.calls == 1
    assert provider.last_text == 'hello world'
    assert resolver.calls == 1
    assert_valid_result(response, 2)
    assert response.results[0].rank == 1
    assert response.results[1].rank == 2
    assert response.results[0].distance == 0.05
    assert response.results[0].similarity_score == 0.95
    assert not hasattr(response.results[0], 'embedding')

    empty_provider = StubProvider(result=make_result([0.2] * 1536))
    response = KnowledgeSearchService(provider=empty_provider, context_resolver=resolver).search(
        KnowledgeSearchRequest(query='x', top_k=5),
        FakeSession(FakeQuery(rows=[])),
    )
    assert response.result_count == 0
    assert response.results == []

    error_cases = [
        (StubProvider(exc=__import__('app.embeddings.openai_provider', fromlist=['EmbeddingConfigurationError']).EmbeddingConfigurationError('x')), 503),
        (StubProvider(exc=__import__('app.embeddings.openai_provider', fromlist=['EmbeddingProviderError']).EmbeddingProviderError('x')), 502),
        (StubProvider(result=make_result([0.1] * 1535)), 422),
        (StubProvider(result=make_result('not-a-list')), 422),
        (StubProvider(result=make_result([float('nan')] + [0.1] * 1535)), 422),
        (StubProvider(result=make_result([True] + [0.1] * 1535)), 422),
    ]
    for provider, expected in error_cases:
        service = KnowledgeSearchService(provider=provider, context_resolver=resolver)
        try:
            service.search(KnowledgeSearchRequest(query='x'), FakeSession(FakeQuery(rows=[])))
            raise AssertionError('expected error')
        except HTTPException as exc:
            assert exc.status_code == expected

    failing_db = FakeSession(FakeQuery(raises=RuntimeError('db failed')))
    service = KnowledgeSearchService(provider=StubProvider(result=make_result([0.1] * 1536)), context_resolver=resolver)
    try:
        service.search(KnowledgeSearchRequest(query='x'), failing_db)
        raise AssertionError('expected 500')
    except HTTPException as exc:
        assert exc.status_code == 500
    assert failing_db.rollback_calls == 1

    def compile_query(context, payload):
        service = KnowledgeSearchService(provider=StubProvider(result=make_result([0.1] * 1536)), context_resolver=StubResolver(context))
        db = Session()
        try:
            query = service._build_query(
                payload=payload,
                context=context,
                query_embedding=[0.1] * 1536,
                db=db,
            )
            statement = query.statement
            assert statement is not None
            compiled = statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': False})
            return compiled, str(compiled)
        finally:
            db.close()

    global_compiled, global_sql = compile_query(
        KnowledgeSearchContext(customer_id=None, project_id=None, issue_id=None, resolved_scope_types=[ScopeType.global_scope]),
        KnowledgeSearchRequest(query='x', top_k=5),
    )
    assert 'JOIN knowledge_documents' in global_sql or 'JOIN' in global_sql
    assert 'knowledge_documents.status' in global_sql
    assert 'knowledge_chunks.embedding' in global_sql
    assert '<=>' in global_sql
    assert 'ORDER BY' in global_sql
    assert 'LIMIT' in global_sql
    assert 'customer_id IS NULL' in global_sql
    assert 'project_id IS NULL' in global_sql

    customer_compiled, customer_sql = compile_query(
        KnowledgeSearchContext(customer_id=3, project_id=None, issue_id=None, resolved_scope_types=[ScopeType.global_scope, ScopeType.customer]),
        KnowledgeSearchRequest(query='x', top_k=5),
    )
    assert 'customer_id' in customer_sql
    assert 3 in customer_compiled.params.values()

    project_compiled, project_sql = compile_query(
        KnowledgeSearchContext(customer_id=3, project_id=10, issue_id=None, resolved_scope_types=[ScopeType.global_scope, ScopeType.customer, ScopeType.project]),
        KnowledgeSearchRequest(query='x', top_k=5),
    )
    assert 'project_id' in project_sql
    assert 3 in project_compiled.params.values()
    assert 10 in project_compiled.params.values()

    min_sim_compiled, _ = compile_query(
        KnowledgeSearchContext(customer_id=None, project_id=None, issue_id=None, resolved_scope_types=[ScopeType.global_scope]),
        KnowledgeSearchRequest(query='x', top_k=5, min_similarity=0.8),
    )
    numeric_values = [value for value in min_sim_compiled.params.values() if isinstance(value, (int, float)) and not isinstance(value, bool)]
    assert any(abs(float(value) - 0.2) < 1e-9 for value in numeric_values)

    print('Knowledge search service assertions passed')


if __name__ == '__main__':
    main()
