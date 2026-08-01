from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.agent_graph.nodes import (
    AgentGraphNode,
    build_contract_node_registry,
)
from app.agent_graph.routing import (
    route_after_clarification,
    route_after_evidence_evaluation,
    route_after_final_review,
    route_after_triage_confirmation,
)
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
)


AGENT_LANGGRAPH_STATIC_EDGES = (
    (START, LOAD_ISSUE_NODE),
    (LOAD_ISSUE_NODE, TRIAGE_ISSUE_NODE),
    (
        TRIAGE_ISSUE_NODE,
        AWAIT_TRIAGE_CONFIRMATION_NODE,
    ),
    (
        ROUTE_INVESTIGATION_NODE,
        SELECT_TOOL_NODE,
    ),
    (SELECT_TOOL_NODE, EXECUTE_TOOL_NODE),
    (
        EXECUTE_TOOL_NODE,
        EVALUATE_EVIDENCE_NODE,
    ),
    (
        GENERATE_ANALYSIS_NODE,
        PERSIST_ANALYSIS_NODE,
    ),
    (
        PERSIST_ANALYSIS_NODE,
        FINAL_REVIEW_NODE,
    ),
    (
        FINAL_REVIEW_NODE,
        AWAIT_FINAL_REVIEW_NODE,
    ),
    (FINALIZE_RUN_NODE, END),
)

AGENT_LANGGRAPH_CONDITIONAL_TARGETS = {
    AWAIT_TRIAGE_CONFIRMATION_NODE: {
        "wait": END,
        "continue": ROUTE_INVESTIGATION_NODE,
    },
    EVALUATE_EVIDENCE_NODE: {
        "more_tools": SELECT_TOOL_NODE,
        "clarification": REQUEST_CLARIFICATION_NODE,
        "analysis": GENERATE_ANALYSIS_NODE,
    },
    REQUEST_CLARIFICATION_NODE: {
        "wait": END,
        "continue": SELECT_TOOL_NODE,
    },
    AWAIT_FINAL_REVIEW_NODE: {
        "wait": END,
        "continue": FINALIZE_RUN_NODE,
    },
}


def build_agent_state_graph(
    *,
    node_registry: Mapping[
        str,
        AgentGraphNode,
    ]
    | None = None,
) -> StateGraph:
    registry = dict(
        node_registry
        if node_registry is not None
        else build_contract_node_registry()
    )

    if set(registry) != AGENT_LANGGRAPH_NODES:
        raise ValueError(
            "Node registry must exactly match "
            "the frozen Agent Graph nodes"
        )

    builder = StateGraph(AgentGraphState)

    for node_name in sorted(registry):
        builder.add_node(
            node_name,
            registry[node_name],
        )

    for source, target in (
        AGENT_LANGGRAPH_STATIC_EDGES
    ):
        builder.add_edge(
            source,
            target,
        )

    builder.add_conditional_edges(
        AWAIT_TRIAGE_CONFIRMATION_NODE,
        route_after_triage_confirmation,
        AGENT_LANGGRAPH_CONDITIONAL_TARGETS[
            AWAIT_TRIAGE_CONFIRMATION_NODE
        ],
    )
    builder.add_conditional_edges(
        EVALUATE_EVIDENCE_NODE,
        route_after_evidence_evaluation,
        AGENT_LANGGRAPH_CONDITIONAL_TARGETS[
            EVALUATE_EVIDENCE_NODE
        ],
    )
    builder.add_conditional_edges(
        REQUEST_CLARIFICATION_NODE,
        route_after_clarification,
        AGENT_LANGGRAPH_CONDITIONAL_TARGETS[
            REQUEST_CLARIFICATION_NODE
        ],
    )
    builder.add_conditional_edges(
        AWAIT_FINAL_REVIEW_NODE,
        route_after_final_review,
        AGENT_LANGGRAPH_CONDITIONAL_TARGETS[
            AWAIT_FINAL_REVIEW_NODE
        ],
    )

    return builder


def compile_agent_graph(
    *,
    checkpointer: Any = None,
    node_registry: Mapping[
        str,
        AgentGraphNode,
    ]
    | None = None,
):
    return build_agent_state_graph(
        node_registry=node_registry
    ).compile(
        checkpointer=checkpointer
    )


def build_in_memory_agent_graph(
    *,
    node_registry: Mapping[
        str,
        AgentGraphNode,
    ]
    | None = None,
):
    return compile_agent_graph(
        checkpointer=InMemorySaver(),
        node_registry=node_registry,
    )
