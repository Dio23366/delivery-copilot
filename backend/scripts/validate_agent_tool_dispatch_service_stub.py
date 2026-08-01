from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType
from pathlib import Path
import operator
import sys

from pydantic import BaseModel


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.schemas.agent_tools import (
    AgentAnalysisHistoryOutput,
    AgentDeliveryRiskOutput,
    AgentSearchKnowledgeOutput,
)
from app.services.agent_tool_contract_service import (
    ValidatedAgentToolArguments,
    agent_tool_contract_service,
)
from app.services.agent_tool_dispatch_service import (
    DEFAULT_AGENT_TOOL_ADAPTERS,
    AgentToolDispatchError,
    AgentToolDispatchService,
    agent_tool_dispatch_service,
)
from app.services.agent_tool_registry import (
    approved_agent_tool_registry,
)


def expect_raises(
    exception_type: type[BaseException],
    callback: Callable[[], object],
) -> BaseException:
    try:
        callback()
    except exception_type as exc:
        return exc
    raise AssertionError(
        f"Expected {exception_type.__name__} to be raised"
    )


class RecordingAdapter:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[
            tuple[dict[str, object], object]
        ] = []

    def __call__(
        self,
        *,
        db: object,
        **arguments: object,
    ) -> object:
        self.calls.append((dict(arguments), db))
        return self.result


class RaisingAdapter:
    def __call__(
        self,
        *,
        db: object,
        **arguments: object,
    ) -> BaseModel:
        raise LookupError("adapter business failure")


def build_results() -> dict[str, BaseModel]:
    return {
        "search_knowledge": AgentSearchKnowledgeOutput(
            retrieval_status="no_results",
            retrieval_query="controlled query",
            knowledge_evidence=(),
            knowledge_citations=(),
            retrieval_error_code=None,
        ),
        "get_analysis_history": (
            AgentAnalysisHistoryOutput(
                issue_id=17,
                analysis_count=0,
                analyses=(),
            )
        ),
        "calculate_delivery_risk": (
            AgentDeliveryRiskOutput(
                project_id=9,
                overdue_requirements=0,
                blocked_issues=0,
                critical_issues=0,
                delivery_completion_rate=1.0,
                risk_level="low",
            )
        ),
    }


def build_recording_service() -> tuple[
    AgentToolDispatchService,
    dict[str, RecordingAdapter],
]:
    results = build_results()
    recorders: dict[str, RecordingAdapter] = {}
    mapping: dict[str, RecordingAdapter] = {}

    for definition in (
        approved_agent_tool_registry.list_definitions()
    ):
        recorder = RecordingAdapter(
            results[definition.tool_name]
        )
        recorders[definition.tool_name] = recorder
        mapping[definition.adapter_target] = recorder

    return (
        AgentToolDispatchService(adapters=mapping),
        recorders,
    )


def test_default_mapping_covers_registry() -> None:
    expected = {
        definition.adapter_target
        for definition in (
            approved_agent_tool_registry
            .list_definitions()
        )
    }
    assert set(DEFAULT_AGENT_TOOL_ADAPTERS) == expected
    assert set(
        agent_tool_dispatch_service.adapters
    ) == expected
    print("PASS: default mapping covers Registry exactly")


def test_adapter_mapping_is_immutable() -> None:
    assert isinstance(
        DEFAULT_AGENT_TOOL_ADAPTERS,
        MappingProxyType,
    )
    assert isinstance(
        agent_tool_dispatch_service.adapters,
        MappingProxyType,
    )
    expect_raises(
        TypeError,
        lambda: operator.setitem(
            agent_tool_dispatch_service.adapters,
            "unexpected",
            lambda **_: None,
        ),
    )
    print("PASS: adapter mapping is immutable")


