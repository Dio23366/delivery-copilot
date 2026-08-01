from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Protocol, TypeAlias

from app.agent_graph.state import (
    AGENT_LANGGRAPH_NODES,
    AWAIT_FINAL_REVIEW_NODE,
    AWAIT_TRIAGE_CONFIRMATION_NODE,
    EVALUATE_EVIDENCE_NODE,
    EXECUTE_TOOL_NODE,
    FINALIZE_RUN_NODE,
    FINAL_REVIEW_NODE,
    GENERATE_ANALYSIS_NODE,
    LOAD_ISSUE_NODE,
    PERSIST_ANALYSIS_NODE,
    REQUEST_CLARIFICATION_NODE,
    ROUTE_INVESTIGATION_NODE,
    SELECT_TOOL_NODE,
    TRIAGE_ISSUE_NODE,
    AgentGraphState,
    AgentGraphStateContractError,
    merge_agent_graph_state,
    validate_agent_graph_state,
)
from app.services.agent_tool_selection_service import (
    AGENT_TOOL_SELECTION_VERSION,
)


AgentGraphNode: TypeAlias = Callable[
    [AgentGraphState],
    dict[str, object],
]


class _IssueContextService(Protocol):
    def load_issue_context(
        self,
        db: object,
        *,
        issue_id: int,
    ) -> object:
        ...

    def serialize_issue_context(
        self,
        context: object,
    ) -> Mapping[str, object]:
        ...


class _InvestigationRoutingService(Protocol):
    def route(
        self,
        state: Mapping[str, object],
        *,
        step_count: int,
        tool_call_count: int,
    ) -> object:
        ...


class _ToolSelectionService(Protocol):
    def select(
        self,
        state: Mapping[str, object],
    ) -> object:
        ...


class _EvidenceEvaluationService(Protocol):
    def evaluate(
        self,
        state: Mapping[str, object],
    ) -> object:
        ...


class _ReplayAwareToolExecutionService(Protocol):
    def execute_current_step(
        self,
        db: object,
        *,
        run_id: str,
        tool_name: str,
        arguments: Mapping[str, object],
        max_tool_calls: int,
    ) -> object:
        ...


class _ToolResultStateService(Protocol):
    def apply_replay(
        self,
        state: Mapping[str, object],
        execution_outcome: object,
    ) -> object:
        ...


_SELECTED_TOOL_FIELDS = frozenset(
    {
        "selection_version",
        "tool_name",
        "tool_version",
        "arguments",
        "call_identity",
        "confidence",
        "reason",
    }
)


def _selected_tool_execution_inputs(
    state: Mapping[str, object],
) -> tuple[str, dict[str, object], int]:
    selected_tool = state.get("selected_tool")

    if not isinstance(selected_tool, Mapping):
        raise AgentGraphStateContractError(
            "Agent state must contain selected_tool"
        )

    if set(selected_tool) != _SELECTED_TOOL_FIELDS:
        raise AgentGraphStateContractError(
            "selected_tool fields do not match "
            "the frozen contract"
        )

    selection_version = selected_tool.get(
        "selection_version"
    )
    if (
        selection_version
        != AGENT_TOOL_SELECTION_VERSION
    ):
        raise AgentGraphStateContractError(
            "selected_tool selection_version "
            "is unsupported"
        )

    tool_name = selected_tool.get("tool_name")
    if (
        not isinstance(tool_name, str)
        or not tool_name.strip()
        or tool_name != tool_name.strip()
    ):
        raise AgentGraphStateContractError(
            "selected_tool tool_name must be "
            "a normalized nonblank string"
        )

    tool_version = selected_tool.get(
        "tool_version"
    )
    if (
        not isinstance(tool_version, str)
        or not tool_version.strip()
        or tool_version != tool_version.strip()
    ):
        raise AgentGraphStateContractError(
            "selected_tool tool_version must be "
            "a normalized nonblank string"
        )

    call_identity = selected_tool.get(
        "call_identity"
    )
    identity_prefix = f"{tool_name}:"
    if (
        not isinstance(call_identity, str)
        or not call_identity.startswith(
            identity_prefix
        )
        or len(
            call_identity[len(identity_prefix):]
        ) != 64
    ):
        raise AgentGraphStateContractError(
            "selected_tool call_identity is invalid"
        )

    arguments = selected_tool.get("arguments")
    if not isinstance(arguments, Mapping):
        raise AgentGraphStateContractError(
            "selected_tool arguments must be "
            "a mapping"
        )

    confidence = selected_tool.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or confidence < 0
        or confidence > 1
    ):
        raise AgentGraphStateContractError(
            "selected_tool confidence must be "
            "between 0 and 1"
        )

    reason = selected_tool.get("reason")
    if (
        not isinstance(reason, str)
        or not reason.strip()
        or reason != reason.strip()
    ):
        raise AgentGraphStateContractError(
            "selected_tool reason must be "
            "a normalized nonblank string"
        )

    max_tool_calls = state.get("max_tool_calls")
    if (
        type(max_tool_calls) is not int
        or max_tool_calls < 1
    ):
        raise AgentGraphStateContractError(
            "Agent state max_tool_calls must be "
            "a positive integer"
        )

    return (
        tool_name,
        dict(arguments),
        max_tool_calls,
    )


