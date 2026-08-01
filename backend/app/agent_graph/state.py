from __future__ import annotations

from collections.abc import Mapping
import math
from typing import (
    NotRequired,
    Required,
    TypeAlias,
    TypedDict,
)


AGENT_LANGGRAPH_STATE_SCHEMA_VERSION = (
    "agent_langgraph_state_v0.1"
)
AGENT_LANGGRAPH_GRAPH_VERSION = (
    "agent_langgraph_v0.1"
)
AGENT_LANGGRAPH_DEFAULT_MAX_TRANSITIONS = 16

CHECKPOINT_THREAD_ID_SOURCE = "AgentRun.run_id"
CHECKPOINT_NAMESPACE_POLICY = (
    "default_empty_root_namespace"
)

LOAD_ISSUE_NODE = "load_issue"
TRIAGE_ISSUE_NODE = "triage_issue"
AWAIT_TRIAGE_CONFIRMATION_NODE = (
    "await_triage_confirmation"
)
ROUTE_INVESTIGATION_NODE = "route_investigation"
SELECT_TOOL_NODE = "select_tool"
EXECUTE_TOOL_NODE = "execute_tool"
EVALUATE_EVIDENCE_NODE = "evaluate_evidence"
REQUEST_CLARIFICATION_NODE = (
    "request_clarification"
)
GENERATE_ANALYSIS_NODE = "generate_analysis"
PERSIST_ANALYSIS_NODE = "persist_analysis"
FINAL_REVIEW_NODE = "final_review"
AWAIT_FINAL_REVIEW_NODE = "await_final_review"
FINALIZE_RUN_NODE = "finalize_run"

AGENT_LANGGRAPH_NODES = frozenset(
    {
        LOAD_ISSUE_NODE,
        TRIAGE_ISSUE_NODE,
        AWAIT_TRIAGE_CONFIRMATION_NODE,
        ROUTE_INVESTIGATION_NODE,
        SELECT_TOOL_NODE,
        EXECUTE_TOOL_NODE,
        EVALUATE_EVIDENCE_NODE,
        REQUEST_CLARIFICATION_NODE,
        GENERATE_ANALYSIS_NODE,
        PERSIST_ANALYSIS_NODE,
        FINAL_REVIEW_NODE,
        AWAIT_FINAL_REVIEW_NODE,
        FINALIZE_RUN_NODE,
    }
)

JsonScalar: TypeAlias = (
    str | int | float | bool | None
)
JsonValue: TypeAlias = (
    JsonScalar
    | list["JsonValue"]
    | dict[str, "JsonValue"]
)
JsonObject: TypeAlias = dict[str, JsonValue]


class AgentGraphState(TypedDict, total=False):
    state_schema_version: Required[str]
    run_id: Required[str]
    issue_id: Required[int]
    graph_version: Required[str]
    current_node: Required[str]
    transition_count: Required[int]
    max_transitions: Required[int]

    issue_context: NotRequired[JsonObject]
    triage_suggestion: NotRequired[JsonObject]
    triage_result: NotRequired[JsonObject]
    triage_attempt: NotRequired[int]
    max_retries: NotRequired[int]
    triage_confirmed: NotRequired[bool]

    max_steps: NotRequired[int]
    max_tool_calls: NotRequired[int]
    selected_tool: NotRequired[
        JsonObject | None
    ]
    tool_results: NotRequired[
        list[JsonObject]
    ]
    retrieved_evidence: NotRequired[
        list[JsonObject]
    ]
    evidence_sufficient: NotRequired[bool]
    evidence_reason: NotRequired[str]

    clarification_question: NotRequired[str]
    clarification_response: NotRequired[
        str | None
    ]

    generated_analysis: NotRequired[JsonObject]
    analysis_log_id: NotRequired[int]
    pending_approval: NotRequired[bool]

    visited_nodes: NotRequired[list[str]]
    stop_reason: NotRequired[str]
    error_code: NotRequired[str | None]
    error_message: NotRequired[str | None]


AGENT_GRAPH_STATE_REQUIRED_KEYS = frozenset(
    {
        "state_schema_version",
        "run_id",
        "issue_id",
        "graph_version",
        "current_node",
        "transition_count",
        "max_transitions",
    }
)
AGENT_GRAPH_STATE_KEYS = frozenset(
    AgentGraphState.__annotations__
)
AGENT_GRAPH_STATE_OPTIONAL_KEYS = frozenset(
    AGENT_GRAPH_STATE_KEYS
    - AGENT_GRAPH_STATE_REQUIRED_KEYS
)

