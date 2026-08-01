from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Customer, Issue, Project
from app.schemas.knowledge import (
    KnowledgeSearchContext,
    KnowledgeSearchRequest,
    ScopeType,
)


class KnowledgeSearchContextResolver:
    def resolve(
        self,
        payload: KnowledgeSearchRequest,
        db: Session,
    ) -> KnowledgeSearchContext:
        if payload.issue_id is not None:
            return self._resolve_issue(payload.issue_id, db)

        if payload.project_id is not None:
            return self._resolve_project(payload.project_id, db)

        if payload.customer_id is not None:
            return self._resolve_customer(payload.customer_id, db)

        return KnowledgeSearchContext(
            customer_id=None,
            project_id=None,
            issue_id=None,
            resolved_scope_types=[ScopeType.global_scope],
        )

    def _resolve_customer(
        self,
        customer_id: int,
        db: Session,
    ) -> KnowledgeSearchContext:
        customer = (
            db.query(Customer)
            .filter(Customer.id == customer_id)
            .first()
        )

        if customer is None:
            raise HTTPException(
                status_code=404,
                detail='Customer not found',
            )

        return KnowledgeSearchContext(
            customer_id=customer.id,
            project_id=None,
            issue_id=None,
            resolved_scope_types=[
                ScopeType.global_scope,
                ScopeType.customer,
            ],
        )

    def _resolve_project(
        self,
        project_id: int,
        db: Session,
    ) -> KnowledgeSearchContext:
        project = (
            db.query(Project)
            .filter(Project.id == project_id)
            .first()
        )

        if project is None:
            raise HTTPException(
                status_code=404,
                detail='Project not found',
            )

        scope_types = [ScopeType.global_scope]

        if project.customer_id is not None:
            scope_types.append(ScopeType.customer)

        scope_types.append(ScopeType.project)

        return KnowledgeSearchContext(
            customer_id=project.customer_id,
            project_id=project.id,
            issue_id=None,
            resolved_scope_types=scope_types,
        )

    def _resolve_issue(
        self,
        issue_id: int,
        db: Session,
    ) -> KnowledgeSearchContext:
        issue = (
            db.query(Issue)
            .filter(Issue.id == issue_id)
            .first()
        )

        if issue is None:
            raise HTTPException(
                status_code=404,
                detail='Issue not found',
            )

        if issue.project_id is None:
            return KnowledgeSearchContext(
                customer_id=None,
                project_id=None,
                issue_id=issue.id,
                resolved_scope_types=[ScopeType.global_scope],
            )

        project = (
            db.query(Project)
            .filter(Project.id == issue.project_id)
            .first()
        )

        if project is None:
            raise HTTPException(
                status_code=500,
                detail='Issue project relation is invalid',
            )

        scope_types = [ScopeType.global_scope]

        if project.customer_id is not None:
            scope_types.append(ScopeType.customer)

        scope_types.append(ScopeType.project)

        return KnowledgeSearchContext(
            customer_id=project.customer_id,
            project_id=project.id,
            issue_id=issue.id,
            resolved_scope_types=scope_types,
        )


knowledge_search_context_resolver = KnowledgeSearchContextResolver()
