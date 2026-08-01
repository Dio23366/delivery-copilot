from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Callable, TypeVar

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.ai.grounded_retrieval_service import (
    grounded_retrieval_service,
)
from app.ai.schemas import (
    GroundedRetrievalOutcome,
    KnowledgeCitationSnapshot,
    KnowledgeEvidence,
)
from app.models import Customer, Issue, Project
from app.models.base import Base
from app.schemas.agent_tools import (
    AgentSearchKnowledgeOutput,
)
from app.services.agent_search_knowledge_tool_adapter import (
    AgentSearchKnowledgeToolAdapter,
    agent_search_knowledge_tool_adapter,
)
from app.services.agent_tool_registry import (
    approved_agent_tool_registry,
)


T = TypeVar("T")


def expect_raises(
    exception_type: type[T],
    callback: Callable[[], object],
) -> T:
    try:
        callback()
    except exception_type as exc:
        return exc
    raise AssertionError(
        f"Expected {exception_type.__name__} to be raised"
    )


def make_evidence() -> KnowledgeEvidence:
    return KnowledgeEvidence(
        citation_id="K1",
        rank=1,
        chunk_id=501,
        document_id=301,
        document_title="API Troubleshooting Guide",
        scope_type="global",
        doc_type="runbook",
        source_kind="manual",
        source_name="Enterprise Runbook",
        source_uri=None,
        chunk_index=0,
        chunk_text="Verify credentials and token scope.",
        distance=0.09,
        similarity_score=0.91,
    )


def make_citation() -> KnowledgeCitationSnapshot:
    return KnowledgeCitationSnapshot(
        citation_id="K1",
        rank=1,
        chunk_id=501,
        document_id=301,
        document_title="API Troubleshooting Guide",
        scope_type="global",
        doc_type="runbook",
        source_kind="manual",
        source_name="Enterprise Runbook",
        source_uri=None,
        chunk_index=0,
        chunk_text="Verify credentials and token scope.",
        similarity_score=0.91,
    )


def success_outcome() -> GroundedRetrievalOutcome:
    return GroundedRetrievalOutcome(
        retrieval_status="succeeded",
        retrieval_query="API authentication failure",
        knowledge_evidence=(make_evidence(),),
        knowledge_citations=(make_citation(),),
        retrieval_error_code=None,
    )


class FakeRetrievalService:
    def __init__(
        self,
        outcome: GroundedRetrievalOutcome,
    ) -> None:
        self.outcome = outcome
        self.calls: list[
            tuple[
                Issue,
                Project | None,
                Customer | None,
                Session,
            ]
        ] = []

    def retrieve(
        self,
        issue: Issue,
        project: Project | None,
        customer: Customer | None,
        db: Session,
    ) -> GroundedRetrievalOutcome:
        self.calls.append(
            (issue, project, customer, db)
        )
        return self.outcome


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            Project.__table__,
            Issue.__table__,
        ],
    )
    return Session(engine)


def seed_data(db: Session) -> None:
    db.add(
        Customer(
            id=501,
            name="Acme Enterprise",
            industry="Finance",
            contact="ops@acme.example",
            status="active",
            owner="Delivery Team",
        )
    )
    db.add_all(
        (
            Project(
                id=101,
                customer_id=501,
                name="API Integration",
                status="active",
                health="at_risk",
                risk_level="high",
                delivery_stage="Testing",
            ),
            Project(
                id=202,
                customer_id=None,
                name="Customerless Project",
                status="planning",
                health="healthy",
                risk_level="low",
                delivery_stage="Discovery",
            ),
        )
    )
    db.add_all(
        (
            Issue(
                id=1001,
                project_id=101,
                title="Authentication failure",
                status="investigating",
                severity="high",
            ),
            Issue(
                id=1002,
                project_id=None,
                title="Unscoped issue",
                status="open",
                severity="low",
            ),
            Issue(
                id=1003,
                project_id=202,
                title="Project without customer",
                status="open",
                severity="medium",
            ),
            Issue(
                id=1004,
                project_id=999,
                title="Missing referenced project",
                status="open",
                severity="medium",
            ),
        )
    )
    db.commit()


