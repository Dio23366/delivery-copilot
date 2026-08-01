from __future__ import annotations

import ast
from dataclasses import fields
import hashlib
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agent_graph.builder import (  # noqa: E402
    build_agent_state_graph,
)
from app.agent_graph.nodes import (  # noqa: E402
    build_execute_tool_runtime_node,
)
from app.agent_graph.runtime import (  # noqa: E402
    AgentGraphRuntime,
    build_agent_graph_runtime,
    build_runtime_node_registry,
)
from app.agent_graph.state import (  # noqa: E402
    AGENT_LANGGRAPH_NODES,
    EXECUTE_TOOL_NODE,
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
    AGENT_TOOL_SELECTION_VERSION,
    AgentToolSelectionService,
)


NODES_PATH = BACKEND_DIR / "app" / "agent_graph" / "nodes.py"
RUNTIME_PATH = BACKEND_DIR / "app" / "agent_graph" / "runtime.py"
READ_ONLY_VALIDATOR_PATH = (
    BACKEND_DIR
    / "scripts"
    / "validate_agent_langgraph_read_only_adapters.py"
)
PREREQUISITE_VALIDATOR_PATH = (
    BACKEND_DIR
    / "scripts"
    / "validate_agent_execute_tool_adapter_"
    "prerequisites_stub.py"
)
REPLAY_VALIDATOR_PATH = (
    BACKEND_DIR
    / "scripts"
    / "validate_agent_replay_aware_tool_"
    "execution_service_stub.py"
)
INIT_PATH = BACKEND_DIR / "app" / "agent_graph" / "__init__.py"
BUILDER_PATH = BACKEND_DIR / "app" / "agent_graph" / "builder.py"
STATE_PATH = BACKEND_DIR / "app" / "agent_graph" / "state.py"
RUNNER_PATH = (
    BACKEND_DIR
    / "app"
    / "services"
    / "agent_runner_service.py"
)
REPLAY_SERVICE_PATH = (
    BACKEND_DIR
    / "app"
    / "services"
    / "agent_replay_aware_tool_execution_service.py"
)
RESULT_STATE_SERVICE_PATH = (
    BACKEND_DIR
    / "app"
    / "services"
    / "agent_tool_result_state_service.py"
)

EXPECTED_HASHES = {
    NODES_PATH: "7c19866f93b1c9ad8ce9aec91abec84d9b537754453cfd145c602a5c4732889a",
    RUNTIME_PATH: "a8ff3e91790a0bff9dbcf1c1c4b210a414970a5783955a16e543de678ec864f0",
    READ_ONLY_VALIDATOR_PATH: "85d9c4ddb1939396793571928d5f27dfc7b476d91ccfe7e26eff170222bede7b",
    PREREQUISITE_VALIDATOR_PATH: "cb53464771b9a66d24050f2f598cc3abb152a9badf0be91a4adb8ecbfbeeda41",
    REPLAY_VALIDATOR_PATH: "ecdd4f17f63283a72496269c0a14de5cabf70652ede3acc73017c95d905a1d37",
    INIT_PATH: "4121837ac0c5a8ad0f2ea41647b61974d0e0f32196fef037a026b0e2ede7551f",
    BUILDER_PATH: "f6ab00a91bc28f712360a387d9db9635cc07098a9e2bf189e2241a27b77a843b",
    STATE_PATH: "cf13e5f7b435e6c2f1d2c6b3c05795a648d7396290ab36635a820cdb60e38e95",
    RUNNER_PATH: "fa853ab1bb2d8527d345515144e3c8102b115efdcf2281f9b913f76ac6bb8730",
    REPLAY_SERVICE_PATH: "f631c10235ccd4ef7f2155d771eae6c7d930e2a617f0d71e957b29da2dee282f",
    RESULT_STATE_SERVICE_PATH: "03b0fa20755df08bb666694b25c07f61c85d13388ad2b5dabe7db48704b7f357",
}

ASSERTION_COUNT = 0
TEST_COUNT = 0


def check(condition: bool, message: str) -> None:
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


def test(callback) -> None:
    global TEST_COUNT
    callback()
    TEST_COUNT += 1


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_sha256(path: Path) -> str:
    normalized = (
        path.read_bytes()
        .replace(b"\r\n", b"\n")
        .replace(b"\r", b"\n")
    )
    return hashlib.sha256(normalized).hexdigest()


def selected_tool() -> dict[str, object]:
    return {
        "selection_version": AGENT_TOOL_SELECTION_VERSION,
        "tool_name": "search_knowledge",
        "tool_version": "grounded_retrieval_v1",
        "arguments": {"issue_id": 17},
        "call_identity": "search_knowledge:" + ("a" * 64),
        "confidence": 0.9,
        "reason": "Grounded evidence is required.",
    }


