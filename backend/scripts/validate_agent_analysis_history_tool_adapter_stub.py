from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
from typing import Callable, TypeVar

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.models import (
    AIAnalysisLog,
    Customer,
    Issue,
    Project,
)
from app.models.base import Base
from app.schemas.agent_tools import (
    AGENT_ANALYSIS_HISTORY_LIMIT,
    AgentAnalysisHistoryOutput,
)
from app.services.agent_analysis_history_tool_adapter import (
    AgentAnalysisHistoryToolAdapter,
)
from app.services.agent_tool_registry import (
    approved_agent_tool_registry,
)


T = TypeVar("T")
BASE_TIME = datetime(2026, 7, 27, 10, 0, 0)


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


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            Project.__table__,
            Issue.__table__,
            AIAnalysisLog.__table__,
        ],
    )
    return Session(engine)


def citation_payload() -> dict[str, object]:
    return {
        "citation_id": "K1",
        "rank": 1,
        "chunk_id": 501,
        "document_id": 301,
        "document_title": "API Troubleshooting Guide",
        "scope_type": "global",
        "doc_type": "runbook",
        "source_kind": "manual",
        "source_name": "Enterprise Runbook",
        "source_uri": None,
        "chunk_index": 0,
        "chunk_text": "Verify credentials and token scope.",
        "similarity_score": 0.91,
    }


def make_log(
    *,
    analysis_id: int,
    issue_id: int,
    created_at: datetime,
    provider: str = "rule_based_fallback",
    model_name: str | None = None,
    prompt_version: str | None = "issue_summarizer_v3",
    feedback_status: str = "pending",
    retrieval_status: str = "not_attempted",
    retrieval_query: str | None = None,
    citations: list[dict[str, object]] | None = None,
    recommended_actions_json: str | None = None,
    knowledge_citations_json: str | None = None,
) -> AIAnalysisLog:
    actions_json = (
        recommended_actions_json
        if recommended_actions_json is not None
        else json.dumps(
            [
                f"Action {analysis_id}-A",
                f"Action {analysis_id}-B",
            ]
        )
    )
    citations_json = (
        knowledge_citations_json
        if knowledge_citations_json is not None
        else json.dumps(citations or [])
    )

    return AIAnalysisLog(
        id=analysis_id,
        issue_id=issue_id,
        analysis_type="issue_summarizer",
        provider=provider,
        model_name=model_name,
        prompt_version=prompt_version,
        issue_summary=f"Summary {analysis_id}",
        possible_root_cause=f"Root cause {analysis_id}",
        recommended_actions_json=actions_json,
        customer_update_draft=f"Customer update {analysis_id}",
        risk_level="medium",
        project_impact=f"Project impact {analysis_id}",
        feedback_status=feedback_status,
        feedback_note=None,
        edited_output=None,
        retrieval_status=retrieval_status,
        retrieval_query=retrieval_query,
        knowledge_citations_json=citations_json,
        retrieval_error_code=None,
        created_at=created_at,
        updated_at=created_at + timedelta(minutes=1),
    )


def seed_data(db: Session) -> None:
    db.add_all(
        (
            Issue(
                id=1001,
                project_id=None,
                title="Target issue",
                status="investigating",
                severity="high",
            ),
            Issue(
                id=1002,
                project_id=None,
                title="Issue with no history",
                status="open",
                severity="low",
            ),
            Issue(
                id=1003,
                project_id=None,
                title="Malformed actions issue",
                status="open",
                severity="medium",
            ),
            Issue(
                id=1004,
                project_id=None,
                title="Malformed citations issue",
                status="open",
                severity="medium",
            ),
            Issue(
                id=2001,
                project_id=None,
                title="Unrelated issue",
                status="resolved",
                severity="low",
            ),
        )
    )

    logs: list[AIAnalysisLog] = []
    for analysis_id in range(1, 8):
        created_at = BASE_TIME + timedelta(
            hours=min(analysis_id, 6)
        )
        logs.append(
            make_log(
                analysis_id=analysis_id,
                issue_id=1001,
                created_at=created_at,
                provider=(
                    "llm"
                    if analysis_id == 7
                    else "rule_based_fallback"
                ),
                model_name=(
                    "gpt-5.5"
                    if analysis_id == 7
                    else None
                ),
                prompt_version=(
                    "issue_summarizer_v4_grounded"
                    if analysis_id == 7
                    else "issue_summarizer_v3"
                ),
                feedback_status=(
                    "accepted"
                    if analysis_id == 6
                    else "pending"
                ),
                retrieval_status=(
                    "succeeded"
                    if analysis_id == 7
                    else "not_attempted"
                ),
                retrieval_query=(
                    "Target issue authentication failure"
                    if analysis_id == 7
                    else None
                ),
                citations=(
                    [citation_payload()]
                    if analysis_id == 7
                    else []
                ),
            )
        )

    logs.extend(
        (
            make_log(
                analysis_id=20,
                issue_id=2001,
                created_at=BASE_TIME + timedelta(hours=20),
            ),
            make_log(
                analysis_id=30,
                issue_id=1003,
                created_at=BASE_TIME,
                recommended_actions_json="{bad-json",
            ),
            make_log(
                analysis_id=40,
                issue_id=1004,
                created_at=BASE_TIME,
                knowledge_citations_json=(
                    '{"not": "an array"}'
                ),
            ),
        )
    )

    db.add_all(logs)
    db.commit()


def test_limit_constant_is_frozen() -> None:
    assert AGENT_ANALYSIS_HISTORY_LIMIT == 5
    print("PASS: analysis history limit is frozen")


