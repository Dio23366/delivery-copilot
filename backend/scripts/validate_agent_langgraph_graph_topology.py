from __future__ import annotations

from pathlib import Path
import sys


BACKEND_DIR = (
    Path(__file__).resolve().parents[1]
)

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(BACKEND_DIR),
    )

from langgraph.graph import END, START

from app.agent_graph.builder import (
    AGENT_LANGGRAPH_CONDITIONAL_TARGETS,
    AGENT_LANGGRAPH_STATIC_EDGES,
    build_agent_state_graph,
    build_in_memory_agent_graph,
)
from app.agent_graph.nodes import (
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
    FINALIZE_RUN_NODE,
    REQUEST_CLARIFICATION_NODE,
    AgentGraphStateContractError,
    build_checkpoint_config,
    build_initial_agent_graph_state,
    merge_agent_graph_state,
    validate_agent_graph_state,
)


ASSERTION_COUNT = 0


def check(
    condition: bool,
    message: str,
) -> None:
    global ASSERTION_COUNT
    ASSERTION_COUNT += 1

    if not condition:
        raise AssertionError(message)


def expect_contract_error(
    callback,
    *,
    message: str,
) -> None:
    global ASSERTION_COUNT
    ASSERTION_COUNT += 1

    try:
        callback()
    except AgentGraphStateContractError:
        return

    raise AssertionError(message)


def invoke(
    graph,
    *,
    run_id: str,
    update: dict[str, object] | None = None,
):
    initial = build_initial_agent_graph_state(
        run_id=run_id,
        issue_id=17,
    )

    if update is not None:
        initial = merge_agent_graph_state(
            initial,
            update,
        )

    output = graph.invoke(
        initial,
        build_checkpoint_config(
            run_id=run_id
        ),
    )
    return validate_agent_graph_state(
        output
    )


