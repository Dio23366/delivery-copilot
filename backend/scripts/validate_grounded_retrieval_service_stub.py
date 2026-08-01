from __future__ import annotations

import math
from dataclasses import asdict

from fastapi import HTTPException

from app.ai.grounded_retrieval_service import GroundedRetrievalService
from app.ai.retrieval_query_builder import build_issue_retrieval_query
from app.ai.schemas import GroundedRetrievalOutcome, KnowledgeCitationSnapshot, KnowledgeEvidence
from app.models import Customer, Issue, Project
from app.schemas.knowledge import KnowledgeSearchContext, KnowledgeSearchRequest, KnowledgeSearchResponse, KnowledgeSearchResult, ScopeType


class FakeIssue:
    def __init__(self):
        self.id = 42
        self.title = '  Payment timeout  '
        self.description = '  Payments fail after deploy  '
        self.issue_type = '  incident '
        self.severity = ' high '
        self.status = ' open '
        self.owner = ' ops '


class FakeProject:
    def __init__(self):
        self.id = 7
        self.name = '  Billing Platform '
        self.status = 'active'
        self.delivery_stage = ' rollout '
        self.risk_level = 'medium'
        self.health = 'green'


class FakeCustomer:
    def __init__(self):
        self.id = 3
        self.name = '  Acme Corp '
        self.industry = ' finance '


class StubKnowledgeSearchService:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.calls = []

    def search(self, payload, db):
        self.calls.append((payload, db))
        if self.exc:
            raise self.exc
        return self.response


class FakeSession:
    def __init__(self):
        self.commit_calls = 0
        self.rollback_calls = 0
        self.add_calls = 0

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1

    def add(self, *_args, **_kwargs):
        self.add_calls += 1


class FakeResult:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def make_context() -> KnowledgeSearchContext:
    return KnowledgeSearchContext(
        customer_id=None,
        project_id=None,
        issue_id=101,
        resolved_scope_types=[
            ScopeType.global_scope,
        ],
    )


def make_result(rows, *, context: KnowledgeSearchContext | None = None):
    resolved_context = context if context is not None else make_context()
    return KnowledgeSearchResponse(
        query='retrieval query',
        top_k=5,
        min_similarity=None,
        context=resolved_context,
        result_count=len(rows),
        results=rows,
    )


def build_row(rank, chunk_id, document_id, scope_type, doc_type, source_kind, chunk_text, distance):
    return KnowledgeSearchResult(
        rank=rank,
        chunk_id=chunk_id,
        document_id=document_id,
        document_title=f'Doc {document_id}',
        scope_type=scope_type,
        customer_id=3,
        project_id=7,
        doc_type=doc_type,
        source_kind=source_kind,
        source_name='notes.md',
        source_uri='https://example.com',
        chunk_index=rank - 1,
        chunk_text=chunk_text,
        distance=distance,
        similarity_score=1 - distance,
    )


def assert_outcome_equal(left: GroundedRetrievalOutcome, right: GroundedRetrievalOutcome) -> None:
    assert left == right
    assert [item.citation_id for item in left.knowledge_evidence] == [item.citation_id for item in right.knowledge_evidence]


def assert_success_case() -> None:
    issue = FakeIssue()
    project = FakeProject()
    customer = FakeCustomer()
    rows = [
        build_row(1, 101, 201, 'global', 'solution_note', 'manual', 'alpha chunk', 0.1),
        build_row(2, 102, 202, 'customer', 'deployment_guide', 'generated', 'beta chunk', 0.2),
        build_row(3, 103, 203, 'project', 'api_doc', 'internal_wiki', 'gamma chunk', 0.3),
    ]
    response = make_result(rows)
    stub = StubKnowledgeSearchService(response=response)
    service = GroundedRetrievalService(knowledge_search_service=stub)
    db = FakeSession()
    outcome = service.retrieve(issue, project, customer, db)
    assert len(stub.calls) == 1
    payload, call_db = stub.calls[0]
    assert payload.query == build_issue_retrieval_query(issue, project, customer)
    assert payload.issue_id == issue.id
    assert payload.top_k == 5
    assert call_db is db
    assert outcome.retrieval_status == 'succeeded'
    assert outcome.retrieval_error_code is None
    assert len(outcome.knowledge_evidence) == 3
    assert len(outcome.knowledge_citations) == 3
    assert [item.citation_id for item in outcome.knowledge_evidence] == ['K1', 'K2', 'K3']
    assert [item.citation_id for item in outcome.knowledge_citations] == ['K1', 'K2', 'K3']
    assert outcome.knowledge_evidence[0].distance == 0.1
    assert outcome.knowledge_citations[0].similarity_score == 0.9
    assert 'distance' not in asdict(outcome.knowledge_citations[0])


