from __future__ import annotations

import ast
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Callable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.ai.schemas import IssueAnalysisResult
from app.schemas.agent_tools import (
    AgentAnalysisHistoryItem,
    AgentDeliveryRiskOutput,
    AgentKnowledgeCitation,
    AgentKnowledgeEvidence,
    AgentSearchKnowledgeOutput,
)
from app.services.agent_analysis_generation_service import (
    AGENT_ANALYSIS_GENERATION_VERSION,
    GENERATED_ANALYSIS_STATE_KEY,
    AgentAnalysisGenerationError,
    AgentAnalysisGenerationService,
)


SERVICE_PATH = (
    BACKEND_ROOT
    / "app"
    / "services"
    / "agent_analysis_generation_service.py"
)


def expect_error(
    error_code: str,
    callback: Callable[[], object],
) -> AgentAnalysisGenerationError:
    try:
        callback()
    except AgentAnalysisGenerationError as exc:
        assert exc.error_code == error_code
        return exc
    raise AssertionError(
        f"Expected AgentAnalysisGenerationError: {error_code}"
    )


class StubProvider:
    name = "llm"

    def __init__(
        self,
        *,
        provider_name: str = "llm",
        model_name: str | None = "gpt-test",
        fallback_reason: str | None = None,
        result: object | None = None,
    ) -> None:
        self.last_provider_name = provider_name
        self.last_model_name = model_name
        self.last_fallback_reason = fallback_reason
        self.contexts: list[object] = []
        self.result = result or IssueAnalysisResult(
            issue_summary="Authentication fails after rollout.",
            possible_root_cause="Token exchange configuration may be inconsistent.",
            recommended_actions=[
                "Validate the token endpoint configuration.",
                "Compare the rollout configuration with the last known good version.",
            ],
            customer_update_draft="The issue is under controlled investigation.",
            risk_level="high",
            project_impact="Testing and customer acceptance may be delayed.",
        )

    def analyze_issue(self, context: object) -> object:
        self.contexts.append(context)
        return self.result


def issue_context() -> dict[str, object]:
    return {
        "issue_id": 17,
        "issue_title": "Token exchange failure",
        "issue_description": "Authentication fails after rollout.",
        "issue_type": "API",
        "severity": "high",
        "status": "investigating",
        "owner": "Platform Team",
        "project_name": "Enterprise Delivery",
        "project_status": "active",
        "delivery_stage": "Testing",
        "risk_level": "high",
        "health": "critical",
        "customer_name": "Example Customer",
        "customer_industry": "Finance",
        "customer_contact": "Customer Owner",
    }


def knowledge_output() -> AgentSearchKnowledgeOutput:
    evidence = AgentKnowledgeEvidence(
        citation_id="K1",
        rank=1,
        chunk_id=101,
        document_id=11,
        document_title="API Authentication Guide",
        scope_type="global",
        doc_type="runbook",
        source_kind="manual",
        source_name="Delivery Knowledge Base",
        source_uri=None,
        chunk_index=0,
        chunk_text="Validate the token endpoint and client credentials.",
        distance=0.2,
        similarity_score=0.8,
    )
    citation = AgentKnowledgeCitation(
        citation_id="K1",
        rank=1,
        chunk_id=101,
        document_id=11,
        document_title="API Authentication Guide",
        scope_type="global",
        doc_type="runbook",
        source_kind="manual",
        source_name="Delivery Knowledge Base",
        source_uri=None,
        chunk_index=0,
        chunk_text="Validate the token endpoint and client credentials.",
        similarity_score=0.8,
    )
    return AgentSearchKnowledgeOutput(
        retrieval_status="succeeded",
        retrieval_query="token exchange authentication failure",
        knowledge_evidence=(evidence,),
        knowledge_citations=(citation,),
        retrieval_error_code=None,
    )


def history_item(
    *,
    feedback_status: str = "accepted",
) -> AgentAnalysisHistoryItem:
    now = datetime(2026, 7, 28, tzinfo=timezone.utc)
    return AgentAnalysisHistoryItem(
        analysis_id=67,
        issue_id=17,
        analysis_type="issue_summarizer",
        provider="llm",
        model_name="gpt-test",
        prompt_version="issue_summarizer_v4_grounded",
        issue_summary="A prior accepted analysis exists.",
        possible_root_cause="Token refresh timing may be inconsistent.",
        recommended_actions=(
            "Compare token refresh timing.",
        ),
        customer_update_draft="A prior update was accepted.",
        risk_level="high",
        project_impact="Testing may be delayed.",
        feedback_status=feedback_status,
        feedback_note="Reviewed by delivery lead.",
        edited_output=(
            "Human-reviewed prior analysis."
            if feedback_status == "edited_and_accepted"
            else None
        ),
        retrieval_status="not_attempted",
        retrieval_query=None,
        knowledge_citations=(),
        retrieval_error_code=None,
        knowledge_grounded=False,
        created_at=now,
        updated_at=now,
    )