def state_for_execute(
    *,
    selected: object = None,
    max_tool_calls: object = 3,
    transition_count: int = 5,
    tool_results: list[dict[str, object]] | None = None,
    retrieved_evidence: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    state = build_initial_agent_graph_state(
        run_id="run-execute-tool",
        issue_id=17,
    )
    return merge_agent_graph_state(
        state,
        {
            "current_node": EXECUTE_TOOL_NODE,
            "transition_count": transition_count,
            "triage_confirmed": True,
            "selected_tool": (
                selected_tool()
                if selected is None
                else selected
            ),
            "max_tool_calls": max_tool_calls,
            "tool_results": list(tool_results or []),
            "retrieved_evidence": list(
                retrieved_evidence or []
            ),
        },
    )


class FakeStateUpdate:
    def __init__(self, update: object) -> None:
        self.update = update

    def to_state_update(self):
        return self.update


class FakeExecutionService:
    def __init__(
        self,
        *,
        events: list[str] | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.events = events
        self.error = error
        self.calls: list[tuple[object, dict[str, object]]] = []
        self.outcome = object()

    def execute_current_step(
        self,
        db: object,
        **kwargs: object,
    ) -> object:
        if self.events is not None:
            self.events.append("execute_current_step")
        self.calls.append((db, dict(kwargs)))

        if self.error is not None:
            raise self.error

        return self.outcome


class FakeResultStateService:
    def __init__(
        self,
        *,
        events: list[str] | None = None,
        error: BaseException | None = None,
        update: object = None,
    ) -> None:
        self.events = events
        self.error = error
        self.update = update
        self.calls: list[tuple[dict[str, object], object]] = []

    def apply_replay(
        self,
        state,
        execution_outcome: object,
    ) -> FakeStateUpdate:
        if self.events is not None:
            self.events.append("apply_replay")
        self.calls.append((dict(state), execution_outcome))

        if self.error is not None:
            raise self.error

        if self.update is not None:
            return FakeStateUpdate(self.update)

        selected = dict(state["selected_tool"])
        tool_result = {
            "tool_name": selected["tool_name"],
            "tool_version": selected["tool_version"],
            "call_identity": selected["call_identity"],
            "arguments": dict(selected["arguments"]),
            "result_json": {
                "retrieval_status": "no_results",
            },
            "execution_status": "completed",
        }
        return FakeStateUpdate(
            {
                "selected_tool": None,
                "tool_results": [
                    *state.get("tool_results", []),
                    tool_result,
                ],
                "retrieved_evidence": list(
                    state.get("retrieved_evidence", [])
                ),
            }
        )


class PassiveService:
    pass


def runtime_with(
    *,
    execution_service: object,
    result_state_service: object,
) -> AgentGraphRuntime:
    return AgentGraphRuntime(
        issue_context_service=PassiveService(),
        investigation_routing_service=PassiveService(),
        tool_selection_service=PassiveService(),
        replay_aware_tool_execution_service=(
            execution_service
        ),
        tool_result_state_service=result_state_service,
        evidence_evaluation_service=PassiveService(),
    )


def execute_node_with(
    *,
    execution_service: FakeExecutionService | None = None,
    result_state_service: FakeResultStateService | None = None,
):
    db = object()
    execution = execution_service or FakeExecutionService()
    result_state = (
        result_state_service or FakeResultStateService()
    )
    node = build_execute_tool_runtime_node(
        db=db,
        execution_service=execution,
        result_state_service=result_state,
    )
    return db, execution, result_state, node


def terminal_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def execute_node_call_order() -> list[str]:
    tree = ast.parse(
        NODES_PATH.read_text(encoding="utf-8"),
        filename=str(NODES_PATH),
    )

    builder = next(
        node
        for node in tree.body
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "build_execute_tool_runtime_node"
        )
    )
    nested = next(
        node
        for node in builder.body
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "node"
        )
    )
    calls = sorted(
        (
            node
            for node in ast.walk(nested)
            if isinstance(node, ast.Call)
        ),
        key=lambda item: (item.lineno, item.col_offset),
    )
    return [
        name
        for call in calls
        if (name := terminal_name(call)) is not None
    ]


def source_call_terminals(path: Path) -> set[str]:
    tree = ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )
    return {
        name
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        if (name := terminal_name(node)) is not None
    }


