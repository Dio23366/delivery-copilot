from __future__ import annotations

import json
from pathlib import Path
import sys
from types import MappingProxyType


BACKEND_DIR = (
    Path(__file__).resolve().parents[1]
)

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(BACKEND_DIR),
    )

from app.agent_graph.state import (
    AGENT_GRAPH_STATE_KEYS,
    AGENT_GRAPH_STATE_REQUIRED_KEYS,
    AGENT_LANGGRAPH_DEFAULT_MAX_TRANSITIONS,
    AGENT_LANGGRAPH_GRAPH_VERSION,
    AGENT_LANGGRAPH_NODES,
    AGENT_LANGGRAPH_STATE_SCHEMA_VERSION,
    CHECKPOINT_NAMESPACE_POLICY,
    CHECKPOINT_THREAD_ID_SOURCE,
    AgentGraphStateContractError,
    assert_json_compatible,
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


def validate_requirements() -> None:
    requirements_path = (
        BACKEND_DIR / "requirements.txt"
    )
    lines = [
        line.strip()
        for line in requirements_path.read_text(
            encoding="utf-8-sig"
        ).splitlines()
        if line.strip()
    ]

    required_lines = {
        "langgraph==1.2.10",
        "langgraph-checkpoint-postgres==3.1.0",
        "psycopg[binary,pool]==3.2.10",
        "psycopg-pool==3.3.1",
    }

    check(
        required_lines.issubset(set(lines)),
        "Frozen LangGraph dependency pins are missing",
    )
    check(
        "psycopg[binary]==3.2.10"
        not in lines,
        "Old Psycopg requirement must be replaced",
    )


def main() -> int:
    validate_requirements()

    check(
        AGENT_LANGGRAPH_STATE_SCHEMA_VERSION
        == "agent_langgraph_state_v0.1",
        "Unexpected state schema version",
    )
    check(
        AGENT_LANGGRAPH_GRAPH_VERSION
        == "agent_langgraph_v0.1",
        "Unexpected graph version",
    )
    check(
        AGENT_LANGGRAPH_DEFAULT_MAX_TRANSITIONS
        == 16,
        "Unexpected transition cap",
    )
    check(
        CHECKPOINT_THREAD_ID_SOURCE
        == "AgentRun.run_id",
        "Unexpected checkpoint thread source",
    )
    check(
        CHECKPOINT_NAMESPACE_POLICY
        == "default_empty_root_namespace",
        "Unexpected checkpoint namespace policy",
    )
    check(
        len(AGENT_LANGGRAPH_NODES) == 13,
        "Frozen graph node count must be 13",
    )
    check(
        AGENT_GRAPH_STATE_REQUIRED_KEYS
        == {
            "state_schema_version",
            "run_id",
            "issue_id",
            "graph_version",
            "current_node",
            "transition_count",
            "max_transitions",
        },
        "Frozen required state keys changed",
    )

    initial = build_initial_agent_graph_state(
        run_id="run-d63c-001",
        issue_id=17,
    )

    check(
        set(initial)
        == AGENT_GRAPH_STATE_REQUIRED_KEYS,
        "Initial state must contain only required keys",
    )
    check(
        initial["current_node"] == "load_issue",
        "Initial state must start at load_issue",
    )
    check(
        initial["transition_count"] == 0,
        "Initial transition count must be zero",
    )
    check(
        initial["max_transitions"] == 16,
        "Initial transition cap mismatch",
    )

    encoded = json.dumps(
        initial,
        sort_keys=True,
    )
    check(
        "run-d63c-001" in encoded,
        "Initial state must be JSON serializable",
    )

    config = build_checkpoint_config(
        run_id="run-d63c-001"
    )
    check(
        config
        == {
            "configurable": {
                "thread_id": "run-d63c-001",
            }
        },
        "Checkpoint identity mapping mismatch",
    )

    merged = merge_agent_graph_state(
        initial,
        {
            "current_node": "triage_issue",
            "transition_count": 1,
            "issue_context": {
                "issue_id": 17,
                "title": "API timeout",
            },
            "triage_suggestion": {
                "issue_type": "API",
                "severity": "high",
            },
            "triage_attempt": 1,
            "max_retries": 2,
            "triage_confirmed": False,
            "max_steps": 20,
            "max_tool_calls": 3,
            "selected_tool": None,
            "tool_results": [],
            "retrieved_evidence": [],
            "evidence_sufficient": False,
            "evidence_reason": (
                "More evidence is required."
            ),
            "clarification_question": (
                "Which environment is affected?"
            ),
            "clarification_response": None,
            "visited_nodes": [
                "load_issue",
                "triage_issue",
            ],
        },
    )

    check(
        merged["current_node"] == "triage_issue",
        "Merged state current node mismatch",
    )
    check(
        merged["issue_context"]["issue_id"] == 17,
        "Merged state issue context mismatch",
    )
    check(
        set(merged).issubset(
            AGENT_GRAPH_STATE_KEYS
        ),
        "Merged state contains unknown keys",
    )
    validate_agent_graph_state(merged)
    assert_json_compatible(merged)

    expect_contract_error(
        lambda: validate_agent_graph_state(
            {
                **initial,
                "unknown_key": "blocked",
            }
        ),
        message="Unknown state keys must fail",
    )
    expect_contract_error(
        lambda: validate_agent_graph_state(
            {
                key: value
                for key, value in initial.items()
                if key != "run_id"
            }
        ),
        message="Missing required keys must fail",
    )
    expect_contract_error(
        lambda: build_initial_agent_graph_state(
            run_id=" ",
            issue_id=17,
        ),
        message="Blank run_id must fail",
    )
    expect_contract_error(
        lambda: build_initial_agent_graph_state(
            run_id="run-d63c-002",
            issue_id=True,
        ),
        message="Boolean issue_id must fail",
    )
    expect_contract_error(
        lambda: validate_agent_graph_state(
            {
                **initial,
                "graph_version": "wrong",
            }
        ),
        message="Wrong graph version must fail",
    )
    expect_contract_error(
        lambda: validate_agent_graph_state(
            {
                **initial,
                "current_node": "unknown",
            }
        ),
        message="Unknown graph node must fail",
    )
    expect_contract_error(
        lambda: validate_agent_graph_state(
            {
                **initial,
                "transition_count": -1,
            }
        ),
        message="Negative transition count must fail",
    )
    expect_contract_error(
        lambda: validate_agent_graph_state(
            {
                **initial,
                "max_transitions": 0,
            }
        ),
        message="Nonpositive transition cap must fail",
    )
    expect_contract_error(
        lambda: validate_agent_graph_state(
            {
                **initial,
                "pending_approval": "yes",
            }
        ),
        message="Nonboolean approval flag must fail",
    )
    expect_contract_error(
        lambda: validate_agent_graph_state(
            {
                **initial,
                "tool_results": [
                    "invalid",
                ],
            }
        ),
        message="Invalid tool result items must fail",
    )
    expect_contract_error(
        lambda: assert_json_compatible(
            {
                "value": (
                    "tuple",
                )
            }
        ),
        message="Tuple checkpoint values must fail",
    )
    expect_contract_error(
        lambda: assert_json_compatible(
            {
                "value": float("nan"),
            }
        ),
        message="NaN checkpoint values must fail",
    )
    expect_contract_error(
        lambda: assert_json_compatible(
            {
                1: "invalid",
            }
        ),
        message="Non-string JSON keys must fail",
    )
    expect_contract_error(
        lambda: build_checkpoint_config(
            run_id=" ",
        ),
        message="Blank checkpoint thread_id must fail",
    )
    expect_contract_error(
        lambda: validate_agent_graph_state(
            {
                **initial,
                "issue_context": "invalid",
            }
        ),
        message="issue_context must be a JSON object",
    )
    expect_contract_error(
        lambda: validate_agent_graph_state(
            {
                **initial,
                "triage_suggestion": [],
            }
        ),
        message="triage_suggestion must be a JSON object",
    )
    expect_contract_error(
        lambda: validate_agent_graph_state(
            {
                **initial,
                "triage_result": 1,
            }
        ),
        message="triage_result must be a JSON object",
    )
    expect_contract_error(
        lambda: validate_agent_graph_state(
            {
                **initial,
                "generated_analysis": [],
            }
        ),
        message="generated_analysis must be a JSON object",
    )
    expect_contract_error(
        lambda: validate_agent_graph_state(
            {
                **initial,
                "transition_count": 17,
                "max_transitions": 16,
            }
        ),
        message="Transition count above cap must fail",
    )

    mapping_state = validate_agent_graph_state(
        {
            **initial,
            "issue_context": MappingProxyType(
                {
                    "nested": MappingProxyType(
                        {
                            "value": 1,
                        }
                    ),
                }
            ),
            "tool_results": [
                MappingProxyType(
                    {
                        "tool_name": "search_knowledge",
                    }
                ),
            ],
        }
    )
    check(
        type(mapping_state["issue_context"])
        is dict,
        "Nested Mapping must normalize to dict",
    )
    check(
        type(
            mapping_state["issue_context"][
                "nested"
            ]
        ) is dict,
        "Nested Mapping values must normalize",
    )
    check(
        type(mapping_state["tool_results"][0])
        is dict,
        "Tool result Mapping must normalize",
    )
    json.dumps(
        mapping_state,
        sort_keys=True,
    )

    print("=== COPY THIS SUMMARY ===")
    print("stage=completed")
    print(
        "operation=validate_agent_langgraph_state_contract"
    )
    print(
        "state_schema_version="
        f"{AGENT_LANGGRAPH_STATE_SCHEMA_VERSION}"
    )
    print(
        "graph_version="
        f"{AGENT_LANGGRAPH_GRAPH_VERSION}"
    )
    print(
        "graph_node_count="
        f"{len(AGENT_LANGGRAPH_NODES)}"
    )
    print(
        "required_state_key_count="
        f"{len(AGENT_GRAPH_STATE_REQUIRED_KEYS)}"
    )
    print(
        "total_state_key_count="
        f"{len(AGENT_GRAPH_STATE_KEYS)}"
    )
    print(f"assertion_count={ASSERTION_COUNT}")
    print("json_checkpoint_contract=passed")
    print("checkpoint_identity_contract=passed")
    print(
        "checkpoint_namespace_policy="
        f"{CHECKPOINT_NAMESPACE_POLICY}"
    )
    print("checkpoint_root_config=thread_id_only")
    print("dependency_pin_contract=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())