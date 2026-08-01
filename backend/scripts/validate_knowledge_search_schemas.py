from __future__ import annotations

from math import inf, nan

from pydantic import ValidationError

from app.schemas.knowledge import (
    DocType,
    KnowledgeSearchContext,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSearchResult,
    ScopeType,
    SourceKind,
)


def expect_validation_error(factory) -> None:
    try:
        factory()
        raise AssertionError('expected Pydantic ValidationError')
    except ValidationError:
        pass


def build_result(rank: int = 1) -> KnowledgeSearchResult:
    return KnowledgeSearchResult(
        rank=rank,
        chunk_id=6,
        document_id=4,
        document_title='Deployment Troubleshooting Guide',
        scope_type=ScopeType.project,
        customer_id=None,
        project_id=10,
        doc_type=DocType.troubleshooting_guide,
        source_kind=SourceKind.manual,
        source_name='Internal Guide',
        source_uri=None,
        chunk_index=2,
        chunk_text='Relevant deployment troubleshooting knowledge.',
        distance=0.1234,
        similarity_score=0.8766,
    )


def main() -> None:
    request = KnowledgeSearchRequest(
        query='  API authentication failed after deployment  ',
        issue_id=18,
    )

    assert request.query == 'API authentication failed after deployment'
    assert request.issue_id == 18
    assert request.customer_id is None
    assert request.project_id is None
    assert request.top_k == 5
    assert request.min_similarity is None

    KnowledgeSearchRequest(query='global search')
    KnowledgeSearchRequest(query='customer search', customer_id=3)
    KnowledgeSearchRequest(query='project search', project_id=10)
    KnowledgeSearchRequest(
        query='threshold search',
        min_similarity=-0.5,
        top_k=20,
    )

    expect_validation_error(
        lambda: KnowledgeSearchRequest(query='   ')
    )
    expect_validation_error(
        lambda: KnowledgeSearchRequest(
            query='conflicting context',
            customer_id=3,
            project_id=10,
        )
    )
    expect_validation_error(
        lambda: KnowledgeSearchRequest(query='invalid id', issue_id=0)
    )
    expect_validation_error(
        lambda: KnowledgeSearchRequest(query='invalid id', project_id=-1)
    )
    expect_validation_error(
        lambda: KnowledgeSearchRequest(query='invalid top k', top_k=0)
    )
    expect_validation_error(
        lambda: KnowledgeSearchRequest(query='invalid top k', top_k=21)
    )
    expect_validation_error(
        lambda: KnowledgeSearchRequest(
            query='invalid similarity',
            min_similarity=-1.1,
        )
    )
    expect_validation_error(
        lambda: KnowledgeSearchRequest(
            query='invalid similarity',
            min_similarity=1.1,
        )
    )
    expect_validation_error(
        lambda: KnowledgeSearchRequest(
            query='invalid similarity',
            min_similarity=nan,
        )
    )
    expect_validation_error(
        lambda: KnowledgeSearchRequest(
            query='invalid similarity',
            min_similarity=inf,
        )
    )
    expect_validation_error(
        lambda: KnowledgeSearchRequest(
            query='unknown field',
            unknown_field='bad',
        )
    )

    context = KnowledgeSearchContext(
        customer_id=3,
        project_id=10,
        issue_id=18,
        resolved_scope_types=[
            ScopeType.global_scope,
            ScopeType.customer,
            ScopeType.project,
        ],
    )

    expect_validation_error(
        lambda: KnowledgeSearchContext(
            resolved_scope_types=[
                ScopeType.global_scope,
                ScopeType.global_scope,
            ]
        )
    )

    result = build_result()

    response = KnowledgeSearchResponse(
        query=request.query,
        top_k=5,
        min_similarity=None,
        context=context,
        result_count=1,
        results=[result],
    )

    assert response.result_count == 1
    assert response.results[0].rank == 1
    assert response.results[0].similarity_score == 0.8766

    empty_response = KnowledgeSearchResponse(
        query='no result query',
        top_k=5,
        min_similarity=None,
        context=KnowledgeSearchContext(
            resolved_scope_types=[ScopeType.global_scope],
        ),
        result_count=0,
        results=[],
    )

    assert empty_response.result_count == 0

    expect_validation_error(
        lambda: KnowledgeSearchResponse(
            query='mismatched count',
            top_k=5,
            context=context,
            result_count=0,
            results=[result],
        )
    )

    expect_validation_error(
        lambda: KnowledgeSearchResponse(
            query='too many results',
            top_k=1,
            context=context,
            result_count=2,
            results=[
                build_result(rank=1),
                build_result(rank=2),
            ],
        )
    )

    expect_validation_error(
        lambda: KnowledgeSearchResponse(
            query='invalid ranks',
            top_k=5,
            context=context,
            result_count=1,
            results=[build_result(rank=2)],
        )
    )

    print('Knowledge search schema assertions passed')


if __name__ == '__main__':
    main()
