from __future__ import annotations

import ast
from dataclasses import (
    FrozenInstanceError,
    fields,
    is_dataclass,
)
import hashlib
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(BACKEND_DIR),
    )

from app.agent_graph.builder import (  # noqa: E402
    build_agent_state_graph,
)
from app.agent_graph.nodes import (  # noqa: E402
    build_contract_node_registry,
)
from app.agent_graph.runtime import (  # noqa: E402
    AgentGraphRuntime,
    build_agent_graph_runtime,
    build_runtime_node_registry,
)
from app.agent_graph.state import (  # noqa: E402
    AGENT_GRAPH_STATE_KEYS,
    AGENT_LANGGRAPH_NODES,
    EVALUATE_EVIDENCE_NODE,
    EXECUTE_TOOL_NODE,
    LOAD_ISSUE_NODE,
    ROUTE_INVESTIGATION_NODE,
    SELECT_TOOL_NODE,
    AgentGraphStateContractError,
    build_initial_agent_graph_state,
    merge_agent_graph_state,
)
from app.services.agent_evidence_evaluation_service import (  # noqa: E402
    AgentEvidenceEvaluationService,
)
from app.services.agent_investigation_routing_service import (  # noqa: E402
    AgentInvestigationRoutingService,
)
from app.services.agent_issue_context_service import (  # noqa: E402
    AgentIssueContextService,
)
from app.services.agent_replay_aware_tool_execution_service import (  # noqa: E402
    AgentReplayAwareToolExecutionService,
)
from app.services.agent_tool_result_state_service import (  # noqa: E402
    AgentToolResultStateService,
)
from app.services.agent_tool_selection_service import (  # noqa: E402
    AgentToolSelectionService,
)


NODES_PATH = (
    BACKEND_DIR
    / "app"
    / "agent_graph"
    / "nodes.py"
)
RUNTIME_PATH = (
    BACKEND_DIR
    / "app"
    / "agent_graph"
    / "runtime.py"
)
INIT_PATH = (
    BACKEND_DIR
    / "app"
    / "agent_graph"
    / "__init__.py"
)
BUILDER_PATH = (
    BACKEND_DIR
    / "app"
    / "agent_graph"
    / "builder.py"
)
STATE_PATH = (
    BACKEND_DIR
    / "app"
    / "agent_graph"
    / "state.py"
)

EXPECTED_HASHES = {
    NODES_PATH: "7c19866f93b1c9ad8ce9aec91abec84d9b537754453cfd145c602a5c4732889a",
    RUNTIME_PATH: "a8ff3e91790a0bff9dbcf1c1c4b210a414970a5783955a16e543de678ec864f0",
    INIT_PATH: "4121837ac0c5a8ad0f2ea41647b61974d0e0f32196fef037a026b0e2ede7551f",
    BUILDER_PATH: "f6ab00a91bc28f712360a387d9db9635cc07098a9e2bf189e2241a27b77a843b",
    STATE_PATH: "cf13e5f7b435e6c2f1d2c6b3c05795a648d7396290ab36635a820cdb60e38e95",
}

TARGET_NODES = {
    LOAD_ISSUE_NODE,
    ROUTE_INVESTIGATION_NODE,
    SELECT_TOOL_NODE,
    EXECUTE_TOOL_NODE,
    EVALUATE_EVIDENCE_NODE,
}

ASSERTION_COUNT = 0


def check(
    condition: bool,
    message: str,
) -> None:
    global ASSERTION_COUNT
    ASSERTION_COUNT += 1

    if not condition:
        raise AssertionError(message)


def expect_raises(
    exception_type: type[BaseException],
    callback,
    *,
    message: str,
) -> BaseException:
    global ASSERTION_COUNT
    ASSERTION_COUNT += 1

    try:
        callback()
    except exception_type as exc:
        return exc

    raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_sha256(path: Path) -> str:
    normalized = (
        path.read_bytes()
        .replace(b"\r\n", b"\n")
        .replace(b"\r", b"\n")
    )
    return hashlib.sha256(normalized).hexdigest()