def risk_output() -> AgentDeliveryRiskOutput:
    return AgentDeliveryRiskOutput(
        project_id=7,
        overdue_requirements=2,
        blocked_issues=1,
        critical_issues=1,
        delivery_completion_rate=0.75,
        risk_level="high",
    )


def tool_result(
    tool_name: str,
    call_identity: str,
    result_json: dict[str, object],
) -> dict[str, object]:
    return {
        "tool_name": tool_name,
        "tool_version": "tool_v0.1",
        "call_identity": call_identity,
        "arguments": {"issue_id": 17},
        "result_json": result_json,
        "execution_status": "completed",
    }


def evidence_envelope(
    tool_name: str,
    call_identity: str,
    evidence_type: str,
    payload: dict[str, object],
) -> dict[str, object]:
    return {
        "source_tool": tool_name,
        "source_call_identity": call_identity,
        "evidence_type": evidence_type,
        "payload": payload,
    }


def base_state() -> dict[str, object]:
    output = knowledge_output()
    return {
        "issue_id": 17,
        "issue_context": issue_context(),
        "selected_tool": None,
        "tool_results": [
            tool_result(
                "search_knowledge",
                "search-1",
                output.model_dump(mode="json"),
            ),
        ],
        "retrieved_evidence": [
            evidence_envelope(
                "search_knowledge",
                "search-1",
                "knowledge_chunk",
                output.knowledge_evidence[0].model_dump(
                    mode="json"
                ),
            ),
        ],
        "evidence_sufficient": True,
        "evidence_reason": "Grounded knowledge is sufficient.",
    }


def service(
    provider: StubProvider | None = None,
) -> tuple[AgentAnalysisGenerationService, StubProvider]:
    actual_provider = provider or StubProvider()
    return (
        AgentAnalysisGenerationService(
            analysis_provider=actual_provider
        ),
        actual_provider,
    )


def test_version_and_state_key_contract() -> None:
    assert AGENT_ANALYSIS_GENERATION_VERSION == (
        "agent_analysis_generation_v0.1"
    )
    assert GENERATED_ANALYSIS_STATE_KEY == "generated_analysis"


def test_happy_path_uses_all_evidence_types() -> None:
    state = base_state()
    history = history_item(
        feedback_status="edited_and_accepted"
    )
    state["tool_results"].extend(
        [
            tool_result(
                "get_analysis_history",
                "history-1",
                {
                    "issue_id": 17,
                    "analysis_count": 1,
                    "analyses": [
                        history.model_dump(mode="json")
                    ],
                },
            ),
            tool_result(
                "calculate_delivery_risk",
                "risk-1",
                risk_output().model_dump(mode="json"),
            ),
        ]
    )
    state["retrieved_evidence"].append(
        evidence_envelope(
            "get_analysis_history",
            "history-1",
            "analysis_history",
            history.model_dump(mode="json"),
        )
    )
    state["clarification_response"] = (
        "Customer confirmed the failure began after rollout."
    )
    original = deepcopy(state)
    generator, provider = service()

    outcome = generator.generate(state)

    assert state == original
    assert len(provider.contexts) == 1
    context = provider.contexts[0]
    assert context.issue["id"] == 17
    assert context.project["name"] == "Enterprise Delivery"
    assert context.customer["name"] == "Example Customer"
    assert len(context.knowledge_evidence) == 1
    assert tuple(
        item.evidence_type
        for item in context.supplemental_evidence
    ) == (
        "analysis_history",
        "human_clarification",
        "delivery_risk",
    )
    update = outcome.to_state_update()
    generated = update[GENERATED_ANALYSIS_STATE_KEY]
    assert generated["provider"] == "llm"
    assert generated["model_name"] == "gpt-test"
    assert generated["retrieval_status"] == "succeeded"
    assert generated["supplemental_evidence_count"] == 3
    json.dumps(update, ensure_ascii=False)