def test_source_and_scope_contract() -> None:
    normalized_paths = {
        INIT_PATH,
        STATE_PATH,
    }

    for path, expected in EXPECTED_HASHES.items():
        actual_hash = (
            normalized_sha256(path)
            if path in normalized_paths
            else sha256(path)
        )
        check(
            actual_hash == expected,
            f"SHA256 mismatch: {path.name}",
        )

    call_order = execute_node_call_order()
    required_order = [
        "validate_agent_graph_state",
        "_selected_tool_execution_inputs",
        "execute_current_step",
        "apply_replay",
        "_execute_tool_state_update",
        "_advance",
    ]
    positions = [call_order.index(name) for name in required_order]
    check(
        positions == sorted(positions),
        "execute_tool node call order changed",
    )
    check(
        call_order.count("execute_current_step") == 1,
        "execute_current_step call count changed",
    )
    check(
        call_order.count("apply_replay") == 1,
        "apply_replay call count changed",
    )
    check(
        call_order.count("_advance") == 1,
        "execute_tool advance count changed",
    )

    combined_text = (
        NODES_PATH.read_text(encoding="utf-8")
        + "\n"
        + RUNTIME_PATH.read_text(encoding="utf-8")
    )
    check(
        "AgentRunnerService" not in combined_text,
        "Runtime Adapter must not depend on Runner",
    )
    check(
        "checkpointer" not in combined_text.lower(),
        "Runtime Adapter must not use Checkpointer",
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
        source_call_terminals(NODES_PATH)
        | source_call_terminals(RUNTIME_PATH)
    )
    check(
        forbidden_calls.isdisjoint(actual_calls),
        "Runtime Adapter contains transaction calls",
    )

    prerequisite_text = PREREQUISITE_VALIDATOR_PATH.read_text(
        encoding="utf-8-sig"
    )
    replay_text = REPLAY_VALIDATOR_PATH.read_text(
        encoding="utf-8-sig"
    )
    check(
        'print("graph_execute_tool_wired=yes")'
        in prerequisite_text,
        "Prerequisite Validator wiring summary is stale",
    )
    check(
        'print("runtime_modified=yes")'
        in prerequisite_text,
        "Prerequisite Runtime summary is stale",
    )
    check(
        'print("nodes_modified=yes")'
        in prerequisite_text,
        "Prerequisite Nodes summary is stale",
    )
    check(
        'print("graph_execute_tool_wired=yes")'
        in replay_text,
        "Replay Validator wiring summary is stale",
    )
    check(
        "Graph execute_tool wiring occurred early"
        not in replay_text,
        "Replay Validator still blocks Runtime wiring",
    )


def test_runtime_contract() -> None:
    check(
        tuple(field.name for field in fields(AgentGraphRuntime))
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
            for field in fields(AgentGraphRuntime)
            for token in ("db", "session", "checkpointer")
        ),
        "Runtime must not hold invocation dependencies",
    )

    default_runtime = build_agent_graph_runtime()
    check(
        isinstance(
            default_runtime.issue_context_service,
            AgentIssueContextService,
        ),
        "Default Issue Context service mismatch",
    )
    check(
        isinstance(
            default_runtime.investigation_routing_service,
            AgentInvestigationRoutingService,
        ),
        "Default Routing service mismatch",
    )
    check(
        isinstance(
            default_runtime.tool_selection_service,
            AgentToolSelectionService,
        ),
        "Default Selection service mismatch",
    )
    check(
        isinstance(
            default_runtime.replay_aware_tool_execution_service,
            AgentReplayAwareToolExecutionService,
        ),
        "Default Replay Execution service mismatch",
    )
    check(
        isinstance(
            default_runtime.tool_result_state_service,
            AgentToolResultStateService,
        ),
        "Default Result State service mismatch",
    )
    check(
        isinstance(
            default_runtime.evidence_evaluation_service,
            AgentEvidenceEvaluationService,
        ),
        "Default Evidence service mismatch",
    )

    execution = FakeExecutionService()
    result_state = FakeResultStateService()
    registry = build_runtime_node_registry(
        runtime=runtime_with(
            execution_service=execution,
            result_state_service=result_state,
        ),
        db=object(),
    )
    check(
        set(registry) == AGENT_LANGGRAPH_NODES,
        "Runtime registry keys changed",
    )
    check(
        len(registry) == 13,
        "Runtime registry count changed",
    )
    runtime_nodes = {
        name
        for name, node in registry.items()
        if node.__name__.endswith("_runtime_node")
    }
    check(
        len(runtime_nodes) == 5,
        "Runtime Adapter count must be 5",
    )
    check(
        EXECUTE_TOOL_NODE in runtime_nodes,
        "execute_tool Runtime Adapter missing",
    )
    check(
        registry[EXECUTE_TOOL_NODE].__name__
        == "execute_tool_runtime_node",
        "execute_tool Runtime node name changed",
    )
    build_agent_state_graph(node_registry=registry)
    expect_raises(
        TypeError,
        lambda: build_runtime_node_registry(
            runtime=runtime_with(
                execution_service=execution,
                result_state_service=result_state,
            ),
            db=None,
        ),
        message="None DB must fail",
    )


