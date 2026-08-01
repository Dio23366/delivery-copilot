from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys

from pydantic import ValidationError


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.schemas.agent_tools import (  # noqa: E402
    AGENT_ANALYSIS_HISTORY_LIMIT,
    AgentAnalysisHistoryInput,
    AgentAnalysisHistoryItem,
    AgentAnalysisHistoryOutput,
    AgentDeliveryRiskInput,
    AgentDeliveryRiskOutput,
    AgentDeliveryRiskSignals,
    AgentKnowledgeCitation,
    AgentKnowledgeEvidence,
    AgentSearchKnowledgeInput,
    AgentSearchKnowledgeOutput,
)


def expect_validation_error(operation) -> None:
    try:
        operation()
    except ValidationError:
        return
    raise AssertionError("Expected Pydantic ValidationError")


def make_evidence(
    *,
    rank: int = 1,
    citation_id: str = "K1",
) -> AgentKnowledgeEvidence:
    return AgentKnowledgeEvidence(
        citation_id=citation_id,
        rank=rank,
        chunk_id=10 + rank,
        document_id=20 + rank,
        document_title="API Troubleshooting",
        scope_type="global",
        doc_type="runbook",
        source_kind="manual",
        source_name="Enterprise Runbook",
        source_uri=None,
        chunk_index=rank - 1,
        chunk_text="Validate authentication and authorization.",
        distance=0.1,
        similarity_score=0.9,
    )


def make_citation(
    *,
    rank: int = 1,
    citation_id: str = "K1",
) -> AgentKnowledgeCitation:
    return AgentKnowledgeCitation(
        citation_id=citation_id,
        rank=rank,
        chunk_id=10 + rank,
        document_id=20 + rank,
        document_title="API Troubleshooting",
        scope_type="global",
        doc_type="runbook",
        source_kind="manual",
        source_name="Enterprise Runbook",
        source_uri=None,
        chunk_index=rank - 1,
        chunk_text="Validate authentication and authorization.",
        similarity_score=0.9,
    )


def make_history_item(
    *,
    analysis_id: int,
    created_at: datetime,
    issue_id: int = 17,
) -> AgentAnalysisHistoryItem:
    return AgentAnalysisHistoryItem(
        analysis_id=analysis_id,
        issue_id=issue_id,
        analysis_type="issue_summarizer",
        provider="llm",
        model_name="gpt-5.5",
        prompt_version="issue_summarizer_v4_grounded",
        issue_summary="Authentication is failing.",
        possible_root_cause="The token scope may be incorrect.",
        recommended_actions=("Validate token scope.",),
        customer_update_draft="We are validating authentication.",
        risk_level="high",
        project_impact="The integration timeline may be affected.",
        feedback_status="accepted",
        feedback_note=None,
        edited_output=None,
        retrieval_status="succeeded",
        retrieval_query="API authentication failure",
        knowledge_citations=(make_citation(),),
        retrieval_error_code=None,
        knowledge_grounded=True,
        created_at=created_at,
        updated_at=created_at,
    )


def test_positive_tool_inputs() -> None:
    assert AgentSearchKnowledgeInput(issue_id=17).issue_id == 17
    assert AgentAnalysisHistoryInput(issue_id=17).issue_id == 17
    assert AgentDeliveryRiskInput(issue_id=17).issue_id == 17
    print("PASS: positive issue-scoped tool inputs")


def test_invalid_tool_inputs() -> None:
    expect_validation_error(
        lambda: AgentSearchKnowledgeInput(issue_id=0)
    )
    expect_validation_error(
        lambda: AgentAnalysisHistoryInput(issue_id=-1)
    )
    expect_validation_error(
        lambda: AgentDeliveryRiskInput(issue_id=0)
    )
    print("PASS: invalid issue identifiers rejected")


def test_successful_search_output() -> None:
    output = AgentSearchKnowledgeOutput(
        retrieval_status="succeeded",
        retrieval_query=" API authentication ",
        knowledge_evidence=(make_evidence(),),
        knowledge_citations=(make_citation(),),
        retrieval_error_code=None,
    )
    assert output.retrieval_query == "API authentication"
    assert len(output.knowledge_evidence) == 1
    print("PASS: successful knowledge output")