def test_history_only_maps_to_supplemental_evidence() -> None:
    history = history_item()
    state = base_state()
    state["tool_results"] = [
        tool_result(
            "get_analysis_history",
            "history-1",
            {
                "issue_id": 17,
                "analysis_count": 1,
                "analyses": [history.model_dump(mode="json")],
            },
        )
    ]
    state["retrieved_evidence"] = [
        evidence_envelope(
            "get_analysis_history",
            "history-1",
            "analysis_history",
            history.model_dump(mode="json"),
        )
    ]
    generator, provider = service()

    outcome = generator.generate(state)

    context = provider.contexts[0]
    assert context.retrieval_query is None
    assert context.knowledge_evidence == ()
    assert len(context.supplemental_evidence) == 1
    assert outcome.to_state_update()[
        GENERATED_ANALYSIS_STATE_KEY
    ]["retrieval_status"] == "not_attempted"


def test_clarification_only_is_supported() -> None:
    state = base_state()
    state["tool_results"] = []
    state["retrieved_evidence"] = []
    state["clarification_response"] = (
        "Customer confirmed that only the new environment is affected."
    )
    generator, provider = service()

    generator.generate(state)

    supplemental = provider.contexts[0].supplemental_evidence
    assert len(supplemental) == 1
    assert supplemental[0].evidence_type == "human_clarification"


def test_fallback_provider_metadata_is_controlled() -> None:
    provider = StubProvider(
        provider_name="rule_based_fallback",
        model_name="must-be-cleared",
        fallback_reason="missing_api_key",
    )
    generator, _ = service(provider)

    outcome = generator.generate(base_state())

    generated = outcome.to_state_update()[
        GENERATED_ANALYSIS_STATE_KEY
    ]
    assert generated["provider"] == "rule_based_fallback"
    assert generated["model_name"] is None
    assert generated["provider_fallback_reason"] == (
        "missing_api_key"
    )


def test_rejected_history_is_not_in_prompt() -> None:
    state = base_state()
    history = history_item(feedback_status="rejected")
    state["tool_results"].append(
        tool_result(
            "get_analysis_history",
            "history-1",
            {
                "issue_id": 17,
                "analysis_count": 1,
                "analyses": [history.model_dump(mode="json")],
            },
        )
    )
    state["retrieved_evidence"].append(
        evidence_envelope(
            "get_analysis_history",
            "history-1",
            "analysis_history",
            history.model_dump(mode="json"),
        )
    )
    generator, provider = service()

    generator.generate(state)

    assert provider.contexts[0].supplemental_evidence == ()


def test_non_mapping_state_is_rejected() -> None:
    generator, _ = service()
    expect_error(
        "invalid_agent_state",
        lambda: generator.generate([]),
    )


def test_insufficient_evidence_is_rejected() -> None:
    state = base_state()
    state["evidence_sufficient"] = False
    generator, _ = service()
    expect_error(
        "evidence_not_sufficient",
        lambda: generator.generate(state),
    )


def test_pending_selected_tool_is_rejected() -> None:
    state = base_state()
    state["selected_tool"] = {"tool_name": "search_knowledge"}
    generator, _ = service()
    expect_error(
        "tool_execution_incomplete",
        lambda: generator.generate(state),
    )


def test_issue_context_fields_are_frozen() -> None:
    state = base_state()
    state["issue_context"]["unexpected"] = "value"
    generator, _ = service()
    expect_error(
        "invalid_issue_context",
        lambda: generator.generate(state),
    )


def test_issue_id_must_be_positive() -> None:
    state = base_state()
    state["issue_context"]["issue_id"] = 0
    generator, _ = service()
    expect_error(
        "invalid_issue_context",
        lambda: generator.generate(state),
    )


def test_tool_results_must_be_sequence() -> None:
    state = base_state()
    state["tool_results"] = None
    generator, _ = service()
    expect_error(
        "invalid_tool_results",
        lambda: generator.generate(state),
    )


def test_duplicate_search_results_are_rejected() -> None:
    state = base_state()
    state["tool_results"].append(
        deepcopy(state["tool_results"][0])
    )
    state["tool_results"][1]["call_identity"] = "search-2"
    generator, _ = service()
    expect_error(
        "duplicate_tool_results",
        lambda: generator.generate(state),
    )