def test_all_approved_tools_dispatch() -> None:
    service, recorders = build_recording_service()
    db_marker = object()

    cases = (
        (
            "search_knowledge",
            {"issue_id": 17},
            AgentSearchKnowledgeOutput,
        ),
        (
            "get_analysis_history",
            {"issue_id": 17},
            AgentAnalysisHistoryOutput,
        ),
        (
            "calculate_delivery_risk",
            {"issue_id": 17},
            AgentDeliveryRiskOutput,
        ),
    )

    for tool_name, arguments, result_type in cases:
        validated = (
            agent_tool_contract_service
            .validate_arguments(
                tool_name,
                arguments,
            )
        )
        result = service.execute(
            validated,
            db_marker,
        )
        assert isinstance(result, result_type)
        assert recorders[tool_name].calls == [
            ({"issue_id": 17}, db_marker)
        ]

    print("PASS: all approved Tools dispatch explicitly")


def test_normalized_arguments_are_forwarded() -> None:
    service, recorders = build_recording_service()
    validated = (
        agent_tool_contract_service.validate_arguments(
            "search_knowledge",
            {"issue_id": "17"},
        )
    )

    service.execute(validated, object())

    assert (
        recorders["search_knowledge"]
        .calls[0][0]
        == {"issue_id": 17}
    )
    print("PASS: normalized arguments are forwarded")


def test_unapproved_tool_is_rejected() -> None:
    invalid = ValidatedAgentToolArguments(
        tool_name="unapproved_tool",
        tool_version="v1",
        input_schema_name="UnknownInput",
        arguments_json=MappingProxyType(
            {"issue_id": 17}
        ),
        canonical_arguments_json='{"issue_id":17}',
        call_identity="unapproved_tool:digest",
    )

    error = expect_raises(
        AgentToolDispatchError,
        lambda: agent_tool_dispatch_service.execute(
            invalid,
            object(),
        ),
    )
    assert error.error_code == "unapproved_tool"
    print("PASS: unapproved Tool is rejected")


def test_tool_version_mismatch_is_rejected() -> None:
    valid = (
        agent_tool_contract_service.validate_arguments(
            "search_knowledge",
            {"issue_id": 17},
        )
    )
    invalid = ValidatedAgentToolArguments(
        tool_name=valid.tool_name,
        tool_version="wrong_version",
        input_schema_name=valid.input_schema_name,
        arguments_json=valid.arguments_json,
        canonical_arguments_json=(
            valid.canonical_arguments_json
        ),
        call_identity=valid.call_identity,
    )

    error = expect_raises(
        AgentToolDispatchError,
        lambda: agent_tool_dispatch_service.execute(
            invalid,
            object(),
        ),
    )
    assert error.error_code == "tool_version_mismatch"
    print("PASS: Tool version mismatch is rejected")


def test_input_schema_mismatch_is_rejected() -> None:
    valid = (
        agent_tool_contract_service.validate_arguments(
            "search_knowledge",
            {"issue_id": 17},
        )
    )
    invalid = ValidatedAgentToolArguments(
        tool_name=valid.tool_name,
        tool_version=valid.tool_version,
        input_schema_name="WrongInputSchema",
        arguments_json=valid.arguments_json,
        canonical_arguments_json=(
            valid.canonical_arguments_json
        ),
        call_identity=valid.call_identity,
    )

    error = expect_raises(
        AgentToolDispatchError,
        lambda: agent_tool_dispatch_service.execute(
            invalid,
            object(),
        ),
    )
    assert error.error_code == "input_schema_mismatch"
    print("PASS: input schema mismatch is rejected")


def test_missing_mapping_is_rejected() -> None:
    mapping = dict(DEFAULT_AGENT_TOOL_ADAPTERS)
    mapping.pop(
        "AgentSearchKnowledgeToolAdapter.execute"
    )
    error = expect_raises(
        ValueError,
        lambda: AgentToolDispatchService(
            adapters=mapping
        ),
    )
    assert "missing=" in str(error)
    print("PASS: missing Registry target is rejected")