def test_no_results_search_output() -> None:
    output = AgentSearchKnowledgeOutput(
        retrieval_status="no_results",
        retrieval_query="missing evidence",
    )
    assert output.knowledge_evidence == ()
    assert output.knowledge_citations == ()
    print("PASS: no-results knowledge output")


def test_failed_search_output() -> None:
    output = AgentSearchKnowledgeOutput(
        retrieval_status="failed",
        retrieval_query="provider failure",
        retrieval_error_code="retrieval_provider_failed",
    )
    assert output.retrieval_error_code == (
        "retrieval_provider_failed"
    )
    print("PASS: failed knowledge output")


def test_invalid_search_status_combinations() -> None:
    expect_validation_error(
        lambda: AgentSearchKnowledgeOutput(
            retrieval_status="succeeded",
            retrieval_query="missing result",
        )
    )
    expect_validation_error(
        lambda: AgentSearchKnowledgeOutput(
            retrieval_status="failed",
            retrieval_query="missing error",
        )
    )
    expect_validation_error(
        lambda: AgentSearchKnowledgeOutput(
            retrieval_status="no_results",
            retrieval_query="unexpected result",
            knowledge_evidence=(make_evidence(),),
            knowledge_citations=(make_citation(),),
        )
    )
    print("PASS: invalid retrieval combinations rejected")


def test_mismatched_evidence_and_citations() -> None:
    expect_validation_error(
        lambda: AgentSearchKnowledgeOutput(
            retrieval_status="succeeded",
            retrieval_query="identity mismatch",
            knowledge_evidence=(make_evidence(),),
            knowledge_citations=(
                make_citation(citation_id="K2"),
            ),
        )
    )
    print("PASS: evidence and citation mismatch rejected")


def test_analysis_history_item() -> None:
    now = datetime.now(timezone.utc)
    item = make_history_item(
        analysis_id=68,
        created_at=now,
    )
    assert item.knowledge_grounded is True
    assert item.recommended_actions == (
        "Validate token scope.",
    )
    print("PASS: controlled analysis history item")


def test_inconsistent_grounded_flag() -> None:
    now = datetime.now(timezone.utc)
    payload = make_history_item(
        analysis_id=68,
        created_at=now,
    ).model_dump()
    payload["knowledge_grounded"] = False

    expect_validation_error(
        lambda: AgentAnalysisHistoryItem(**payload)
    )
    print("PASS: inconsistent grounded flag rejected")


def test_analysis_history_output() -> None:
    now = datetime.now(timezone.utc)
    newer = make_history_item(
        analysis_id=68,
        created_at=now,
    )
    older = make_history_item(
        analysis_id=67,
        created_at=now - timedelta(minutes=1),
    )
    output = AgentAnalysisHistoryOutput(
        issue_id=17,
        analysis_count=2,
        analyses=(newer, older),
    )
    assert output.analysis_count == 2
    print("PASS: newest-first analysis history")


def test_invalid_history_count_and_issue() -> None:
    now = datetime.now(timezone.utc)
    item = make_history_item(
        analysis_id=68,
        created_at=now,
    )
    expect_validation_error(
        lambda: AgentAnalysisHistoryOutput(
            issue_id=17,
            analysis_count=0,
            analyses=(item,),
        )
    )
    expect_validation_error(
        lambda: AgentAnalysisHistoryOutput(
            issue_id=18,
            analysis_count=1,
            analyses=(item,),
        )
    )
    print("PASS: invalid history count and issue rejected")


def test_invalid_history_order() -> None:
    now = datetime.now(timezone.utc)
    older = make_history_item(
        analysis_id=67,
        created_at=now - timedelta(minutes=1),
    )
    newer = make_history_item(
        analysis_id=68,
        created_at=now,
    )
    expect_validation_error(
        lambda: AgentAnalysisHistoryOutput(
            issue_id=17,
            analysis_count=2,
            analyses=(older, newer),
        )
    )
    print("PASS: invalid history order rejected")