def test_orphan_evidence_is_rejected() -> None:
    state = base_state()
    state["tool_results"] = []
    generator, _ = service()
    expect_error(
        "orphan_retrieved_evidence",
        lambda: generator.generate(state),
    )


def test_knowledge_payload_mismatch_is_rejected() -> None:
    state = base_state()
    state["retrieved_evidence"][0]["payload"][
        "chunk_text"
    ] = "Changed evidence text"
    generator, _ = service()
    expect_error(
        "knowledge_evidence_mismatch",
        lambda: generator.generate(state),
    )


def test_invalid_search_schema_is_controlled() -> None:
    state = base_state()
    state["tool_results"][0]["result_json"][
        "retrieval_status"
    ] = "unknown"
    generator, _ = service()
    expect_error(
        "invalid_search_result",
        lambda: generator.generate(state),
    )


def test_invalid_history_schema_is_controlled() -> None:
    state = base_state()
    state["tool_results"] = [
        tool_result(
            "get_analysis_history",
            "history-1",
            {"issue_id": 17, "analysis_count": 1, "analyses": []},
        )
    ]
    state["retrieved_evidence"] = [
        evidence_envelope(
            "get_analysis_history",
            "history-1",
            "analysis_history",
            {"analysis_id": 67},
        )
    ]
    generator, _ = service()
    expect_error(
        "invalid_history_evidence",
        lambda: generator.generate(state),
    )


def test_invalid_risk_schema_is_controlled() -> None:
    state = base_state()
    state["tool_results"].append(
        tool_result(
            "calculate_delivery_risk",
            "risk-1",
            {"project_id": 7},
        )
    )
    generator, _ = service()
    expect_error(
        "invalid_delivery_risk_result",
        lambda: generator.generate(state),
    )


def test_risk_only_is_not_primary_evidence() -> None:
    state = base_state()
    state["tool_results"] = [
        tool_result(
            "calculate_delivery_risk",
            "risk-1",
            risk_output().model_dump(mode="json"),
        )
    ]
    state["retrieved_evidence"] = []
    generator, _ = service()
    expect_error(
        "missing_generation_evidence",
        lambda: generator.generate(state),
    )


def test_invalid_provider_result_is_controlled() -> None:
    provider = StubProvider(result=object())
    generator, _ = service(provider)
    expect_error(
        "invalid_analysis_result",
        lambda: generator.generate(base_state()),
    )


def test_service_is_transaction_neutral() -> None:
    source = SERVICE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_names: set[str] = set()
    calls: set[str] = set()

    def dotted_name(node: ast.AST) -> str | None:
        parts: list[str] = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            return ".".join(reversed(parts))
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module)
        if isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
        if isinstance(node, ast.Call):
            name = dotted_name(node.func)
            if name is not None:
                calls.add(name)

    assert not any(
        name.startswith("sqlalchemy")
        for name in imported_names
    )
    assert not any(
        name.endswith(
            "agent_persistence_service"
        )
        for name in imported_names
    )
    assert not {
        "db.add",
        "db.commit",
        "db.rollback",
        "db.refresh",
        "db.flush",
        "db.delete",
    }.intersection(calls)


def main() -> None:
    tests = (
        test_version_and_state_key_contract,
        test_happy_path_uses_all_evidence_types,
        test_history_only_maps_to_supplemental_evidence,
        test_clarification_only_is_supported,
        test_fallback_provider_metadata_is_controlled,
        test_rejected_history_is_not_in_prompt,
        test_non_mapping_state_is_rejected,
        test_insufficient_evidence_is_rejected,
        test_pending_selected_tool_is_rejected,
        test_issue_context_fields_are_frozen,
        test_issue_id_must_be_positive,
        test_tool_results_must_be_sequence,
        test_duplicate_search_results_are_rejected,
        test_orphan_evidence_is_rejected,
        test_knowledge_payload_mismatch_is_rejected,
        test_invalid_search_schema_is_controlled,
        test_invalid_history_schema_is_controlled,
        test_invalid_risk_schema_is_controlled,
        test_risk_only_is_not_primary_evidence,
        test_invalid_provider_result_is_controlled,
        test_service_is_transaction_neutral,
    )

    for test in tests:
        test()
        print(f"passed={test.__name__}")

    print(
        "Agent analysis generation service assertions "
        f"passed: {len(tests)}/{len(tests)}"
    )
    print(f"passed_count={len(tests)}")


if __name__ == "__main__":
    main()
