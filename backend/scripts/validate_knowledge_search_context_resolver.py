from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, Customer, Issue, Project
from app.schemas.knowledge import KnowledgeSearchRequest, ScopeType
from app.services.knowledge_search_context_resolver import (
    KnowledgeSearchContextResolver,
)


def expect_http_exception(
    factory: Callable[[], object],
    *,
    status_code: int,
    detail: str,
) -> None:
    try:
        factory()
        raise AssertionError(
            f'expected HTTP {status_code}: {detail}'
        )
    except HTTPException as exc:
        assert exc.status_code == status_code
        assert exc.detail == detail


def create_session() -> Session:
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    return session_factory()


def seed_context_data(db: Session) -> None:
    customer = Customer(
        id=1,
        name='Resolver Test Customer',
        industry='Technology',
        contact=None,
        status='active',
        owner='Delivery Team',
    )

    project_with_customer = Project(
        id=10,
        customer_id=1,
        name='Project With Customer',
        status='active',
        health='healthy',
        risk_level='low',
        delivery_stage='Implementation',
    )

    project_without_customer = Project(
        id=11,
        customer_id=None,
        name='Standalone Project',
        status='active',
        health='healthy',
        risk_level='low',
        delivery_stage='Implementation',
    )

    issue_with_customer_project = Issue(
        id=100,
        project_id=10,
        title='Issue With Customer Project',
        description='Resolver test issue.',
        issue_type='API',
        status='open',
        severity='high',
        owner='Engineering',
    )

    issue_with_standalone_project = Issue(
        id=101,
        project_id=11,
        title='Issue With Standalone Project',
        description='Resolver test issue.',
        issue_type='Deployment',
        status='open',
        severity='medium',
        owner='Engineering',
    )

    issue_without_project = Issue(
        id=102,
        project_id=None,
        title='Issue Without Project',
        description='Resolver test issue.',
        issue_type='Configuration',
        status='open',
        severity='low',
        owner='Engineering',
    )

    invalid_relation_issue = Issue(
        id=103,
        project_id=999,
        title='Issue With Invalid Project Relation',
        description='Resolver test issue.',
        issue_type='Data',
        status='open',
        severity='high',
        owner='Engineering',
    )

    db.add_all(
        [
            customer,
            project_with_customer,
            project_without_customer,
            issue_with_customer_project,
            issue_with_standalone_project,
            issue_without_project,
            invalid_relation_issue,
        ]
    )
    db.commit()


def main() -> None:
    db = create_session()
    resolver = KnowledgeSearchContextResolver()

    try:
        seed_context_data(db)

        global_context = resolver.resolve(
            KnowledgeSearchRequest(query='global query'),
            db,
        )

        assert global_context.customer_id is None
        assert global_context.project_id is None
        assert global_context.issue_id is None
        assert global_context.resolved_scope_types == [
            ScopeType.global_scope
        ]

        customer_context = resolver.resolve(
            KnowledgeSearchRequest(
                query='customer query',
                customer_id=1,
            ),
            db,
        )

        assert customer_context.customer_id == 1
        assert customer_context.project_id is None
        assert customer_context.issue_id is None
        assert customer_context.resolved_scope_types == [
            ScopeType.global_scope,
            ScopeType.customer,
        ]

        project_context = resolver.resolve(
            KnowledgeSearchRequest(
                query='project query',
                project_id=10,
            ),
            db,
        )

        assert project_context.customer_id == 1
        assert project_context.project_id == 10
        assert project_context.issue_id is None
        assert project_context.resolved_scope_types == [
            ScopeType.global_scope,
            ScopeType.customer,
            ScopeType.project,
        ]

        standalone_project_context = resolver.resolve(
            KnowledgeSearchRequest(
                query='standalone project query',
                project_id=11,
            ),
            db,
        )

        assert standalone_project_context.customer_id is None
        assert standalone_project_context.project_id == 11
        assert standalone_project_context.issue_id is None
        assert standalone_project_context.resolved_scope_types == [
            ScopeType.global_scope,
            ScopeType.project,
        ]

        issue_context = resolver.resolve(
            KnowledgeSearchRequest(
                query='issue query',
                issue_id=100,
            ),
            db,
        )

        assert issue_context.customer_id == 1
        assert issue_context.project_id == 10
        assert issue_context.issue_id == 100
        assert issue_context.resolved_scope_types == [
            ScopeType.global_scope,
            ScopeType.customer,
            ScopeType.project,
        ]

        standalone_issue_context = resolver.resolve(
            KnowledgeSearchRequest(
                query='standalone issue query',
                issue_id=101,
            ),
            db,
        )

        assert standalone_issue_context.customer_id is None
        assert standalone_issue_context.project_id == 11
        assert standalone_issue_context.issue_id == 101
        assert standalone_issue_context.resolved_scope_types == [
            ScopeType.global_scope,
            ScopeType.project,
        ]

        issue_without_project_context = resolver.resolve(
            KnowledgeSearchRequest(
                query='issue without project query',
                issue_id=102,
            ),
            db,
        )

        assert issue_without_project_context.customer_id is None
        assert issue_without_project_context.project_id is None
        assert issue_without_project_context.issue_id == 102
        assert issue_without_project_context.resolved_scope_types == [
            ScopeType.global_scope
        ]

        expect_http_exception(
            lambda: resolver.resolve(
                KnowledgeSearchRequest(
                    query='missing customer',
                    customer_id=999,
                ),
                db,
            ),
            status_code=404,
            detail='Customer not found',
        )

        expect_http_exception(
            lambda: resolver.resolve(
                KnowledgeSearchRequest(
                    query='missing project',
                    project_id=999,
                ),
                db,
            ),
            status_code=404,
            detail='Project not found',
        )

        expect_http_exception(
            lambda: resolver.resolve(
                KnowledgeSearchRequest(
                    query='missing issue',
                    issue_id=999,
                ),
                db,
            ),
            status_code=404,
            detail='Issue not found',
        )

        expect_http_exception(
            lambda: resolver.resolve(
                KnowledgeSearchRequest(
                    query='invalid issue relation',
                    issue_id=103,
                ),
                db,
            ),
            status_code=500,
            detail='Issue project relation is invalid',
        )

        print(
            'Knowledge search context resolver SQLite assertions passed'
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