def _execute_tool_state_update(
    outcome: object,
) -> dict[str, object]:
    update = _decision_state_update(
        outcome,
        operation="execute_tool",
    )
    expected_fields = {
        "selected_tool",
        "tool_results",
        "retrieved_evidence",
    }

    if set(update) != expected_fields:
        raise AgentGraphStateContractError(
            "execute_tool result-state fields do not "
            "match the frozen contract"
        )

    if update["selected_tool"] is not None:
        raise AgentGraphStateContractError(
            "execute_tool must clear selected_tool"
        )

    return update


def _advance(
    state: AgentGraphState,
    *,
    node_name: str,
    extra_update: Mapping[str, object] | None = None,
) -> dict[str, object]:
    validated = validate_agent_graph_state(state)

    if node_name not in AGENT_LANGGRAPH_NODES:
        raise AgentGraphStateContractError(
            f"Unknown Agent Graph node: {node_name}"
        )

    transition_count = (
        validated["transition_count"] + 1
    )

    if transition_count > validated["max_transitions"]:
        raise AgentGraphStateContractError(
            "Agent Graph transition limit exceeded"
        )

    visited_nodes = [
        *validated.get("visited_nodes", []),
        node_name,
    ]
    update: dict[str, object] = {
        "current_node": node_name,
        "transition_count": transition_count,
        "visited_nodes": visited_nodes,
    }

    if extra_update is not None:
        update.update(dict(extra_update))

    merge_agent_graph_state(
        validated,
        update,
    )
    return update


def _decision_state_update(
    decision: object,
    *,
    operation: str,
) -> dict[str, object]:
    to_state_update = getattr(
        decision,
        "to_state_update",
        None,
    )

    if not callable(to_state_update):
        raise TypeError(
            f"{operation} must return an object "
            "with to_state_update()"
        )

    update = to_state_update()

    if not isinstance(update, Mapping):
        raise TypeError(
            f"{operation}.to_state_update() "
            "must return a mapping"
        )

    validated = validate_agent_graph_state(
        dict(update),
        allow_partial=True,
    )
    return dict(validated)


def _recording_node(
    node_name: str,
) -> AgentGraphNode:
    def node(
        state: AgentGraphState,
    ) -> dict[str, object]:
        return _advance(
            state,
            node_name=node_name,
        )

    node.__name__ = f"{node_name}_contract_node"
    return node


def build_load_issue_runtime_node(
    *,
    db: object,
    service: _IssueContextService,
) -> AgentGraphNode:
    def node(
        state: AgentGraphState,
    ) -> dict[str, object]:
        validated = validate_agent_graph_state(
            state
        )
        context = service.load_issue_context(
            db,
            issue_id=validated["issue_id"],
        )
        serialized = (
            service.serialize_issue_context(
                context
            )
        )

        if not isinstance(serialized, Mapping):
            raise TypeError(
                "load_issue serialization must "
                "return a mapping"
            )

        return _advance(
            validated,
            node_name=LOAD_ISSUE_NODE,
            extra_update={
                "issue_context": dict(serialized),
            },
        )

    node.__name__ = "load_issue_runtime_node"
    return node


def build_route_investigation_runtime_node(
    *,
    service: _InvestigationRoutingService,
) -> AgentGraphNode:
    def node(
        state: AgentGraphState,
    ) -> dict[str, object]:
        validated = validate_agent_graph_state(
            state
        )
        outcome = service.route(
            validated,
            step_count=(
                validated["transition_count"] + 1
            ),
            tool_call_count=len(
                validated.get("tool_results", [])
            ),
        )
        update = _decision_state_update(
            outcome,
            operation="route_investigation",
        )

        return _advance(
            validated,
            node_name=ROUTE_INVESTIGATION_NODE,
            extra_update=update,
        )

    node.__name__ = (
        "route_investigation_runtime_node"
    )
    return node


def build_select_tool_runtime_node(
    *,
    service: _ToolSelectionService,
) -> AgentGraphNode:
    def node(
        state: AgentGraphState,
    ) -> dict[str, object]:
        validated = validate_agent_graph_state(
            state
        )
        decision = service.select(validated)
        update = _decision_state_update(
            decision,
            operation="select_tool",
        )

        return _advance(
            validated,
            node_name=SELECT_TOOL_NODE,
            extra_update=update,
        )

    node.__name__ = "select_tool_runtime_node"
    return node