class FakeStateUpdate:
    def __init__(
        self,
        update: dict[str, object],
    ) -> None:
        self._update = dict(update)

    def to_state_update(
        self,
    ) -> dict[str, object]:
        return dict(self._update)


class FakeIssueContextService:
    def __init__(
        self,
        *,
        unsafe: bool = False,
    ) -> None:
        self.unsafe = unsafe
        self.calls: list[tuple[object, int]] = []

    def load_issue_context(
        self,
        db: object,
        *,
        issue_id: int,
    ) -> object:
        self.calls.append(
            (db, issue_id)
        )
        return {
            "issue_id": issue_id,
        }

    def serialize_issue_context(
        self,
        context: object,
    ) -> dict[str, object]:
        if self.unsafe:
            return {
                "invalid": object(),
            }

        return {
            "issue_id": 17,
            "issue_title": (
                "Runtime adapter issue"
            ),
            "severity": "high",
            "status": "investigating",
        }


class FakeInvestigationRoutingService:
    def __init__(self) -> None:
        self.calls: list[
            tuple[dict[str, object], int, int]
        ] = []

    def route(
        self,
        state,
        *,
        step_count: int,
        tool_call_count: int,
    ) -> FakeStateUpdate:
        self.calls.append(
            (
                dict(state),
                step_count,
                tool_call_count,
            )
        )
        return FakeStateUpdate(
            {
                "max_steps": 16,
                "max_tool_calls": 3,
            }
        )


class FakeToolSelectionService:
    def __init__(
        self,
        *,
        error: BaseException | None = None,
    ) -> None:
        self.error = error
        self.calls: list[
            dict[str, object]
        ] = []

    def select(
        self,
        state,
    ) -> FakeStateUpdate:
        self.calls.append(
            dict(state)
        )

        if self.error is not None:
            raise self.error

        return FakeStateUpdate(
            {
                "selected_tool": {
                    "selection_version": (
                        "agent_tool_selection_v0.1"
                    ),
                    "tool_name": (
                        "search_knowledge"
                    ),
                    "tool_version": (
                        "grounded_retrieval_v1"
                    ),
                    "arguments": {
                        "issue_id": 17,
                    },
                    "call_identity": (
                        "search_knowledge:"
                        + ("a" * 64)
                    ),
                    "confidence": 0.9,
                    "reason": (
                        "Grounded evidence is useful."
                    ),
                },
            }
        )


class FakeReplayAwareToolExecutionService:
    def __init__(
        self,
        *,
        error: BaseException | None = None,
    ) -> None:
        self.error = error
        self.calls: list[
            tuple[object, dict[str, object]]
        ] = []
        self.outcome = object()

    def execute_current_step(
        self,
        db: object,
        **kwargs: object,
    ) -> object:
        self.calls.append((db, dict(kwargs)))

        if self.error is not None:
            raise self.error

        return self.outcome


class FakeToolResultStateService:
    def __init__(
        self,
        *,
        error: BaseException | None = None,
    ) -> None:
        self.error = error
        self.calls: list[
            tuple[dict[str, object], object]
        ] = []

    def apply_replay(
        self,
        state,
        execution_outcome: object,
    ) -> FakeStateUpdate:
        self.calls.append(
            (dict(state), execution_outcome)
        )

        if self.error is not None:
            raise self.error

        selected = dict(state["selected_tool"])
        return FakeStateUpdate(
            {
                "selected_tool": None,
                "tool_results": [
                    *state.get("tool_results", []),
                    {
                        "tool_name": selected[
                            "tool_name"
                        ],
                        "tool_version": selected[
                            "tool_version"
                        ],
                        "call_identity": selected[
                            "call_identity"
                        ],
                        "arguments": dict(
                            selected["arguments"]
                        ),
                        "result_json": {
                            "retrieval_status": (
                                "no_results"
                            ),
                        },
                        "execution_status": (
                            "completed"
                        ),
                    },
                ],
                "retrieved_evidence": list(
                    state.get(
                        "retrieved_evidence",
                        [],
                    )
                ),
            }
        )


