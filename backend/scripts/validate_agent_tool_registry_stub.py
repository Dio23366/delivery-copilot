from __future__ import annotations

from pathlib import Path
import sys
from types import MappingProxyType


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.agent_tool_registry import (  # noqa: E402
    AGENT_TOOL_REGISTRY_VERSION,
    APPROVED_AGENT_TOOL_DEFINITIONS,
    APPROVED_AGENT_TOOL_NAMES,
    CALCULATE_DELIVERY_RISK_TOOL,
    GET_ANALYSIS_HISTORY_TOOL,
    SEARCH_KNOWLEDGE_TOOL,
    AgentToolDefinition,
    ApprovedAgentToolRegistry,
    approved_agent_tool_registry,
)


def expect_raises(
    exception_type: type[BaseException],
    operation,
) -> BaseException:
    try:
        operation()
    except exception_type as exc:
        return exc
    raise AssertionError(
        f"Expected {exception_type.__name__} to be raised"
    )


def test_exact_approved_tool_names() -> None:
    assert APPROVED_AGENT_TOOL_NAMES == (
        "search_knowledge",
        "get_analysis_history",
        "calculate_delivery_risk",
    )
    assert approved_agent_tool_registry.list_names() == (
        APPROVED_AGENT_TOOL_NAMES
    )
    print("PASS: exact approved tool allowlist")


def test_registry_version_and_stable_order() -> None:
    assert (
        approved_agent_tool_registry.registry_version
        == AGENT_TOOL_REGISTRY_VERSION
        == "agent_tool_registry_v0.1"
    )
    assert (
        approved_agent_tool_registry.list_definitions()
        == APPROVED_AGENT_TOOL_DEFINITIONS
    )
    print("PASS: registry version and stable order")


def test_search_knowledge_definition() -> None:
    definition = approved_agent_tool_registry.get(
        SEARCH_KNOWLEDGE_TOOL
    )
    assert definition.tool_version == "grounded_retrieval_v1"
    assert (
        definition.adapter_target
        == "AgentSearchKnowledgeToolAdapter.execute"
    )
    assert definition.timeout_seconds == 30
    assert definition.argument_fields == ("issue_id",)
    assert definition.result_fields == (
        "retrieval_status",
        "retrieval_query",
        "knowledge_evidence",
        "knowledge_citations",
        "retrieval_error_code",
    )
    assert definition.read_only is True
    assert definition.requires_approval is False
    assert definition.produces_evidence is True
    print("PASS: search_knowledge definition")


def test_analysis_history_definition() -> None:
    definition = approved_agent_tool_registry.get(
        GET_ANALYSIS_HISTORY_TOOL
    )
    assert definition.tool_version == "analysis_history_v1"
    assert (
        definition.adapter_target
        == "AgentAnalysisHistoryToolAdapter.execute"
    )
    assert definition.timeout_seconds == 10
    assert definition.argument_fields == ("issue_id",)
    assert definition.result_fields == (
        "issue_id",
        "analysis_count",
        "analyses",
    )
    assert definition.produces_evidence is True
    print("PASS: get_analysis_history definition")


def test_delivery_risk_definition() -> None:
    definition = approved_agent_tool_registry.get(
        CALCULATE_DELIVERY_RISK_TOOL
    )
    assert definition.tool_version == "delivery_risk_v1"
    assert (
        definition.adapter_target
        == "AgentDeliveryRiskToolAdapter.execute"
    )
    assert definition.timeout_seconds == 5
    assert definition.argument_fields == ("issue_id",)
    assert definition.result_fields == (
        "project_id",
        "overdue_requirements",
        "blocked_issues",
        "critical_issues",
        "delivery_completion_rate",
        "risk_level",
    )
    assert definition.produces_evidence is False
    print("PASS: calculate_delivery_risk definition")