def build_execute_tool_runtime_node(
    *,
    db: object,
    execution_service: (
        _ReplayAwareToolExecutionService
    ),
    result_state_service: _ToolResultStateService,
) -> AgentGraphNode:
    def node(
        state: AgentGraphState,
    ) -> dict[str, object]:
        validated = validate_agent_graph_state(
            state
        )
        (
            tool_name,
            arguments,
            max_tool_calls,
        ) = _selected_tool_execution_inputs(
            validated
        )
        execution_outcome = (
            execution_service.execute_current_step(
                db,
                run_id=validated["run_id"],
                tool_name=tool_name,
                arguments=arguments,
                max_tool_calls=max_tool_calls,
            )
        )
        result_state_outcome = (
            result_state_service.apply_replay(
                validated,
                execution_outcome,
            )
        )
        update = _execute_tool_state_update(
            result_state_outcome
        )

        return _advance(
            validated,
            node_name=EXECUTE_TOOL_NODE,
            extra_update=update,
        )

    node.__name__ = "execute_tool_runtime_node"
    return node


def build_evaluate_evidence_runtime_node(
    *,
    service: _EvidenceEvaluationService,
) -> AgentGraphNode:
    def node(
        state: AgentGraphState,
    ) -> dict[str, object]:
        validated = validate_agent_graph_state(
            state
        )
        decision = service.evaluate(validated)
        update = _decision_state_update(
            decision,
            operation="evaluate_evidence",
        )

        return _advance(
            validated,
            node_name=EVALUATE_EVIDENCE_NODE,
            extra_update=update,
        )

    node.__name__ = (
        "evaluate_evidence_runtime_node"
    )
    return node


def execute_tool_contract_node(
    state: AgentGraphState,
) -> dict[str, object]:
    validated = validate_agent_graph_state(state)
    tool_results = [
        *validated.get("tool_results", [])
    ]
    selected_tool = validated.get("selected_tool")
    max_tool_calls = validated.get(
        "max_tool_calls",
        1,
    )

    if (
        selected_tool is not None
        and len(tool_results) < max_tool_calls
    ):
        tool_name = selected_tool.get(
            "tool_name",
            "contract_tool",
        )
        tool_results.append(
            {
                "tool_name": str(tool_name),
                "status": "simulated",
            }
        )

    return _advance(
        validated,
        node_name=EXECUTE_TOOL_NODE,
        extra_update={
            "tool_results": tool_results,
        },
    )


def generate_analysis_contract_node(
    state: AgentGraphState,
) -> dict[str, object]:
    validated = validate_agent_graph_state(state)
    generated_analysis = validated.get(
        "generated_analysis",
        {
            "status": "simulated",
            "source": "contract_topology",
        },
    )

    return _advance(
        validated,
        node_name=GENERATE_ANALYSIS_NODE,
        extra_update={
            "generated_analysis": generated_analysis,
        },
    )


def finalize_run_contract_node(
    state: AgentGraphState,
) -> dict[str, object]:
    return _advance(
        state,
        node_name=FINALIZE_RUN_NODE,
        extra_update={
            "pending_approval": False,
            "stop_reason": "completed",
        },
    )


def build_contract_node_registry(
) -> dict[str, AgentGraphNode]:
    registry: dict[str, AgentGraphNode] = {
        LOAD_ISSUE_NODE: _recording_node(
            LOAD_ISSUE_NODE
        ),
        TRIAGE_ISSUE_NODE: _recording_node(
            TRIAGE_ISSUE_NODE
        ),
        AWAIT_TRIAGE_CONFIRMATION_NODE: (
            _recording_node(
                AWAIT_TRIAGE_CONFIRMATION_NODE
            )
        ),
        ROUTE_INVESTIGATION_NODE: _recording_node(
            ROUTE_INVESTIGATION_NODE
        ),
        SELECT_TOOL_NODE: _recording_node(
            SELECT_TOOL_NODE
        ),
        EXECUTE_TOOL_NODE: (
            execute_tool_contract_node
        ),
        EVALUATE_EVIDENCE_NODE: _recording_node(
            EVALUATE_EVIDENCE_NODE
        ),
        REQUEST_CLARIFICATION_NODE: (
            _recording_node(
                REQUEST_CLARIFICATION_NODE
            )
        ),
        GENERATE_ANALYSIS_NODE: (
            generate_analysis_contract_node
        ),
        PERSIST_ANALYSIS_NODE: _recording_node(
            PERSIST_ANALYSIS_NODE
        ),
        FINAL_REVIEW_NODE: _recording_node(
            FINAL_REVIEW_NODE
        ),
        AWAIT_FINAL_REVIEW_NODE: _recording_node(
            AWAIT_FINAL_REVIEW_NODE
        ),
        FINALIZE_RUN_NODE: (
            finalize_run_contract_node
        ),
    }

    if set(registry) != AGENT_LANGGRAPH_NODES:
        raise RuntimeError(
            "Contract node registry does not match "
            "the frozen Agent Graph nodes"
        )

    return registry


AGENT_LANGGRAPH_CONTRACT_NODE_REGISTRY = (
    MappingProxyType(
        build_contract_node_registry()
    )
)