class FakeEvidenceEvaluationService:
    def __init__(self) -> None:
        self.calls: list[
            dict[str, object]
        ] = []

    def evaluate(
        self,
        state,
    ) -> FakeStateUpdate:
        self.calls.append(
            dict(state)
        )
        return FakeStateUpdate(
            {
                "evidence_sufficient": True,
                "evidence_reason": (
                    "Usable grounded evidence exists."
                ),
            }
        )


def make_runtime(
    *,
    db: object,
    issue_service: object | None = None,
    route_service: object | None = None,
    selection_service: object | None = None,
    execution_service: object | None = None,
    result_state_service: object | None = None,
    evidence_service: object | None = None,
):
    runtime = AgentGraphRuntime(
        issue_context_service=(
            issue_service
            if issue_service is not None
            else FakeIssueContextService()
        ),
        investigation_routing_service=(
            route_service
            if route_service is not None
            else FakeInvestigationRoutingService()
        ),
        tool_selection_service=(
            selection_service
            if selection_service is not None
            else FakeToolSelectionService()
        ),
        replay_aware_tool_execution_service=(
            execution_service
            if execution_service is not None
            else (
                FakeReplayAwareToolExecutionService()
            )
        ),
        tool_result_state_service=(
            result_state_service
            if result_state_service is not None
            else FakeToolResultStateService()
        ),
        evidence_evaluation_service=(
            evidence_service
            if evidence_service is not None
            else FakeEvidenceEvaluationService()
        ),
    )

    return (
        runtime,
        build_runtime_node_registry(
            runtime=runtime,
            db=db,
        ),
    )


def state_for(
    *,
    node_name: str,
    transition_count: int,
    update: dict[str, object] | None = None,
):
    state = build_initial_agent_graph_state(
        run_id=f"run-{node_name}",
        issue_id=17,
    )
    state = merge_agent_graph_state(
        state,
        {
            "current_node": node_name,
            "transition_count": (
                transition_count
            ),
        },
    )

    if update is not None:
        state = merge_agent_graph_state(
            state,
            update,
        )

    return state


def source_call_terminals(
    path: Path,
) -> set[str]:
    tree = ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )
    result: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        function = node.func

        if isinstance(function, ast.Name):
            result.add(function.id)
        elif isinstance(
            function,
            ast.Attribute,
        ):
            result.add(function.attr)

    return result