def test_unexpected_mapping_is_rejected() -> None:
    mapping = dict(DEFAULT_AGENT_TOOL_ADAPTERS)
    mapping["UnexpectedAdapter.execute"] = (
        lambda **_: AgentSearchKnowledgeOutput(
            retrieval_status="no_results",
            retrieval_query="query",
        )
    )
    error = expect_raises(
        ValueError,
        lambda: AgentToolDispatchService(
            adapters=mapping
        ),
    )
    assert "unexpected=" in str(error)
    print("PASS: unexpected adapter target is rejected")


def test_non_callable_mapping_is_rejected() -> None:
    mapping = dict(DEFAULT_AGENT_TOOL_ADAPTERS)
    mapping[
        "AgentSearchKnowledgeToolAdapter.execute"
    ] = object()
    expect_raises(
        TypeError,
        lambda: AgentToolDispatchService(
            adapters=mapping
        ),
    )
    print("PASS: non-callable adapter is rejected")


def test_non_pydantic_output_is_rejected() -> None:
    service, _ = build_recording_service()
    mapping = dict(service.adapters)
    mapping[
        "AgentSearchKnowledgeToolAdapter.execute"
    ] = RecordingAdapter({"not": "pydantic"})
    invalid_service = AgentToolDispatchService(
        adapters=mapping
    )
    validated = (
        agent_tool_contract_service.validate_arguments(
            "search_knowledge",
            {"issue_id": 17},
        )
    )

    error = expect_raises(
        AgentToolDispatchError,
        lambda: invalid_service.execute(
            validated,
            object(),
        ),
    )
    assert error.error_code == "invalid_adapter_output"
    print("PASS: non-Pydantic output is rejected")


def test_adapter_exception_is_not_masked() -> None:
    mapping = dict(DEFAULT_AGENT_TOOL_ADAPTERS)
    mapping[
        "AgentSearchKnowledgeToolAdapter.execute"
    ] = RaisingAdapter()
    service = AgentToolDispatchService(
        adapters=mapping
    )
    validated = (
        agent_tool_contract_service.validate_arguments(
            "search_knowledge",
            {"issue_id": 17},
        )
    )

    error = expect_raises(
        LookupError,
        lambda: service.execute(
            validated,
            object(),
        ),
    )
    assert str(error) == "adapter business failure"
    print("PASS: adapter business exception is preserved")


def test_source_is_static_and_transaction_free() -> None:
    source_path = (
        BACKEND_ROOT
        / "app"
        / "services"
        / "agent_tool_dispatch_service.py"
    )
    source = source_path.read_text(encoding="utf-8")

    forbidden = (
        "eval(",
        "exec(",
        "importlib",
        "__import__",
        "getattr(",
        "db.add(",
        "db.delete(",
        "db.commit(",
        "db.rollback(",
        "db.flush(",
        "db.refresh(",
        ".with_for_update(",
    )
    found = [
        token
        for token in forbidden
        if token in source
    ]

    assert not found, found
    assert "MappingProxyType" in source
    assert "DEFAULT_AGENT_TOOL_ADAPTERS" in source
    assert "ValidatedAgentToolArguments" in source
    print("PASS: source uses static transaction-free dispatch")


def main() -> None:
    tests = (
        test_default_mapping_covers_registry,
        test_adapter_mapping_is_immutable,
        test_all_approved_tools_dispatch,
        test_normalized_arguments_are_forwarded,
        test_unapproved_tool_is_rejected,
        test_tool_version_mismatch_is_rejected,
        test_input_schema_mismatch_is_rejected,
        test_missing_mapping_is_rejected,
        test_unexpected_mapping_is_rejected,
        test_non_callable_mapping_is_rejected,
        test_non_pydantic_output_is_rejected,
        test_adapter_exception_is_not_masked,
        test_source_is_static_and_transaction_free,
    )

    for test in tests:
        test()

    print(
        "Agent Tool Dispatch Service assertions "
        "passed (13/13)"
    )


if __name__ == "__main__":
    main()