def test_default_dependency_is_grounded_service() -> None:
    assert (
        agent_search_knowledge_tool_adapter
        ._retrieval_service
        is grounded_retrieval_service
    )
    print("PASS: default dependency is grounded retrieval")


def test_successful_mapping_and_scope(db: Session) -> None:
    fake = FakeRetrievalService(success_outcome())
    output = AgentSearchKnowledgeToolAdapter(
        fake
    ).execute(1001, db)

    assert isinstance(output, AgentSearchKnowledgeOutput)
    assert output.retrieval_status == "succeeded"
    assert output.retrieval_query == (
        "API authentication failure"
    )
    assert len(output.knowledge_evidence) == 1
    assert len(output.knowledge_citations) == 1
    assert output.knowledge_evidence[0].distance == 0.09
    assert output.knowledge_citations[0].citation_id == "K1"

    assert len(fake.calls) == 1
    issue, project, customer, call_db = fake.calls[0]
    assert issue.id == 1001
    assert project is not None and project.id == 101
    assert customer is not None and customer.id == 501
    assert call_db is db
    print("PASS: success mapping and scope resolution")


def test_no_results_output(db: Session) -> None:
    fake = FakeRetrievalService(
        GroundedRetrievalOutcome(
            retrieval_status="no_results",
            retrieval_query="no matching runbook",
            knowledge_evidence=(),
            knowledge_citations=(),
            retrieval_error_code=None,
        )
    )
    output = AgentSearchKnowledgeToolAdapter(
        fake
    ).execute(1001, db)

    assert output.retrieval_status == "no_results"
    assert output.knowledge_evidence == ()
    assert output.knowledge_citations == ()
    print("PASS: no-results outcome is controlled")


def test_failed_output(db: Session) -> None:
    fake = FakeRetrievalService(
        GroundedRetrievalOutcome(
            retrieval_status="failed",
            retrieval_query="provider failure",
            knowledge_evidence=(),
            knowledge_citations=(),
            retrieval_error_code=(
                "retrieval_provider_failed"
            ),
        )
    )
    output = AgentSearchKnowledgeToolAdapter(
        fake
    ).execute(1001, db)

    assert output.retrieval_status == "failed"
    assert output.retrieval_error_code == (
        "retrieval_provider_failed"
    )
    print("PASS: failed outcome is controlled")


def test_output_is_json_safe(db: Session) -> None:
    output = AgentSearchKnowledgeToolAdapter(
        FakeRetrievalService(success_outcome())
    ).execute(1001, db)

    payload = output.model_dump(mode="json")
    encoded = json.dumps(payload)

    assert '"retrieval_status": "succeeded"' in encoded
    assert "KnowledgeEvidence" not in encoded
    assert "KnowledgeCitationSnapshot" not in encoded
    print("PASS: output is JSON-safe and dataclass-free")


def test_issue_without_project_is_supported(
    db: Session,
) -> None:
    fake = FakeRetrievalService(success_outcome())
    AgentSearchKnowledgeToolAdapter(fake).execute(
        1002,
        db,
    )

    _, project, customer, _ = fake.calls[0]
    assert project is None
    assert customer is None
    print("PASS: Issue without Project uses issue scope")


def test_project_without_customer_is_supported(
    db: Session,
) -> None:
    fake = FakeRetrievalService(success_outcome())
    AgentSearchKnowledgeToolAdapter(fake).execute(
        1003,
        db,
    )

    _, project, customer, _ = fake.calls[0]
    assert project is not None and project.id == 202
    assert customer is None
    print("PASS: Project without Customer is supported")


def test_missing_referenced_project_is_tolerated(
    db: Session,
) -> None:
    fake = FakeRetrievalService(success_outcome())
    AgentSearchKnowledgeToolAdapter(fake).execute(
        1004,
        db,
    )

    _, project, customer, _ = fake.calls[0]
    assert project is None
    assert customer is None
    print("PASS: missing referenced Project falls back safely")