def main() -> int:
    check(
        sha256(NODES_PATH)
        == EXPECTED_HASHES[NODES_PATH],
        "nodes.py SHA256 mismatch",
    )
    check(
        sha256(RUNTIME_PATH)
        == EXPECTED_HASHES[RUNTIME_PATH],
        "runtime.py SHA256 mismatch",
    )
    check(
        normalized_sha256(INIT_PATH)
        == EXPECTED_HASHES[INIT_PATH],
        "__init__.py SHA256 mismatch",
    )
    check(
        sha256(BUILDER_PATH)
        == EXPECTED_HASHES[BUILDER_PATH],
        "builder.py SHA256 mismatch",
    )
    check(
        normalized_sha256(STATE_PATH)
        == EXPECTED_HASHES[STATE_PATH],
        "state.py SHA256 mismatch",
    )

    check(
        is_dataclass(AgentGraphRuntime),
        "AgentGraphRuntime must be a dataclass",
    )
    check(
        AgentGraphRuntime
        .__dataclass_params__
        .frozen,
        "AgentGraphRuntime must be frozen",
    )
    check(
        tuple(
            field.name
            for field in fields(
                AgentGraphRuntime
            )
        )
        == (
            "issue_context_service",
            "investigation_routing_service",
            "tool_selection_service",
            "replay_aware_tool_execution_service",
            "tool_result_state_service",
            "evidence_evaluation_service",
        ),
        "Runtime service fields changed",
    )
    check(
        not any(
            token in field.name.lower()
            for field in fields(
                AgentGraphRuntime
            )
            for token in (
                "db",
                "session",
                "checkpointer",
            )
        ),
        "Runtime must not hold DB/session/checkpointer",
    )

    default_runtime = (
        build_agent_graph_runtime()
    )
    check(
        isinstance(
            default_runtime
            .issue_context_service,
            AgentIssueContextService,
        ),
        "Default Issue Context service mismatch",
    )
    check(
        isinstance(
            default_runtime
            .investigation_routing_service,
            AgentInvestigationRoutingService,
        ),
        "Default Routing service mismatch",
    )
    check(
        isinstance(
            default_runtime
            .tool_selection_service,
            AgentToolSelectionService,
        ),
        "Default Tool Selection service mismatch",
    )
    check(
        isinstance(
            default_runtime
            .replay_aware_tool_execution_service,
            AgentReplayAwareToolExecutionService,
        ),
        "Default Replay Execution service mismatch",
    )
    check(
        isinstance(
            default_runtime
            .tool_result_state_service,
            AgentToolResultStateService,
        ),
        "Default Tool Result State service mismatch",
    )
    check(
        isinstance(
            default_runtime
            .evidence_evaluation_service,
            AgentEvidenceEvaluationService,
        ),
        "Default Evidence service mismatch",
    )

    frozen_runtime = AgentGraphRuntime(
        issue_context_service=object(),
        investigation_routing_service=object(),
        tool_selection_service=object(),
        replay_aware_tool_execution_service=object(),
        tool_result_state_service=object(),
        evidence_evaluation_service=object(),
    )
    expect_raises(
        FrozenInstanceError,
        lambda: setattr(
            frozen_runtime,
            "issue_context_service",
            object(),
        ),
        message="Runtime mutation must fail",
    )

    check(
        not any(
            token in key.lower()
            for key in AGENT_GRAPH_STATE_KEYS
            for token in (
                "runtime",
                "service",
                "session",
                "db",
            )
        ),
        "State must not hold runtime dependencies",
    )

    db = object()
    issue_service = (
        FakeIssueContextService()
    )
    route_service = (
        FakeInvestigationRoutingService()
    )
    selection_service = (
        FakeToolSelectionService()
    )
    execution_service = (
        FakeReplayAwareToolExecutionService()
    )
    result_state_service = (
        FakeToolResultStateService()
    )
    evidence_service = (
        FakeEvidenceEvaluationService()
    )
    runtime = AgentGraphRuntime(
        issue_context_service=(
            issue_service
        ),
        investigation_routing_service=(
            route_service
        ),
        tool_selection_service=(
            selection_service
        ),
        replay_aware_tool_execution_service=(
            execution_service
        ),
        tool_result_state_service=(
            result_state_service
        ),
        evidence_evaluation_service=(
            evidence_service
        ),
    )
    registry = build_runtime_node_registry(
        runtime=runtime,
        db=db,
    )
    contract_registry = (
        build_contract_node_registry()
    )

    check(
        set(registry)
        == AGENT_LANGGRAPH_NODES,
        "Runtime registry keys changed",
    )
    check(
        len(registry) == 13,
        "Runtime registry count must be 13",
    )
    check(
        {
            name
            for name in registry
            if registry[name]
            .__name__
            .endswith("_runtime_node")
        }
        == TARGET_NODES,
        "Exactly five runtime nodes are required",
    )
    check(
        all(
            registry[name].__name__
            == contract_registry[name].__name__
            for name in (
                set(registry)
                - TARGET_NODES
            )
        ),
        "Non-target contract nodes changed",
    )

    build_agent_state_graph(
        node_registry=registry
    )

    load_state = state_for(
        node_name=LOAD_ISSUE_NODE,
        transition_count=0,
    )
    load_update = registry[
        LOAD_ISSUE_NODE
    ](load_state)
    check(
        set(load_update)
        == {
            "current_node",
            "transition_count",
            "visited_nodes",
            "issue_context",
        },
        "load_issue update keys changed",
    )
    check(
        issue_service.calls
        == [(db, 17)],
        "load_issue service call mismatch",
    )
    check(
        load_update[
            "issue_context"
        ]["issue_id"]
        == 17,
        "Issue Context serialization mismatch",
    )
    check(
        merge_agent_graph_state(
            load_state,
            load_update,
        )["transition_count"]
        == 1,
        "load_issue merged state invalid",
    )

    route_state = state_for(
        node_name=ROUTE_INVESTIGATION_NODE,
        transition_count=3,
        update={
            "triage_confirmed": True,
            "tool_results": [
                {"tool_name": "one"},
                {"tool_name": "two"},
            ],
        },
    )
    route_update = registry[
        ROUTE_INVESTIGATION_NODE
    ](route_state)
    check(
        set(route_update)
        == {
            "current_node",
            "transition_count",
            "visited_nodes",
            "max_steps",
            "max_tool_calls",
        },
        "route_investigation update keys changed",
    )
    check(
        route_service.calls[0][1:]
        == (4, 2),
        "Routing counters changed",
    )
    check(
        merge_agent_graph_state(
            route_state,
            route_update,
        )["max_tool_calls"]
        == 3,
        "Routing merged state invalid",
    )

    select_state = state_for(
        node_name=SELECT_TOOL_NODE,
        transition_count=4,
        update={
            "triage_confirmed": True,
            "triage_result": {
                "issue_type": "API",
                "severity": "high",
            },
        },
    )
    select_update = registry[
        SELECT_TOOL_NODE
    ](select_state)
    check(
        set(select_update)
        == {
            "current_node",
            "transition_count",
            "visited_nodes",
            "selected_tool",
        },
        "select_tool update keys changed",
    )
    check(
        len(selection_service.calls)
        == 1,
        "Tool Selection call count mismatch",
    )
    check(
        select_update[
            "selected_tool"
        ]["tool_name"]
        == "search_knowledge",
        "Selected Tool state mismatch",
    )
    check(
        merge_agent_graph_state(
            select_state,
            select_update,
        )["transition_count"]
        == 5,
        "Tool Selection merged state invalid",
    )

    execute_state = state_for(
        node_name=EXECUTE_TOOL_NODE,
        transition_count=5,
        update={
            "triage_confirmed": True,
            "selected_tool": dict(
                select_update["selected_tool"]
            ),
            "max_tool_calls": 3,
            "tool_results": [],
            "retrieved_evidence": [],
        },
    )
    execute_state_before = dict(execute_state)
    execute_update = registry[
        EXECUTE_TOOL_NODE
    ](execute_state)
    check(
        set(execute_update)
        == {
            "current_node",
            "transition_count",
            "visited_nodes",
            "selected_tool",
            "tool_results",
            "retrieved_evidence",
        },
        "execute_tool update keys changed",
    )
    check(
        execution_service.calls
        == [
            (
                db,
                {
                    "run_id": "run-execute_tool",
                    "tool_name": "search_knowledge",
                    "arguments": {
                        "issue_id": 17,
                    },
                    "max_tool_calls": 3,
                },
            )
        ],
        "Replay execution call mismatch",
    )
    check(
        len(result_state_service.calls) == 1,
        "Replay result-state call count mismatch",
    )
    check(
        result_state_service.calls[0][1]
        is execution_service.outcome,
        "Replay execution outcome changed",
    )
    check(
        execute_update["selected_tool"] is None,
        "execute_tool did not clear selected_tool",
    )
    check(
        len(execute_update["tool_results"]) == 1,
        "execute_tool result mapping mismatch",
    )
    check(
        execute_update["transition_count"] == 6,
        "execute_tool transition count mismatch",
    )
    check(
        execute_update["visited_nodes"][-1]
        == EXECUTE_TOOL_NODE,
        "execute_tool visit history mismatch",
    )
    check(
        execute_state == execute_state_before,
        "execute_tool mutated original state",
    )
    check(
        merge_agent_graph_state(
            execute_state,
            execute_update,
        )["transition_count"]
        == 6,
        "execute_tool merged state invalid",
    )

    evidence_state = state_for(
        node_name=EVALUATE_EVIDENCE_NODE,
        transition_count=6,
        update={
            "triage_confirmed": True,
            "selected_tool": None,
            "max_tool_calls": 3,
            "tool_results": [
                {
                    "tool_name": (
                        "search_knowledge"
                    ),
                },
            ],
            "retrieved_evidence": [],
        },
    )
    evidence_update = registry[
        EVALUATE_EVIDENCE_NODE
    ](evidence_state)
    check(
        set(evidence_update)
        == {
            "current_node",
            "transition_count",
            "visited_nodes",
            "evidence_sufficient",
            "evidence_reason",
        },
        "evaluate_evidence update keys changed",
    )
    check(
        len(evidence_service.calls)
        == 1,
        "Evidence service call count mismatch",
    )
    check(
        evidence_update[
            "evidence_sufficient"
        ]
        is True,
        "Evidence state update mismatch",
    )
    check(
        merge_agent_graph_state(
            evidence_state,
            evidence_update,
        )["transition_count"]
        == 7,
        "Evidence merged state invalid",
    )

    _, unsafe_registry = make_runtime(
        db=db,
        issue_service=(
            FakeIssueContextService(
                unsafe=True
            )
        ),
    )
    expect_raises(
        AgentGraphStateContractError,
        lambda: unsafe_registry[
            LOAD_ISSUE_NODE
        ](load_state),
        message=(
            "Non-JSON Issue Context must fail"
        ),
    )

    error = RuntimeError(
        "selection boom"
    )
    _, raising_registry = make_runtime(
        db=db,
        selection_service=(
            FakeToolSelectionService(
                error=error
            )
        ),
    )
    raised = expect_raises(
        RuntimeError,
        lambda: raising_registry[
            SELECT_TOOL_NODE
        ](select_state),
        message=(
            "Business exceptions must propagate"
        ),
    )
    check(
        raised is error,
        "Original business exception changed",
    )

    runtime_text = RUNTIME_PATH.read_text(
        encoding="utf-8"
    )
    nodes_text = NODES_PATH.read_text(
        encoding="utf-8"
    )
    combined_text = (
        runtime_text + "\n" + nodes_text
    )
    check(
        "AgentRunnerService"
        not in combined_text,
        "Runtime adapters must not import Runner",
    )
    check(
        "checkpointer"
        not in combined_text.lower(),
        "Runtime adapters must not call checkpointer",
    )
    forbidden_calls = {
        "commit",
        "rollback",
        "flush",
        "begin",
        "begin_nested",
        "with_for_update",
    }
    actual_calls = (
        source_call_terminals(
            RUNTIME_PATH
        )
        | source_call_terminals(
            NODES_PATH
        )
    )
    check(
        forbidden_calls.isdisjoint(
            actual_calls
        ),
        "Runtime adapters contain transaction calls",
    )

    print("=== COPY THIS SUMMARY ===")
    print("stage=completed")
    print(
        "operation=validate_agent_langgraph_"
        "read_only_adapters"
    )
    print("runtime_service_count=6")
    print("runtime_registry_node_count=13")
    print("runtime_adapter_node_count=5")
    print("builder_injection=passed")
    print("load_issue_adapter=passed")
    print("route_investigation_adapter=passed")
    print("select_tool_adapter=passed")
    print("execute_tool_adapter=passed")
    print("evaluate_evidence_adapter=passed")
    print("json_safety=passed")
    print("exception_propagation=passed")
    print("runner_dependency=no")
    print("transaction_calls=0")
    print("checkpointer_calls=0")
    print("state_holds_runtime=no")
    print("runtime_holds_session=no")
    print(
        f"assertion_count={ASSERTION_COUNT}"
    )
    print("database_accessed=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