def test_newest_first_and_limit(db: Session) -> None:
    output = AgentAnalysisHistoryToolAdapter().execute(
        1001,
        db,
    )
    assert isinstance(output, AgentAnalysisHistoryOutput)
    assert output.analysis_count == 5
    assert tuple(
        item.analysis_id
        for item in output.analyses
    ) == (7, 6, 5, 4, 3)
    print("PASS: newest-first history is limited to five")


def test_history_is_issue_scoped(db: Session) -> None:
    output = AgentAnalysisHistoryToolAdapter().execute(
        1001,
        db,
    )
    assert all(
        item.issue_id == 1001
        for item in output.analyses
    )
    assert 20 not in {
        item.analysis_id
        for item in output.analyses
    }
    print("PASS: unrelated Issue history does not leak")


def test_json_fields_are_typed(db: Session) -> None:
    output = AgentAnalysisHistoryToolAdapter().execute(
        1001,
        db,
    )
    newest = output.analyses[0]

    assert newest.recommended_actions == (
        "Action 7-A",
        "Action 7-B",
    )
    assert len(newest.knowledge_citations) == 1
    assert newest.knowledge_citations[0].citation_id == "K1"
    assert newest.knowledge_citations[0].rank == 1
    print("PASS: persisted JSON is converted to typed fields")


def test_grounded_flag_is_derived(db: Session) -> None:
    output = AgentAnalysisHistoryToolAdapter().execute(
        1001,
        db,
    )
    assert output.analyses[0].knowledge_grounded is True
    assert all(
        item.knowledge_grounded is False
        for item in output.analyses[1:]
    )
    print("PASS: grounded flag is derived consistently")


def test_output_is_json_safe(db: Session) -> None:
    output = AgentAnalysisHistoryToolAdapter().execute(
        1001,
        db,
    )
    payload = output.model_dump(mode="json")
    encoded = json.dumps(payload)

    assert '"analysis_count": 5' in encoded
    assert "AIAnalysisLog" not in encoded
    print("PASS: output is JSON-safe and ORM-free")


def test_empty_history_is_valid(db: Session) -> None:
    output = AgentAnalysisHistoryToolAdapter().execute(
        1002,
        db,
    )
    assert output.analysis_count == 0
    assert output.analyses == ()
    print("PASS: empty history is represented explicitly")


def test_missing_issue_is_rejected(db: Session) -> None:
    error = expect_raises(
        LookupError,
        lambda: AgentAnalysisHistoryToolAdapter().execute(
            999999,
            db,
        ),
    )
    assert "Issue not found" in str(error)
    print("PASS: missing Issue is rejected")


def test_invalid_issue_id_is_rejected(db: Session) -> None:
    expect_raises(
        ValidationError,
        lambda: AgentAnalysisHistoryToolAdapter().execute(
            0,
            db,
        ),
    )
    print("PASS: invalid issue_id is rejected")


def test_malformed_actions_json_is_rejected(
    db: Session,
) -> None:
    error = expect_raises(
        ValueError,
        lambda: AgentAnalysisHistoryToolAdapter().execute(
            1003,
            db,
        ),
    )
    assert "recommended_actions_json" in str(error)
    print("PASS: malformed actions JSON is rejected")


def test_non_array_citations_json_is_rejected(
    db: Session,
) -> None:
    error = expect_raises(
        ValueError,
        lambda: AgentAnalysisHistoryToolAdapter().execute(
            1004,
            db,
        ),
    )
    assert "knowledge_citations_json" in str(error)
    print("PASS: non-array citations JSON is rejected")


def test_registry_target_matches_adapter() -> None:
    definition = approved_agent_tool_registry.get(
        "get_analysis_history"
    )
    assert (
        definition.adapter_target
        == "AgentAnalysisHistoryToolAdapter.execute"
    )
    assert definition.argument_fields == ("issue_id",)
    assert definition.result_fields == (
        "issue_id",
        "analysis_count",
        "analyses",
    )
    print("PASS: Registry target matches Adapter")


def test_service_source_is_read_only_and_bounded() -> None:
    source_path = (
        BACKEND_ROOT
        / "app"
        / "services"
        / "agent_analysis_history_tool_adapter.py"
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
        "IssueAnalysisService(",
        "analyze_and_store(",
    )
    found = [
        token
        for token in forbidden_tokens
        if token in source
    ]

    assert not found, found
    assert ".limit(AGENT_ANALYSIS_HISTORY_LIMIT)" in source
    assert "AIAnalysisLog.created_at.desc()" in source
    assert "AIAnalysisLog.id.desc()" in source
    assert "AgentAnalysisHistoryOutput(" in source
    print("PASS: service source is read-only and bounded")


def main() -> None:
    test_limit_constant_is_frozen()

    db = build_session()
    try:
        seed_data(db)
        test_newest_first_and_limit(db)
        test_history_is_issue_scoped(db)
        test_json_fields_are_typed(db)
        test_grounded_flag_is_derived(db)
        test_output_is_json_safe(db)
        test_empty_history_is_valid(db)
        test_missing_issue_is_rejected(db)
        test_invalid_issue_id_is_rejected(db)
        test_malformed_actions_json_is_rejected(db)
        test_non_array_citations_json_is_rejected(db)
        test_registry_target_matches_adapter()
        test_service_source_is_read_only_and_bounded()
    finally:
        db.close()

    print(
        "Agent Analysis History Tool Adapter assertions "
        "passed (13/13)"
    )


if __name__ == "__main__":
    main()