def test_success_path() -> None:
    events: list[str] = []
    execution = FakeExecutionService(events=events)
    result_state = FakeResultStateService(events=events)
    db, execution, result_state, node = execute_node_with(
        execution_service=execution,
        result_state_service=result_state,
    )
    state = state_for_execute()
    before = dict(state)
    update = node(state)

    check(
        events == ["execute_current_step", "apply_replay"],
        "Service call order changed",
    )
    check(
        execution.calls
        == [
            (
                db,
                {
                    "run_id": "run-execute-tool",
                    "tool_name": "search_knowledge",
                    "arguments": {"issue_id": 17},
                    "max_tool_calls": 3,
                },
            )
        ],
        "execute_current_step arguments changed",
    )
    check(
        len(result_state.calls) == 1,
        "apply_replay call count changed",
    )
    check(
        result_state.calls[0][0] == state,
        "apply_replay did not receive validated state",
    )
    check(
        result_state.calls[0][1] is execution.outcome,
        "Execution outcome identity changed",
    )
    check(
        set(update)
        == {
            "current_node",
            "transition_count",
            "visited_nodes",
            "selected_tool",
            "tool_results",
            "retrieved_evidence",
        },
        "Partial State update fields changed",
    )
    check(
        update["selected_tool"] is None,
        "selected_tool was not cleared",
    )
    check(
        update["transition_count"] == 6,
        "transition_count did not increment once",
    )
    check(
        update["visited_nodes"] == [EXECUTE_TOOL_NODE],
        "visited_nodes did not append once",
    )
    check(
        len(update["tool_results"]) == 1,
        "Tool result was not mapped",
    )
    check(state == before, "Original State was mutated")
    merged = merge_agent_graph_state(state, update)
    check(
        merged["current_node"] == EXECUTE_TOOL_NODE,
        "Merged current_node changed",
    )
    check(
        merged["transition_count"] == 6,
        "Merged transition_count changed",
    )


def test_selected_tool_guards() -> None:
    base = selected_tool()
    cases: list[tuple[str, object, object]] = [
        ("missing", None, 3),
        ("fields", {**base, "extra": True}, 3),
        (
            "selection_version",
            {**base, "selection_version": "wrong"},
            3,
        ),
        ("tool_name", {**base, "tool_name": " bad"}, 3),
        ("tool_version", {**base, "tool_version": ""}, 3),
        (
            "call_identity",
            {**base, "call_identity": "search_knowledge:short"},
            3,
        ),
        ("arguments", {**base, "arguments": []}, 3),
        ("confidence", {**base, "confidence": True}, 3),
        ("reason", {**base, "reason": " bad"}, 3),
        ("max_tool_calls", base, 0),
    ]

    for name, selected, max_calls in cases:
        execution = FakeExecutionService()
        result_state = FakeResultStateService()
        _, execution, result_state, node = execute_node_with(
            execution_service=execution,
            result_state_service=result_state,
        )

        if name == "missing":
            state = state_for_execute()
            state["selected_tool"] = None
        else:
            try:
                state = state_for_execute(
                    selected=selected,
                    max_tool_calls=max_calls,
                )
            except AgentGraphStateContractError:
                state = build_initial_agent_graph_state(
                    run_id="run-execute-tool",
                    issue_id=17,
                )
                state.update(
                    {
                        "current_node": EXECUTE_TOOL_NODE,
                        "transition_count": 5,
                        "selected_tool": selected,
                        "max_tool_calls": max_calls,
                        "tool_results": [],
                        "retrieved_evidence": [],
                    }
                )

        expect_raises(
            AgentGraphStateContractError,
            lambda state=state, node=node: node(state),
            message=f"Guard did not fail: {name}",
        )
        check(
            execution.calls == [],
            f"Execution occurred before guard: {name}",
        )
        check(
            result_state.calls == [],
            f"Result mapping occurred before guard: {name}",
        )


