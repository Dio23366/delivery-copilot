from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from pydantic import BaseModel, ConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.agent_tool_contract_service import (  # noqa: E402
    AGENT_TOOL_CALL_IDENTITY_VERSION,
    AgentToolContractError,
    AgentToolContractService,
    agent_tool_contract_service,
)
from app.services.agent_tool_registry import (  # noqa: E402
    AgentToolDefinition,
    ApprovedAgentToolRegistry,
)


def expect_contract_error(
    operation,
    *,
    error_code: str,
) -> AgentToolContractError:
    try:
        operation()
    except AgentToolContractError as exc:
        assert exc.error_code == error_code
        return exc
    raise AssertionError("Expected AgentToolContractError")


def knowledge_success_result() -> dict[str, object]:
    evidence = {
        "citation_id": "K1",
        "rank": 1,
        "chunk_id": 11,
        "document_id": 21,
        "document_title": "API Troubleshooting",
        "scope_type": "global",
        "doc_type": "runbook",
        "source_kind": "manual",
        "source_name": "Enterprise Runbook",
        "source_uri": None,
        "chunk_index": 0,
        "chunk_text": "Validate authentication.",
        "distance": 0.1,
        "similarity_score": 0.9,
    }
    citation = dict(evidence)
    citation.pop("distance")
    return {
        "retrieval_status": "succeeded",
        "retrieval_query": " API authentication ",
        "knowledge_evidence": [evidence],
        "knowledge_citations": [citation],
        "retrieval_error_code": None,
    }