if not AGENT_GRAPH_STATE_REQUIRED_KEYS.issubset(
    AGENT_GRAPH_STATE_KEYS
):
    raise RuntimeError(
        "Frozen required Agent Graph state keys "
        "are not declared by AgentGraphState"
    )


class AgentGraphStateContractError(
    ValueError
):
    pass


def _normalized_text(
    value: object,
    *,
    field_name: str,
) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise AgentGraphStateContractError(
            f"{field_name} must be normalized "
            "nonblank text"
        )

    return value


def _positive_int(
    value: object,
    *,
    field_name: str,
) -> int:
    if (
        type(value) is not int
        or value < 1
    ):
        raise AgentGraphStateContractError(
            f"{field_name} must be a positive integer"
        )

    return value


def _nonnegative_int(
    value: object,
    *,
    field_name: str,
) -> int:
    if (
        type(value) is not int
        or value < 0
    ):
        raise AgentGraphStateContractError(
            f"{field_name} must be a nonnegative integer"
        )

    return value


def normalize_json_compatible(
    value: object,
    *,
    path: str = "$",
) -> JsonValue:
    if (
        value is None
        or isinstance(
            value,
            (str, bool, int),
        )
    ):
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            raise AgentGraphStateContractError(
                f"{path} contains a non-finite float"
            )
        return value

    if isinstance(value, list):
        return [
            normalize_json_compatible(
                item,
                path=f"{path}[{index}]",
            )
            for index, item in enumerate(value)
        ]

    if isinstance(value, Mapping):
        normalized: JsonObject = {}

        for key, item in value.items():
            if not isinstance(key, str):
                raise AgentGraphStateContractError(
                    f"{path} contains a non-string key"
                )

            normalized[key] = (
                normalize_json_compatible(
                    item,
                    path=f"{path}.{key}",
                )
            )

        return normalized

    raise AgentGraphStateContractError(
        f"{path} contains a non-JSON value: "
        f"{type(value).__name__}"
    )


def assert_json_compatible(
    value: object,
    *,
    path: str = "$",
) -> None:
    normalize_json_compatible(
        value,
        path=path,
    )