def assert_enum_to_string_cases() -> None:
    class EnumLike:
        def __init__(self, value: str) -> None:
            self.value = value

    enum_row = KnowledgeSearchResult.model_construct(
        rank=1,
        chunk_id=1,
        document_id=1,
        document_title='d',
        scope_type=EnumLike('global'),
        customer_id=1,
        project_id=1,
        doc_type=EnumLike('solution_note'),
        source_kind=EnumLike('manual'),
        source_name=None,
        source_uri=None,
        chunk_index=0,
        chunk_text='text',
        distance=0.1,
        similarity_score=0.9,
    )

    enum_response = KnowledgeSearchResponse.model_construct(
        query='q',
        top_k=5,
        min_similarity=None,
        context=make_context(),
        result_count=1,
        results=[enum_row],
    )

    enum_service = GroundedRetrievalService(
        knowledge_search_service=StubKnowledgeSearchService(
            response=enum_response,
        )
    )

    enum_outcome = enum_service.retrieve(
        FakeIssue(),
        FakeProject(),
        FakeCustomer(),
        FakeSession(),
    )

    enum_evidence = enum_outcome.knowledge_evidence[0]
    enum_citation = enum_outcome.knowledge_citations[0]

    assert enum_evidence.scope_type == 'global'
    assert enum_evidence.doc_type == 'solution_note'
    assert enum_evidence.source_kind == 'manual'
    assert isinstance(enum_evidence.scope_type, str)
    assert isinstance(enum_evidence.doc_type, str)
    assert isinstance(enum_evidence.source_kind, str)

    assert enum_citation.scope_type == 'global'
    assert enum_citation.doc_type == 'solution_note'
    assert enum_citation.source_kind == 'manual'
    assert isinstance(enum_citation.scope_type, str)
    assert isinstance(enum_citation.doc_type, str)
    assert isinstance(enum_citation.source_kind, str)

    string_row = build_row(
        1,
        1,
        1,
        'global',
        'solution_note',
        'manual',
        'text',
        0.1,
    )

    string_response = make_result(
        [string_row],
        context=make_context(),
    )

    string_service = GroundedRetrievalService(
        knowledge_search_service=StubKnowledgeSearchService(
            response=string_response,
        )
    )

    string_outcome = string_service.retrieve(
        FakeIssue(),
        FakeProject(),
        FakeCustomer(),
        FakeSession(),
    )

    string_evidence = string_outcome.knowledge_evidence[0]

    assert string_evidence.scope_type == 'global'
    assert string_evidence.doc_type == 'solution_note'
    assert string_evidence.source_kind == 'manual'
    assert isinstance(string_evidence.scope_type, str)
    assert isinstance(string_evidence.doc_type, str)
    assert isinstance(string_evidence.source_kind, str)


def assert_empty_case() -> None:
    service = GroundedRetrievalService(knowledge_search_service=StubKnowledgeSearchService(make_result([], context=make_context())))
    outcome = service.retrieve(FakeIssue(), FakeProject(), FakeCustomer(), FakeSession())
    assert outcome.retrieval_status == 'no_results'
    assert outcome.knowledge_evidence == ()
    assert outcome.knowledge_citations == ()
    assert outcome.retrieval_error_code is None


def assert_http_mappings() -> None:
    cases = [
        (404, 'retrieval_context_not_found'),
        (422, 'invalid_retrieval_response'),
        (500, 'retrieval_internal_error'),
        (502, 'embedding_provider_failed'),
        (503, 'embedding_provider_not_configured'),
        (418, 'retrieval_http_error'),
    ]
    for status_code, expected in cases:
        service = GroundedRetrievalService(knowledge_search_service=StubKnowledgeSearchService(exc=HTTPException(status_code=status_code, detail='x')))
        outcome = service.retrieve(FakeIssue(), FakeProject(), FakeCustomer(), FakeSession())
        assert outcome.retrieval_status == 'failed'
        assert outcome.retrieval_error_code == expected
        assert outcome.knowledge_evidence == ()
        assert outcome.knowledge_citations == ()


def assert_non_http_mapping() -> None:
    service = GroundedRetrievalService(knowledge_search_service=StubKnowledgeSearchService(exc=RuntimeError('boom')))
    outcome = service.retrieve(FakeIssue(), FakeProject(), FakeCustomer(), FakeSession())
    assert outcome.retrieval_error_code == 'retrieval_unexpected_error'