def test_registry_lookup_guards() -> None:
    assert approved_agent_tool_registry.contains(
        SEARCH_KNOWLEDGE_TOOL
    )
    assert not approved_agent_tool_registry.contains(
        "unregistered_tool"
    )
    expect_raises(
        LookupError,
        lambda: approved_agent_tool_registry.get(
            "unregistered_tool"
        ),
    )
    expect_raises(
        ValueError,
        lambda: approved_agent_tool_registry.get("   "),
    )
    print("PASS: registry lookup guards")


def test_registry_mapping_is_immutable() -> None:
    assert isinstance(
        approved_agent_tool_registry.definitions,
        MappingProxyType,
    )

    def mutate_registry() -> None:
        approved_agent_tool_registry.definitions[
            "unregistered_tool"
        ] = APPROVED_AGENT_TOOL_DEFINITIONS[0]

    expect_raises(TypeError, mutate_registry)
    print("PASS: registry mapping is immutable")


def test_duplicate_definitions_are_rejected() -> None:
    duplicate = APPROVED_AGENT_TOOL_DEFINITIONS[0]
    expect_raises(
        ValueError,
        lambda: ApprovedAgentToolRegistry(
            (duplicate, duplicate)
        ),
    )
    print("PASS: duplicate tool definitions rejected")


def test_definition_invariants() -> None:
    base = APPROVED_AGENT_TOOL_DEFINITIONS[0]

    expect_raises(
        ValueError,
        lambda: AgentToolDefinition(
            tool_name="invalid",
            tool_version=base.tool_version,
            description=base.description,
            adapter_target=base.adapter_target,
            timeout_seconds=0,
            input_schema_name=base.input_schema_name,
            output_schema_name=base.output_schema_name,
            argument_fields=base.argument_fields,
            result_fields=base.result_fields,
        ),
    )
    expect_raises(
        ValueError,
        lambda: AgentToolDefinition(
            tool_name="invalid",
            tool_version=base.tool_version,
            description=base.description,
            adapter_target=base.adapter_target,
            timeout_seconds=1,
            input_schema_name=base.input_schema_name,
            output_schema_name=base.output_schema_name,
            argument_fields=base.argument_fields,
            result_fields=base.result_fields,
            read_only=False,
        ),
    )
    expect_raises(
        ValueError,
        lambda: AgentToolDefinition(
            tool_name="invalid",
            tool_version=base.tool_version,
            description=base.description,
            adapter_target=base.adapter_target,
            timeout_seconds=1,
            input_schema_name=base.input_schema_name,
            output_schema_name=base.output_schema_name,
            argument_fields=("issue_id", "issue_id"),
            result_fields=base.result_fields,
        ),
    )
    print("PASS: tool definition invariants")


def test_registry_source_is_side_effect_free() -> None:
    source_path = (
        BACKEND_ROOT
        / "app"
        / "services"
        / "agent_tool_registry.py"
    )
    source = source_path.read_text(encoding="utf-8")

    forbidden_tokens = (
        "from sqlalchemy",
        "import sqlalchemy",
        "Session",
        "db.commit(",
        "db.rollback(",
        "db.refresh(",
        "db.flush(",
        "IssueAnalysisService(",
        "GroundedRetrievalService(",
        "calculate_risk_level(",
    )
    found = [
        token
        for token in forbidden_tokens
        if token in source
    ]
    assert not found, found
    print("PASS: registry source is side-effect free")


def main() -> None:
    tests = (
        test_exact_approved_tool_names,
        test_registry_version_and_stable_order,
        test_search_knowledge_definition,
        test_analysis_history_definition,
        test_delivery_risk_definition,
        test_registry_lookup_guards,
        test_registry_mapping_is_immutable,
        test_duplicate_definitions_are_rejected,
        test_definition_invariants,
        test_registry_source_is_side_effect_free,
    )

    for test in tests:
        test()

    print(
        "Agent tool registry stub assertions passed "
        f"({len(tests)}/{len(tests)})"
    )


if __name__ == "__main__":
    main()