def test_missing_issue_is_rejected(db: Session) -> None:
    error = expect_raises(
        LookupError,
        lambda: AgentSearchKnowledgeToolAdapter(
            FakeRetrievalService(success_outcome())
        ).execute(999999, db),
    )
    assert "Issue not found" in str(error)
    print("PASS: missing Issue is rejected")


def test_invalid_issue_id_is_rejected(db: Session) -> None:
    expect_raises(
        ValidationError,
        lambda: AgentSearchKnowledgeToolAdapter(
            FakeRetrievalService(success_outcome())
        ).execute(0, db),
    )
    print("PASS: invalid issue_id is rejected")


def test_mismatched_evidence_is_rejected(
    db: Session,
) -> None:
    bad = GroundedRetrievalOutcome(
        retrieval_status="succeeded",
        retrieval_query="mismatched evidence",
        knowledge_evidence=(make_evidence(),),
        knowledge_citations=(),
        retrieval_error_code=None,
    )
    expect_raises(
        ValidationError,
        lambda: AgentSearchKnowledgeToolAdapter(
            FakeRetrievalService(bad)
        ).execute(1001, db),
    )
    print("PASS: mismatched evidence is rejected")


def test_unsupported_status_is_rejected(
    db: Session,
) -> None:
    bad = GroundedRetrievalOutcome(
        retrieval_status="not_attempted",
        retrieval_query="not attempted",
        knowledge_evidence=(),
        knowledge_citations=(),
        retrieval_error_code=None,
    )
    expect_raises(
        ValidationError,
        lambda: AgentSearchKnowledgeToolAdapter(
            FakeRetrievalService(bad)
        ).execute(1001, db),
    )
    print("PASS: unsupported retrieval status is rejected")


def test_registry_target_matches_adapter() -> None:
    definition = approved_agent_tool_registry.get(
        "search_knowledge"
    )
    assert (
        definition.adapter_target
        == "AgentSearchKnowledgeToolAdapter.execute"
    )
    assert definition.argument_fields == ("issue_id",)
    assert definition.result_fields == (
        "retrieval_status",
        "retrieval_query",
        "knowledge_evidence",
        "knowledge_citations",
        "retrieval_error_code",
    )
    print("PASS: Registry target matches Adapter")


def test_service_source_is_read_only_and_layered() -> None:
    source_path = (
        BACKEND_ROOT
        / "app"
        / "services"
        / "agent_search_knowledge_tool_adapter.py"
    )
    source = source_path.read_text(encoding="utf-8")

    forbidden_tokens = (
        "db.add(",
        "db.delete(",
        "db.commit(",
        "db.rollback(",
        "db.flush(",
        "db.refresh(",
        ".with_for_update(",
        "KnowledgeSearchService",
        "knowledge_search_service",
        "IssueAnalysisService",
        "analyze_and_store(",
    )
    found = [
        token
        for token in forbidden_tokens
        if token in source
    ]
    assert not found, found
    assert "grounded_retrieval_service" in source
    assert "AgentSearchKnowledgeOutput(" in source
    assert "_to_agent_evidence(" in source
    assert "_to_agent_citation(" in source
    print("PASS: service source is read-only and layered")


def main() -> None:
    test_default_dependency_is_grounded_service()
    test_registry_target_matches_adapter()

    db = build_session()
    try:
        seed_data(db)
        test_successful_mapping_and_scope(db)
        test_no_results_output(db)
        test_failed_output(db)
        test_output_is_json_safe(db)
        test_issue_without_project_is_supported(db)
        test_project_without_customer_is_supported(db)
        test_missing_referenced_project_is_tolerated(db)
        test_missing_issue_is_rejected(db)
        test_invalid_issue_id_is_rejected(db)
        test_mismatched_evidence_is_rejected(db)
        test_unsupported_status_is_rejected(db)
    finally:
        db.close()

    test_service_source_is_read_only_and_layered()

    print(
        "Agent Search Knowledge Tool Adapter assertions "
        "passed (14/14)"
    )


if __name__ == "__main__":
    main()