def assert_invalid_response_cases() -> None:
    base_row = build_row(1, 1, 1, 'global', 'solution_note', 'manual', 'alpha', 0.1)
    responses = [
        KnowledgeSearchResponse.model_construct(query='q', top_k=5, min_similarity=None, context=make_context(), result_count=2, results=[base_row]),
        KnowledgeSearchResponse.model_construct(query='q', top_k=1, min_similarity=None, context=make_context(), result_count=1, results=[base_row, base_row]),
        KnowledgeSearchResponse.model_construct(query='q', top_k=5, min_similarity=None, context=make_context(), result_count=1, results=[FakeResult(rank=2, chunk_id=1, document_id=1, document_title='d', scope_type='global', customer_id=1, project_id=1, doc_type='solution_note', source_kind='manual', source_name=None, source_uri=None, chunk_index=0, chunk_text='t', distance=0.1, similarity_score=0.9)]),
        KnowledgeSearchResponse.model_construct(query='q', top_k=5, min_similarity=None, context=make_context(), result_count=1, results=[FakeResult(rank=1, chunk_id=1, document_id=1, document_title='d', scope_type='global', customer_id=1, project_id=1, doc_type='solution_note', source_kind='manual', source_name=None, source_uri=None, chunk_index=0, chunk_text='   ', distance=0.1, similarity_score=0.9)]),
        KnowledgeSearchResponse.model_construct(query='q', top_k=5, min_similarity=None, context=make_context(), result_count=1, results=[FakeResult(rank=1, chunk_id=1, document_id=1, document_title='d', scope_type='global', customer_id=1, project_id=1, doc_type='solution_note', source_kind='manual', source_name=None, source_uri=None, chunk_index=0, chunk_text='t', distance=True, similarity_score=0.9)]),
        KnowledgeSearchResponse.model_construct(query='q', top_k=5, min_similarity=None, context=make_context(), result_count=1, results=[FakeResult(rank=1, chunk_id=1, document_id=1, document_title='d', scope_type='global', customer_id=1, project_id=1, doc_type='solution_note', source_kind='manual', source_name=None, source_uri=None, chunk_index=0, chunk_text='t', distance=float('nan'), similarity_score=0.9)]),
        KnowledgeSearchResponse.model_construct(query='q', top_k=5, min_similarity=None, context=make_context(), result_count=1, results=[FakeResult(rank=1, chunk_id=1, document_id=1, document_title='d', scope_type='global', customer_id=1, project_id=1, doc_type='solution_note', source_kind='manual', source_name=None, source_uri=None, chunk_index=0, chunk_text='t', distance=0.1, similarity_score=float('inf'))]),
        KnowledgeSearchResponse.model_construct(query='q', top_k=5, min_similarity=None, context=make_context(), result_count=1, results=[FakeResult(rank=1, chunk_id=1, document_id=1, document_title='d', scope_type='global', customer_id=1, project_id=1, doc_type='solution_note', source_kind='manual', source_name=None, source_uri=None, chunk_index=0, chunk_text='t', distance=0.1, similarity_score=0.1)]),
    ]
    for response in responses:
        service = GroundedRetrievalService(knowledge_search_service=StubKnowledgeSearchService(response=response))
        outcome = service.retrieve(FakeIssue(), FakeProject(), FakeCustomer(), FakeSession())
        assert outcome.retrieval_status == 'failed'
        assert outcome.retrieval_error_code == 'invalid_retrieval_response'
        assert outcome.knowledge_evidence == ()
        assert outcome.knowledge_citations == ()


def assert_no_db_writes() -> None:
    db = FakeSession()
    service = GroundedRetrievalService(knowledge_search_service=StubKnowledgeSearchService(make_result([], context=make_context())))
    service.retrieve(FakeIssue(), FakeProject(), FakeCustomer(), db)
    assert db.commit_calls == 0
    assert db.rollback_calls == 0
    assert db.add_calls == 0


def assert_determinism() -> None:
    rows = [
        build_row(1, 101, 201, 'global', 'solution_note', 'manual', 'alpha chunk', 0.1),
        build_row(2, 102, 202, 'customer', 'deployment_guide', 'generated', 'beta chunk', 0.2),
    ]
    response = make_result(rows, context=make_context())
    service = GroundedRetrievalService(knowledge_search_service=StubKnowledgeSearchService(response=response))
    left = service.retrieve(FakeIssue(), FakeProject(), FakeCustomer(), FakeSession())
    right = service.retrieve(FakeIssue(), FakeProject(), FakeCustomer(), FakeSession())
    assert_outcome_equal(left, right)


def main() -> None:
    assert_success_case()
    assert_enum_to_string_cases()
    assert_empty_case()
    assert_http_mappings()
    assert_non_http_mapping()
    assert_invalid_response_cases()
    assert_no_db_writes()
    assert_determinism()
    print('Grounded retrieval service stub assertions passed')


if __name__ == '__main__':
    main()