def test_exception_propagation() -> None:
    execution_error = RuntimeError("execution boom")
    execution = FakeExecutionService(error=execution_error)
    result_state = FakeResultStateService()
    _, execution, result_state, node = execute_node_with(
        execution_service=execution,
        result_state_service=result_state,
    )
    raised = expect_raises(
        RuntimeError,
        lambda: node(state_for_execute()),
        message="Execution exception must propagate",
    )
    check(raised is execution_error, "Execution exception changed")
    check(
        result_state.calls == [],
        "Result mapping ran after execution failure",
    )

    result_error = RuntimeError("result boom")
    execution = FakeExecutionService()
    result_state = FakeResultStateService(error=result_error)
    _, execution, result_state, node = execute_node_with(
        execution_service=execution,
        result_state_service=result_state,
    )
    raised = expect_raises(
        RuntimeError,
        lambda: node(state_for_execute()),
        message="Result exception must propagate",
    )
    check(raised is result_error, "Result exception changed")
    check(
        len(execution.calls) == 1,
        "Execution call count changed before result failure",
    )


def test_result_update_guards() -> None:
    invalid_updates: list[tuple[str, object]] = [
        (
            "extra_field",
            {
                "selected_tool": None,
                "tool_results": [],
                "retrieved_evidence": [],
                "error_code": None,
            },
        ),
        (
            "selected_not_cleared",
            {
                "selected_tool": selected_tool(),
                "tool_results": [],
                "retrieved_evidence": [],
            },
        ),
        (
            "invalid_tool_results",
            {
                "selected_tool": None,
                "tool_results": {},
                "retrieved_evidence": [],
            },
        ),
        ("not_mapping", []),
    ]

    for name, update in invalid_updates:
        result_state = FakeResultStateService(update=update)
        _, execution, result_state, node = execute_node_with(
            result_state_service=result_state,
        )
        expect_raises(
            (AgentGraphStateContractError, TypeError),
            lambda node=node: node(state_for_execute()),
            message=f"Invalid result update passed: {name}",
        )
        check(
            len(execution.calls) == 1,
            f"Execution call count changed: {name}",
        )
        check(
            len(result_state.calls) == 1,
            f"Result call count changed: {name}",
        )


def test_replay_no_op_mapping() -> None:
    prior_result = {
        "tool_name": "search_knowledge",
        "tool_version": "grounded_retrieval_v1",
        "call_identity": "search_knowledge:" + ("a" * 64),
        "arguments": {"issue_id": 17},
        "result_json": {"retrieval_status": "no_results"},
        "execution_status": "completed",
    }
    prior_evidence: list[dict[str, object]] = []
    state = state_for_execute(
        tool_results=[prior_result],
        retrieved_evidence=prior_evidence,
    )
    result_state = FakeResultStateService(
        update={
            "selected_tool": None,
            "tool_results": [prior_result],
            "retrieved_evidence": prior_evidence,
        }
    )
    _, execution, result_state, node = execute_node_with(
        result_state_service=result_state,
    )
    update = node(state)
    check(
        update["tool_results"] == [prior_result],
        "Replay exact Tool result changed",
    )
    check(
        update["retrieved_evidence"] == prior_evidence,
        "Replay exact evidence changed",
    )
    check(
        update["transition_count"] == 6,
        "Replay transition count changed",
    )
    check(
        len(execution.calls) == 1,
        "Replay execution service call count changed",
    )


def main() -> int:
    test(test_source_and_scope_contract)
    test(test_runtime_contract)
    test(test_success_path)
    test(test_selected_tool_guards)
    test(test_exception_propagation)
    test(test_result_update_guards)
    test(test_replay_no_op_mapping)

    print("=== COPY THIS SUMMARY ===")
    print("stage=completed")
    print(
        "operation=validate_agent_langgraph_"
        "execute_tool_adapter"
    )
    print("runtime_service_count=6")
    print("runtime_registry_node_count=13")
    print("runtime_adapter_node_count=5")
    print("execute_tool_adapter=passed")
    print("selected_tool_guard_count=10")
    print("selected_tool_pre_dispatch_validation=passed")
    print("execute_current_step_call=passed")
    print("apply_replay_call=passed")
    print("result_update_validation=passed")
    print("selected_tool_cleared=passed")
    print("transition_count_incremented_once=passed")
    print("visited_nodes_appended_once=passed")
    print("original_state_mutation=no")
    print("replay_exact_no_op_mapping=passed")
    print("exception_propagation=passed")
    print("runner_dependency=no")
    print("transaction_calls=0")
    print("checkpointer_calls=0")
    print("runtime_holds_session=no")
    print("aligned_regression_validator_count=3")
    print("database_accessed=no")
    print(f"assertion_count={ASSERTION_COUNT}")
    print(f"test_count={TEST_COUNT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