def main() -> int:
    registry = build_contract_node_registry()

    checkpoint_config = build_checkpoint_config(
        run_id="run-topology-checkpoint-config"
    )
    check(
        checkpoint_config
        == {
            "configurable": {
                "thread_id": (
                    "run-topology-checkpoint-config"
                ),
            }
        },
        "Root checkpoint config must be thread-only",
    )

    check(
        set(registry) == AGENT_LANGGRAPH_NODES,
        "Node registry must match frozen nodes",
    )
    check(
        len(registry) == 13,
        "Node registry count must be 13",
    )
    check(
        len(AGENT_LANGGRAPH_STATIC_EDGES) == 10,
        "Unexpected static-edge count",
    )
    check(
        len(
            AGENT_LANGGRAPH_CONDITIONAL_TARGETS
        )
        == 4,
        "Unexpected conditional source count",
    )
    check(
        AGENT_LANGGRAPH_STATIC_EDGES[0]
        == (START, "load_issue"),
        "Graph must start at load_issue",
    )
    check(
        AGENT_LANGGRAPH_STATIC_EDGES[-1]
        == ("finalize_run", END),
        "Graph must end after finalize_run",
    )
    check(
        set(
            AGENT_LANGGRAPH_CONDITIONAL_TARGETS[
                AWAIT_TRIAGE_CONFIRMATION_NODE
            ]
        )
        == {
            "wait",
            "continue",
        },
        "Triage route labels changed",
    )
    check(
        set(
            AGENT_LANGGRAPH_CONDITIONAL_TARGETS[
                EVALUATE_EVIDENCE_NODE
            ]
        )
        == {
            "more_tools",
            "clarification",
            "analysis",
        },
        "Evidence route labels changed",
    )
    check(
        set(
            AGENT_LANGGRAPH_CONDITIONAL_TARGETS[
                REQUEST_CLARIFICATION_NODE
            ]
        )
        == {
            "wait",
            "continue",
        },
        "Clarification route labels changed",
    )
    check(
        set(
            AGENT_LANGGRAPH_CONDITIONAL_TARGETS[
                AWAIT_FINAL_REVIEW_NODE
            ]
        )
        == {
            "wait",
            "continue",
        },
        "Final-review route labels changed",
    )

    build_agent_state_graph()
    graph = build_in_memory_agent_graph()

    base = build_initial_agent_graph_state(
        run_id="run-routing-base",
        issue_id=17,
    )
    check(
        route_after_triage_confirmation(base)
        == "wait",
        "Unconfirmed triage must wait",
    )
    check(
        route_after_triage_confirmation(
            merge_agent_graph_state(
                base,
                {
                    "triage_confirmed": True,
                },
            )
        )
        == "continue",
        "Confirmed triage must continue",
    )
    check(
        route_after_evidence_evaluation(
            merge_agent_graph_state(
                base,
                {
                    "evidence_sufficient": True,
                },
            )
        )
        == "analysis",
        "Sufficient evidence must generate analysis",
    )
    check(
        route_after_evidence_evaluation(
            merge_agent_graph_state(
                base,
                {
                    "evidence_sufficient": False,
                    "clarification_question": (
                        "Which environment?"
                    ),
                    "clarification_response": None,
                },
            )
        )
        == "clarification",
        "Open clarification must request input",
    )
    check(
        route_after_evidence_evaluation(
            merge_agent_graph_state(
                base,
                {
                    "evidence_sufficient": False,
                    "selected_tool": {
                        "tool_name": "search_knowledge",
                    },
                    "tool_results": [],
                    "max_tool_calls": 2,
                },
            )
        )
        == "more_tools",
        "Available tool budget must loop",
    )
    check(
        route_after_evidence_evaluation(
            merge_agent_graph_state(
                base,
                {
                    "evidence_sufficient": False,
                    "selected_tool": {
                        "tool_name": "search_knowledge",
                    },
                    "tool_results": [
                        {
                            "status": "simulated",
                        },
                    ],
                    "max_tool_calls": 1,
                },
            )
        )
        == "analysis",
        "Exhausted tool budget must continue to analysis",
    )
    check(
        route_after_clarification(base)
        == "wait",
        "Missing clarification response must wait",
    )
    check(
        route_after_clarification(
            merge_agent_graph_state(
                base,
                {
                    "clarification_response": (
                        "Production"
                    ),
                },
            )
        )
        == "continue",
        "Clarification response must continue",
    )
    check(
        route_after_final_review(base)
        == "wait",
        "Default final review must wait",
    )
    check(
        route_after_final_review(
            merge_agent_graph_state(
                base,
                {
                    "pending_approval": False,
                },
            )
        )
        == "continue",
        "Approved final review must continue",
    )

    triage_wait = invoke(
        graph,
        run_id="run-triage-wait",
    )
    check(
        triage_wait["current_node"]
        == AWAIT_TRIAGE_CONFIRMATION_NODE,
        "Triage wait path ended at wrong node",
    )
    check(
        triage_wait["transition_count"] == 3,
        "Triage wait transition count mismatch",
    )
    check(
        triage_wait["visited_nodes"]
        == [
            "load_issue",
            "triage_issue",
            "await_triage_confirmation",
        ],
        "Triage wait visited-node order mismatch",
    )

    clarification_wait = invoke(
        graph,
        run_id="run-clarification-wait",
        update={
            "triage_confirmed": True,
            "evidence_sufficient": False,
            "clarification_question": (
                "Which environment?"
            ),
            "clarification_response": None,
            "pending_approval": False,
        },
    )
    check(
        clarification_wait["current_node"]
        == REQUEST_CLARIFICATION_NODE,
        "Clarification path ended at wrong node",
    )
    check(
        clarification_wait["transition_count"] == 8,
        "Clarification path transition count mismatch",
    )
    check(
        clarification_wait["visited_nodes"][-2:]
        == [
            "evaluate_evidence",
            "request_clarification",
        ],
        "Clarification path tail mismatch",
    )

    final_review_wait = invoke(
        graph,
        run_id="run-final-review-wait",
        update={
            "triage_confirmed": True,
            "evidence_sufficient": True,
            "pending_approval": True,
        },
    )
    check(
        final_review_wait["current_node"]
        == AWAIT_FINAL_REVIEW_NODE,
        "Final-review wait ended at wrong node",
    )
    check(
        final_review_wait["transition_count"] == 11,
        "Final-review wait transition count mismatch",
    )
    check(
        final_review_wait["generated_analysis"][
            "source"
        ]
        == "contract_topology",
        "Analysis contract node did not run",
    )

    completed = invoke(
        graph,
        run_id="run-completed",
        update={
            "triage_confirmed": True,
            "evidence_sufficient": True,
            "pending_approval": False,
        },
    )
    check(
        completed["current_node"]
        == FINALIZE_RUN_NODE,
        "Completed path ended at wrong node",
    )
    check(
        completed["transition_count"] == 12,
        "Completed path transition count mismatch",
    )
    check(
        completed["stop_reason"] == "completed",
        "Completed path stop reason mismatch",
    )
    check(
        completed["pending_approval"] is False,
        "Completed path approval flag mismatch",
    )

    bounded_loop = invoke(
        graph,
        run_id="run-bounded-tool-loop",
        update={
            "triage_confirmed": True,
            "evidence_sufficient": False,
            "selected_tool": {
                "tool_name": "search_knowledge",
            },
            "tool_results": [],
            "max_tool_calls": 2,
            "pending_approval": False,
        },
    )
    check(
        bounded_loop["current_node"]
        == FINALIZE_RUN_NODE,
        "Bounded tool loop did not complete",
    )
    check(
        len(bounded_loop["tool_results"]) == 2,
        "Bounded tool loop count mismatch",
    )
    check(
        bounded_loop["transition_count"] == 15,
        "Bounded tool loop transition count mismatch",
    )
    check(
        bounded_loop["visited_nodes"].count(
            "execute_tool"
        )
        == 2,
        "Tool execution node must run twice",
    )
    check(
        bounded_loop["visited_nodes"].count(
            "evaluate_evidence"
        )
        == 2,
        "Evidence evaluation node must run twice",
    )

    capped = build_initial_agent_graph_state(
        run_id="run-transition-cap",
        issue_id=17,
        max_transitions=2,
    )
    capped = merge_agent_graph_state(
        capped,
        registry["load_issue"](capped),
    )
    capped = merge_agent_graph_state(
        capped,
        registry["triage_issue"](capped),
    )
    expect_contract_error(
        lambda: registry[
            "await_triage_confirmation"
        ](capped),
        message="Transition limit must fail closed",
    )

    print("=== COPY THIS SUMMARY ===")
    print("stage=completed")
    print(
        "operation=validate_agent_langgraph_graph_topology"
    )
    print(
        "graph_node_count="
        f"{len(AGENT_LANGGRAPH_NODES)}"
    )
    print(
        "static_edge_count="
        f"{len(AGENT_LANGGRAPH_STATIC_EDGES)}"
    )
    print(
        "conditional_source_count="
        f"{len(AGENT_LANGGRAPH_CONDITIONAL_TARGETS)}"
    )
    print(
        "triage_wait_transition_count="
        f"{triage_wait['transition_count']}"
    )
    print(
        "clarification_wait_transition_count="
        f"{clarification_wait['transition_count']}"
    )
    print(
        "final_review_wait_transition_count="
        f"{final_review_wait['transition_count']}"
    )
    print(
        "completed_transition_count="
        f"{completed['transition_count']}"
    )
    print(
        "bounded_loop_transition_count="
        f"{bounded_loop['transition_count']}"
    )
    print(
        "bounded_loop_tool_result_count="
        f"{len(bounded_loop['tool_results'])}"
    )
    print(f"assertion_count={ASSERTION_COUNT}")
    print("in_memory_checkpointer=passed")
    print("checkpoint_root_config=thread_id_only")
    print("conditional_routing=passed")
    print("bounded_tool_loop=passed")
    print("transition_cap=passed")
    print("database_accessed=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