def validate_agent_graph_state(
    state: Mapping[str, object],
    *,
    allow_partial: bool = False,
) -> AgentGraphState:
    if not isinstance(state, Mapping):
        raise AgentGraphStateContractError(
            "Agent Graph state must be a mapping"
        )

    normalized_value = normalize_json_compatible(
        state
    )

    if not isinstance(normalized_value, dict):
        raise AgentGraphStateContractError(
            "Agent Graph state must normalize "
            "to a JSON object"
        )

    normalized_state = normalized_value

    unknown_keys = set(
        normalized_state
    ).difference(
        AGENT_GRAPH_STATE_KEYS
    )

    if unknown_keys:
        raise AgentGraphStateContractError(
            "Agent Graph state contains unknown keys: "
            f"{sorted(unknown_keys)}"
        )

    if not allow_partial:
        missing_keys = (
            AGENT_GRAPH_STATE_REQUIRED_KEYS
            .difference(normalized_state)
        )

        if missing_keys:
            raise AgentGraphStateContractError(
                "Agent Graph state is missing "
                "required keys: "
                f"{sorted(missing_keys)}"
            )

    if "state_schema_version" in normalized_state:
        if (
            normalized_state["state_schema_version"]
            != AGENT_LANGGRAPH_STATE_SCHEMA_VERSION
        ):
            raise AgentGraphStateContractError(
                "state_schema_version does not match "
                "the frozen contract"
            )

    if "run_id" in normalized_state:
        _normalized_text(
            normalized_state["run_id"],
            field_name="run_id",
        )

    if "issue_id" in normalized_state:
        _positive_int(
            normalized_state["issue_id"],
            field_name="issue_id",
        )

    if "graph_version" in normalized_state:
        graph_version = _normalized_text(
            normalized_state["graph_version"],
            field_name="graph_version",
        )

        if (
            graph_version
            != AGENT_LANGGRAPH_GRAPH_VERSION
        ):
            raise AgentGraphStateContractError(
                "graph_version does not match "
                "the LangGraph graph contract"
            )

    if "current_node" in normalized_state:
        current_node = _normalized_text(
            normalized_state["current_node"],
            field_name="current_node",
        )

        if current_node not in AGENT_LANGGRAPH_NODES:
            raise AgentGraphStateContractError(
                "current_node is not part of "
                "the frozen graph"
            )

    if "transition_count" in normalized_state:
        _nonnegative_int(
            normalized_state["transition_count"],
            field_name="transition_count",
        )

    for field_name in (
        "max_transitions",
        "max_steps",
        "max_tool_calls",
        "triage_attempt",
        "analysis_log_id",
    ):
        if field_name in normalized_state:
            _positive_int(
                normalized_state[field_name],
                field_name=field_name,
            )

    if "max_retries" in normalized_state:
        _nonnegative_int(
            normalized_state["max_retries"],
            field_name="max_retries",
        )

    if (
        "transition_count" in normalized_state
        and "max_transitions" in normalized_state
        and normalized_state["transition_count"]
        > normalized_state["max_transitions"]
    ):
        raise AgentGraphStateContractError(
            "transition_count cannot exceed "
            "max_transitions"
        )

    for field_name in (
        "triage_confirmed",
        "evidence_sufficient",
        "pending_approval",
    ):
        if (
            field_name in normalized_state
            and type(
                normalized_state[field_name]
            ) is not bool
        ):
            raise AgentGraphStateContractError(
                f"{field_name} must be boolean"
            )

    for field_name in (
        "evidence_reason",
        "clarification_question",
        "stop_reason",
    ):
        if field_name in normalized_state:
            _normalized_text(
                normalized_state[field_name],
                field_name=field_name,
            )

    for field_name in (
        "clarification_response",
        "error_code",
        "error_message",
    ):
        if (
            field_name in normalized_state
            and normalized_state[field_name]
            is not None
        ):
            _normalized_text(
                normalized_state[field_name],
                field_name=field_name,
            )

    for field_name in (
        "issue_context",
        "triage_suggestion",
        "triage_result",
        "generated_analysis",
    ):
        if (
            field_name in normalized_state
            and not isinstance(
                normalized_state[field_name],
                dict,
            )
        ):
            raise AgentGraphStateContractError(
                f"{field_name} must be a JSON object"
            )

    if (
        "selected_tool" in normalized_state
        and normalized_state["selected_tool"]
        is not None
        and not isinstance(
            normalized_state["selected_tool"],
            dict,
        )
    ):
        raise AgentGraphStateContractError(
            "selected_tool must be a JSON object "
            "or None"
        )

    for field_name in (
        "tool_results",
        "retrieved_evidence",
    ):
        if field_name not in normalized_state:
            continue

        value = normalized_state[field_name]

        if not isinstance(value, list):
            raise AgentGraphStateContractError(
                f"{field_name} must be a list"
            )

        if not all(
            isinstance(item, dict)
            for item in value
        ):
            raise AgentGraphStateContractError(
                f"{field_name} items must be "
                "JSON objects"
            )

    if "visited_nodes" in normalized_state:
        visited_nodes = normalized_state[
            "visited_nodes"
        ]

        if (
            not isinstance(visited_nodes, list)
            or not all(
                isinstance(item, str)
                and item in AGENT_LANGGRAPH_NODES
                for item in visited_nodes
            )
        ):
            raise AgentGraphStateContractError(
                "visited_nodes must contain only "
                "frozen graph node names"
            )

    return normalized_state


def build_initial_agent_graph_state(
    *,
    run_id: str,
    issue_id: int,
    max_transitions: int = (
        AGENT_LANGGRAPH_DEFAULT_MAX_TRANSITIONS
    ),
) -> AgentGraphState:
    state: AgentGraphState = {
        "state_schema_version": (
            AGENT_LANGGRAPH_STATE_SCHEMA_VERSION
        ),
        "run_id": run_id,
        "issue_id": issue_id,
        "graph_version": (
            AGENT_LANGGRAPH_GRAPH_VERSION
        ),
        "current_node": LOAD_ISSUE_NODE,
        "transition_count": 0,
        "max_transitions": max_transitions,
    }

    return validate_agent_graph_state(state)


def merge_agent_graph_state(
    state: Mapping[str, object],
    update: Mapping[str, object],
) -> AgentGraphState:
    validated_state = validate_agent_graph_state(
        state
    )
    validated_update = validate_agent_graph_state(
        update,
        allow_partial=True,
    )
    merged = {
        **validated_state,
        **validated_update,
    }

    return validate_agent_graph_state(merged)


def build_checkpoint_config(
    *,
    run_id: str,
) -> dict[str, dict[str, str]]:
    normalized_run_id = _normalized_text(
        run_id,
        field_name="run_id",
    )

    return {
        "configurable": {
            "thread_id": normalized_run_id,
        }
    }