def history_result() -> dict[str, object]:
    timestamp = datetime(
        2026,
        7,
        17,
        9,
        30,
        tzinfo=timezone.utc,
    )
    return {
        "issue_id": 17,
        "analysis_count": 1,
        "analyses": [
            {
                "analysis_id": 68,
                "issue_id": 17,
                "analysis_type": "issue_summarizer",
                "provider": "rule_based_fallback",
                "model_name": None,
                "prompt_version": None,
                "issue_summary": "Authentication is failing.",
                "possible_root_cause": "Further validation is required.",
                "recommended_actions": ["Validate token scope."],
                "customer_update_draft": "We are investigating.",
                "risk_level": "high",
                "project_impact": "Timeline risk exists.",
                "feedback_status": "pending",
                "feedback_note": None,
                "edited_output": None,
                "retrieval_status": "not_attempted",
                "retrieval_query": None,
                "knowledge_citations": [],
                "retrieval_error_code": None,
                "knowledge_grounded": False,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        ],
    }


def risk_result() -> dict[str, object]:
    return {
        "project_id": 3,
        "overdue_requirements": 1,
        "blocked_issues": 1,
        "critical_issues": 0,
        "delivery_completion_rate": 0.5,
        "risk_level": "medium",
    }


def test_identity_version_constant() -> None:
    assert (
        AGENT_TOOL_CALL_IDENTITY_VERSION
        == "agent_tool_call_identity_v0.1"
    )
    print("PASS: call identity version")


def test_registry_binding() -> None:
    assert agent_tool_contract_service.registry.list_names() == (
        "search_knowledge",
        "get_analysis_history",
        "calculate_delivery_risk",
    )
    print("PASS: approved Registry binding")


def test_validate_knowledge_arguments() -> None:
    validated = agent_tool_contract_service.validate_arguments(
        "search_knowledge",
        {"issue_id": 17},
    )
    assert validated.tool_version == "grounded_retrieval_v1"
    assert validated.input_schema_name == (
        "AgentSearchKnowledgeInput"
    )
    assert validated.as_dict() == {"issue_id": 17}
    assert validated.canonical_arguments_json == (
        '{"issue_id":17}'
    )
    print("PASS: knowledge arguments")


def test_validate_history_and_risk_arguments() -> None:
    history = agent_tool_contract_service.validate_arguments(
        "get_analysis_history",
        {"issue_id": 17},
    )
    risk = agent_tool_contract_service.validate_arguments(
        "calculate_delivery_risk",
        {"issue_id": 17},
    )
    assert history.as_dict() == {"issue_id": 17}
    assert risk.as_dict() == {"issue_id": 17}
    print("PASS: history and risk arguments")


def test_stable_call_identity() -> None:
    first = agent_tool_contract_service.validate_arguments(
        "search_knowledge",
        {"issue_id": 17},
    )
    second = agent_tool_contract_service.validate_arguments(
        "search_knowledge",
        {"issue_id": 17},
    )
    assert first.call_identity == second.call_identity
    assert first.call_identity.startswith("search_knowledge:")
    assert len(first.call_identity.split(":", maxsplit=1)[1]) == 64
    print("PASS: stable call identity")


def test_identity_changes_by_tool_or_arguments() -> None:
    knowledge = agent_tool_contract_service.validate_arguments(
        "search_knowledge",
        {"issue_id": 17},
    )
    different_issue = (
        agent_tool_contract_service.validate_arguments(
            "search_knowledge",
            {"issue_id": 18},
        )
    )
    history = agent_tool_contract_service.validate_arguments(
        "get_analysis_history",
        {"issue_id": 17},
    )
    assert knowledge.call_identity != different_issue.call_identity
    assert knowledge.call_identity != history.call_identity
    print("PASS: identity distinguishes Tool and arguments")


def test_unapproved_tool_rejected() -> None:
    expect_contract_error(
        lambda: agent_tool_contract_service.validate_arguments(
            "delete_project",
            {"issue_id": 17},
        ),
        error_code="unapproved_tool",
    )
    print("PASS: unapproved Tool rejected")


def test_invalid_argument_payload_rejected() -> None:
    expect_contract_error(
        lambda: agent_tool_contract_service.validate_arguments(
            "search_knowledge",
            {"issue_id": 0},
        ),
        error_code="invalid_tool_arguments",
    )
    expect_contract_error(
        lambda: agent_tool_contract_service.validate_arguments(
            "search_knowledge",
            {
                "issue_id": 17,
                "db_session": "forbidden",
            },
        ),
        error_code="invalid_tool_arguments",
    )
    expect_contract_error(
        lambda: agent_tool_contract_service.validate_arguments(
            "search_knowledge",
            ["not", "a", "mapping"],
        ),
        error_code="invalid_tool_arguments",
    )
    print("PASS: invalid argument payload rejected")


def test_validate_knowledge_result() -> None:
    validated = agent_tool_contract_service.validate_result(
        "search_knowledge",
        knowledge_success_result(),
    )
    result = validated.as_dict()
    assert result["retrieval_query"] == "API authentication"
    assert isinstance(result["knowledge_evidence"], list)
    json.dumps(result, allow_nan=False)
    print("PASS: knowledge result")


def test_validate_history_result() -> None:
    validated = agent_tool_contract_service.validate_result(
        "get_analysis_history",
        history_result(),
    )
    result = validated.as_dict()
    created_at = result["analyses"][0]["created_at"]
    assert isinstance(created_at, str)
    assert created_at.endswith("Z")
    json.dumps(result, allow_nan=False)
    print("PASS: history result")


def test_validate_risk_result() -> None:
    validated = agent_tool_contract_service.validate_result(
        "calculate_delivery_risk",
        risk_result(),
    )
    assert validated.as_dict()["risk_level"] == "medium"
    print("PASS: delivery risk result")


def test_invalid_result_rejected() -> None:
    invalid = knowledge_success_result()
    invalid["retrieval_status"] = "failed"
    expect_contract_error(
        lambda: agent_tool_contract_service.validate_result(
            "search_knowledge",
            invalid,
        ),
        error_code="invalid_tool_result",
    )
    print("PASS: invalid Tool result rejected")


def test_result_mapping_is_immutable() -> None:
    validated = agent_tool_contract_service.validate_result(
        "calculate_delivery_risk",
        risk_result(),
    )

    def mutate() -> None:
        validated.result_json["risk_level"] = "high"

    try:
        mutate()
    except TypeError:
        pass
    else:
        raise AssertionError("Expected immutable result mapping")
    print("PASS: validated result mapping is immutable")


def test_missing_registry_schema_rejected() -> None:
    class LocalSchema(BaseModel):
        model_config = ConfigDict(extra="forbid")
        issue_id: int

    definition = AgentToolDefinition(
        tool_name="local_tool",
        tool_version="local_v1",
        description="Local test Tool.",
        adapter_target="local_target",
        timeout_seconds=1,
        input_schema_name="MissingInputSchema",
        output_schema_name="LocalSchema",
        argument_fields=("issue_id",),
        result_fields=("issue_id",),
    )
    registry = ApprovedAgentToolRegistry((definition,))
    service = AgentToolContractService(registry=registry)

    expect_contract_error(
        lambda: service.validate_arguments(
            "local_tool",
            {"issue_id": 17},
        ),
        error_code="unknown_input_schema",
    )
    assert LocalSchema(issue_id=17).issue_id == 17
    print("PASS: missing Registry schema rejected")


def test_canonical_json_rejects_non_json_values() -> None:
    expect_contract_error(
        lambda: AgentToolContractService._canonical_json(
            {"invalid": object()}
        ),
        error_code="non_json_tool_payload",
    )
    print("PASS: non-JSON payload rejected")


def test_service_source_is_side_effect_free() -> None:
    source_path = (
        BACKEND_ROOT
        / "app"
        / "services"
        / "agent_tool_contract_service.py"
    )
    source = source_path.read_text(encoding="utf-8")

    forbidden_tokens = (
        "sqlalchemy",
        "Session",
        "db.commit(",
        "db.rollback(",
        "db.refresh(",
        "db.flush(",
        "GroundedRetrievalService",
        "IssueAnalysisService",
        "calculate_risk_level(",
        "AgentToolCall(",
    )
    found = [
        token
        for token in forbidden_tokens
        if token in source
    ]
    assert not found, found
    print("PASS: contract service is side-effect free")


def main() -> None:
    tests = (
        test_identity_version_constant,
        test_registry_binding,
        test_validate_knowledge_arguments,
        test_validate_history_and_risk_arguments,
        test_stable_call_identity,
        test_identity_changes_by_tool_or_arguments,
        test_unapproved_tool_rejected,
        test_invalid_argument_payload_rejected,
        test_validate_knowledge_result,
        test_validate_history_result,
        test_validate_risk_result,
        test_invalid_result_rejected,
        test_result_mapping_is_immutable,
        test_missing_registry_schema_rejected,
        test_canonical_json_rejects_non_json_values,
        test_service_source_is_side_effect_free,
    )

    for test in tests:
        test()

    print(
        "Agent Tool contract service stub assertions passed "
        f"({len(tests)}/{len(tests)})"
    )


if __name__ == "__main__":
    main()