def test_history_limit() -> None:
    now = datetime.now(timezone.utc)
    items = tuple(
        make_history_item(
            analysis_id=100 - index,
            created_at=now - timedelta(minutes=index),
        )
        for index in range(AGENT_ANALYSIS_HISTORY_LIMIT + 1)
    )
    expect_validation_error(
        lambda: AgentAnalysisHistoryOutput(
            issue_id=17,
            analysis_count=len(items),
            analyses=items,
        )
    )
    print("PASS: analysis history limit enforced")


def test_delivery_risk_models() -> None:
    signals = AgentDeliveryRiskSignals(
        project_id=3,
        overdue_requirements=1,
        blocked_issues=2,
        critical_issues=1,
        delivery_completion_rate=0.4,
    )
    output = AgentDeliveryRiskOutput(
        **signals.model_dump(),
        risk_level="high",
    )
    assert output.risk_level == "high"
    print("PASS: delivery risk signals and output")


def test_invalid_delivery_risk_values() -> None:
    expect_validation_error(
        lambda: AgentDeliveryRiskSignals(
            project_id=3,
            overdue_requirements=-1,
            blocked_issues=0,
            critical_issues=0,
            delivery_completion_rate=0.5,
        )
    )
    expect_validation_error(
        lambda: AgentDeliveryRiskOutput(
            project_id=3,
            overdue_requirements=0,
            blocked_issues=0,
            critical_issues=0,
            delivery_completion_rate=1.1,
            risk_level="low",
        )
    )
    print("PASS: invalid delivery risk values rejected")


def test_extra_fields_forbidden() -> None:
    expect_validation_error(
        lambda: AgentSearchKnowledgeInput(
            issue_id=17,
            db_session="forbidden",
        )
    )
    print("PASS: extra fields forbidden")


def test_all_outputs_are_json_serializable() -> None:
    now = datetime.now(timezone.utc)
    outputs = (
        AgentSearchKnowledgeOutput(
            retrieval_status="succeeded",
            retrieval_query="API authentication",
            knowledge_evidence=(make_evidence(),),
            knowledge_citations=(make_citation(),),
        ),
        AgentAnalysisHistoryOutput(
            issue_id=17,
            analysis_count=1,
            analyses=(
                make_history_item(
                    analysis_id=68,
                    created_at=now,
                ),
            ),
        ),
        AgentDeliveryRiskOutput(
            project_id=3,
            overdue_requirements=1,
            blocked_issues=1,
            critical_issues=0,
            delivery_completion_rate=0.5,
            risk_level="medium",
        ),
    )

    for output in outputs:
        serialized = output.model_dump(mode="json")
        json.dumps(serialized)

    print("PASS: all Tool outputs are JSON serializable")


def test_schema_source_is_side_effect_free() -> None:
    source_path = (
        BACKEND_ROOT
        / "app"
        / "schemas"
        / "agent_tools.py"
    )
    source = source_path.read_text(encoding="utf-8")

    forbidden_tokens = (
        "sqlalchemy",
        "Session",
        "db.commit(",
        "db.rollback(",
        "db.refresh(",
        "db.flush(",
        "AIAnalysisLog",
        "GroundedRetrievalService",
        "IssueAnalysisService",
        "calculate_risk_level(",
    )
    found = [
        token
        for token in forbidden_tokens
        if token in source
    ]
    assert not found, found
    print("PASS: Tool schema source is side-effect free")


def main() -> None:
    tests = (
        test_positive_tool_inputs,
        test_invalid_tool_inputs,
        test_successful_search_output,
        test_no_results_search_output,
        test_failed_search_output,
        test_invalid_search_status_combinations,
        test_mismatched_evidence_and_citations,
        test_analysis_history_item,
        test_inconsistent_grounded_flag,
        test_analysis_history_output,
        test_invalid_history_count_and_issue,
        test_invalid_history_order,
        test_history_limit,
        test_delivery_risk_models,
        test_invalid_delivery_risk_values,
        test_extra_fields_forbidden,
        test_all_outputs_are_json_serializable,
        test_schema_source_is_side_effect_free,
    )

    for test in tests:
        test()

    print(
        "Agent Tool schema stub assertions passed "
        f"({len(tests)}/{len(tests)})"
    )


if __name__ == "__main__":
    main()