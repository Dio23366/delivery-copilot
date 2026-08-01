from __future__ import annotations

from dataclasses import dataclass

from app.agent_graph.nodes import (
    AgentGraphNode,
    build_contract_node_registry,
    build_evaluate_evidence_runtime_node,
    build_execute_tool_runtime_node,
    build_load_issue_runtime_node,
    build_route_investigation_runtime_node,
    build_select_tool_runtime_node,
)
from app.agent_graph.state import (
    AGENT_LANGGRAPH_NODES,
    EVALUATE_EVIDENCE_NODE,
    EXECUTE_TOOL_NODE,
    LOAD_ISSUE_NODE,
    ROUTE_INVESTIGATION_NODE,
    SELECT_TOOL_NODE,
)
from app.services.agent_evidence_evaluation_service import (
    AgentEvidenceEvaluationService,
)
from app.services.agent_investigation_routing_service import (
    AgentInvestigationRoutingService,
)
from app.services.agent_issue_context_service import (
    AgentIssueContextService,
)
from app.services.agent_replay_aware_tool_execution_service import (
    AgentReplayAwareToolExecutionService,
)
from app.services.agent_tool_result_state_service import (
    AgentToolResultStateService,
)
from app.services.agent_tool_selection_service import (
    AgentToolSelectionService,
)


@dataclass(frozen=True, slots=True)
class AgentGraphRuntime:
    issue_context_service: AgentIssueContextService
    investigation_routing_service: AgentInvestigationRoutingService
    tool_selection_service: AgentToolSelectionService
    replay_aware_tool_execution_service: (
        AgentReplayAwareToolExecutionService
    )
    tool_result_state_service: AgentToolResultStateService
    evidence_evaluation_service: AgentEvidenceEvaluationService


def build_agent_graph_runtime(
    *,
    issue_context_service: AgentIssueContextService
    | None = None,
    investigation_routing_service: (
        AgentInvestigationRoutingService | None
    ) = None,
    tool_selection_service: AgentToolSelectionService
    | None = None,
    replay_aware_tool_execution_service: (
        AgentReplayAwareToolExecutionService | None
    ) = None,
    tool_result_state_service: (
        AgentToolResultStateService | None
    ) = None,
    evidence_evaluation_service: (
        AgentEvidenceEvaluationService | None
    ) = None,
) -> AgentGraphRuntime:
    return AgentGraphRuntime(
        issue_context_service=(
            issue_context_service
            if issue_context_service is not None
            else AgentIssueContextService()
        ),
        investigation_routing_service=(
            investigation_routing_service
            if investigation_routing_service
            is not None
            else AgentInvestigationRoutingService()
        ),
        tool_selection_service=(
            tool_selection_service
            if tool_selection_service is not None
            else AgentToolSelectionService()
        ),
        replay_aware_tool_execution_service=(
            replay_aware_tool_execution_service
            if replay_aware_tool_execution_service
            is not None
            else AgentReplayAwareToolExecutionService()
        ),
        tool_result_state_service=(
            tool_result_state_service
            if tool_result_state_service is not None
            else AgentToolResultStateService()
        ),
        evidence_evaluation_service=(
            evidence_evaluation_service
            if evidence_evaluation_service
            is not None
            else AgentEvidenceEvaluationService()
        ),
    )


def build_runtime_node_registry(
    *,
    runtime: AgentGraphRuntime,
    db: object,
) -> dict[str, AgentGraphNode]:
    if not isinstance(runtime, AgentGraphRuntime):
        raise TypeError(
            "runtime must be an AgentGraphRuntime"
        )

    if db is None:
        raise TypeError("db must not be None")

    registry = build_contract_node_registry()
    registry.update(
        {
            LOAD_ISSUE_NODE: (
                build_load_issue_runtime_node(
                    db=db,
                    service=(
                        runtime.issue_context_service
                    ),
                )
            ),
            ROUTE_INVESTIGATION_NODE: (
                build_route_investigation_runtime_node(
                    service=(
                        runtime
                        .investigation_routing_service
                    ),
                )
            ),
            SELECT_TOOL_NODE: (
                build_select_tool_runtime_node(
                    service=(
                        runtime.tool_selection_service
                    ),
                )
            ),
            EXECUTE_TOOL_NODE: (
                build_execute_tool_runtime_node(
                    db=db,
                    execution_service=(
                        runtime
                        .replay_aware_tool_execution_service
                    ),
                    result_state_service=(
                        runtime
                        .tool_result_state_service
                    ),
                )
            ),
            EVALUATE_EVIDENCE_NODE: (
                build_evaluate_evidence_runtime_node(
                    service=(
                        runtime
                        .evidence_evaluation_service
                    ),
                )
            ),
        }
    )

    if set(registry) != AGENT_LANGGRAPH_NODES:
        raise RuntimeError(
            "Runtime node registry does not match "
            "the frozen Agent Graph nodes"
        )

    return registry
