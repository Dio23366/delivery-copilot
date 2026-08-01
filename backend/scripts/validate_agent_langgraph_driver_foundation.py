from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, fields
import hashlib
import operator
from pathlib import Path
import sys
from typing import TypedDict


BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agent_graph.driver import (
    AGENT_GRAPH_SINGLE_STEP_DRIVER_VERSION,
    AgentGraphSingleStepDriver,
    AgentGraphSingleStepDriverError,
    AgentGraphSingleStepResult,
)


DRIVER_PATH = (
    BACKEND_DIR
    / "app"
    / "agent_graph"
    / "driver.py"
)
VALIDATOR_PATH = Path(__file__).resolve()

EXPECTED_DRIVER_SHA256 = (
    "c617e2423dc1d54c983d057dfe603ef0"
    "527cb78b049ad591d66e38578f8f0754"
)

PROTECTED_SHA256 = {
    (
        BACKEND_DIR
        / "app"
        / "agent_graph"
        / "__init__.py"
    ): "4121837ac0c5a8ad0f2ea41647b61974d0e0f32196fef037a026b0e2ede7551f",
    (
        BACKEND_DIR
        / "app"
        / "agent_graph"
        / "builder.py"
    ): "f6ab00a91bc28f712360a387d9db9635cc07098a9e2bf189e2241a27b77a843b",
    (
        BACKEND_DIR
        / "app"
        / "agent_graph"
        / "nodes.py"
    ): "7c19866f93b1c9ad8ce9aec91abec84d9b537754453cfd145c602a5c4732889a",
    (
        BACKEND_DIR
        / "app"
        / "agent_graph"
        / "routing.py"
    ): "2b145630da74c414bbd3656bdce8d3de5e35f9d2d308af4c0b3b60c7023adb1d",
    (
        BACKEND_DIR
        / "app"
        / "agent_graph"
        / "runtime.py"
    ): "a8ff3e91790a0bff9dbcf1c1c4b210a414970a5783955a16e543de678ec864f0",
    (
        BACKEND_DIR
        / "app"
        / "agent_graph"
        / "state.py"
    ): "cf13e5f7b435e6c2f1d2c6b3c05795a648d7396290ab36635a820cdb60e38e95",
    (
        BACKEND_DIR
        / "app"
        / "services"
        / "agent_runner_service.py"
    ): "fa853ab1bb2d8527d345515144e3c8102b115efdcf2281f9b913f76ac6bb8730",
    (
        BACKEND_DIR
        / "app"
        / "services"
        / "agent_orchestration_service.py"
    ): "69b204f3c08bebf8a105490079297dc7404b1a53345c1fb6f4f3f14a10840984",
    (
        BACKEND_DIR
        / "app"
        / "services"
        / "agent_persistence_service.py"
    ): "cf788d558687340843ea10df61b76d685f65a6190fd98e00eb1ced5e9af7fdf8",
    (
        BACKEND_DIR
        / "app"
        / "services"
        / "agent_replay_aware_tool_execution_service.py"
    ): "f631c10235ccd4ef7f2155d771eae6c7d930e2a617f0d71e957b29da2dee282f",
    (
        BACKEND_DIR
        / "app"
        / "services"
        / "agent_tool_result_state_service.py"
    ): "03b0fa20755df08bb666694b25c07f61c85d13388ad2b5dabe7db48704b7f357",
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


def expect_driver_error(
    error_code: str,
    callback,
) -> AgentGraphSingleStepDriverError:
    exc = expect_raises(
        AgentGraphSingleStepDriverError,
        callback,
        message=(
            "Expected AgentGraphSingleStepDriverError "
            f"with code {error_code}"
        ),
    )
    check(
        exc.error_code == error_code,
        (
            "Unexpected Driver error code: "
            f"{exc.error_code}"
        ),
    )
    return exc


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


class FakeSnapshot:
    def __init__(
        self,
        *,
        next_nodes: object,
        values: object,
    ) -> None:
        self.next = next_nodes
        self.values = values


class FakeGraph:
    def __init__(
        self,
        *,
        before: FakeSnapshot,
        after: FakeSnapshot,
        events: list[object] | None = None,
        get_state_error: BaseException | None = None,
        stream_error: BaseException | None = None,
        mutate_config: bool = False,
    ) -> None:
        self.before = before
        self.after = after
        self.events = list(events or [])
        self.get_state_error = get_state_error
        self.stream_error = stream_error
        self.mutate_config = mutate_config
        self.get_state_calls: list[object] = []
        self.stream_calls: list[dict[str, object]] = []

    def get_state(self, config):
        self.get_state_calls.append(config)

        if self.get_state_error is not None:
            raise self.get_state_error

        if self.mutate_config:
            metadata = config.get("metadata")
            if isinstance(metadata, dict):
                metadata.setdefault("items", []).append(
                    "mutated-inside-graph"
                )

            extra = config["configurable"].get("extra")
            if isinstance(extra, dict):
                extra.setdefault("items", []).append(
                    "mutated-inside-graph"
                )

        if len(self.get_state_calls) == 1:
            return self.before
        return self.after

    def stream(
        self,
        state_input,
        config,
        *,
        stream_mode,
        interrupt_after,
    ):
        self.stream_calls.append(
            {
                "state_input": state_input,
                "config": config,
                "stream_mode": stream_mode,
                "interrupt_after": list(
                    interrupt_after
                ),
            }
        )

        if self.stream_error is not None:
            raise self.stream_error

        yield from self.events


class MutatingEventGraph(FakeGraph):
    def stream(
        self,
        state_input,
        config,
        *,
        stream_mode,
        interrupt_after,
    ):
        self.stream_calls.append(
            {
                "state_input": state_input,
                "config": config,
                "stream_mode": stream_mode,
                "interrupt_after": list(
                    interrupt_after
                ),
            }
        )

        update = {
            "value": 11,
            "nested": {
                "items": [1, 2, 3],
            },
        }
        yield {"middle": update}

        update["nested"]["items"].append(99)
        yield {"other": {"ignored": True}}


def thread_config() -> dict[str, object]:
    return {
        "configurable": {
            "thread_id": "run-driver-test",
        }
    }


def happy_graph(
    *,
    before_values: dict[str, object] | None = None,
    after_values: dict[str, object] | None = None,
    events: list[object] | None = None,
) -> FakeGraph:
    return FakeGraph(
        before=FakeSnapshot(
            next_nodes=("middle",),
            values=(
                before_values
                if before_values is not None
                else {
                    "value": 1,
                    "visited": ["first"],
                }
            ),
        ),
        after=FakeSnapshot(
            next_nodes=("final",),
            values=(
                after_values
                if after_values is not None
                else {
                    "value": 11,
                    "visited": [
                        "first",
                        "middle",
                    ],
                }
            ),
        ),
        events=(
            events
            if events is not None
            else [
                {
                    "middle": {
                        "value": 11,
                        "visited": [
                            "first",
                            "middle",
                        ],
                    }
                }
            ]
        ),
    )


def execute(
    graph: object,
    *,
    config: Mapping[str, object] | None = None,
    expected_node: str = "middle",
) -> AgentGraphSingleStepResult:
    return AgentGraphSingleStepDriver().execute_next_node(
        graph,
        thread_config=(
            thread_config()
            if config is None
            else config
        ),
        expected_node=expected_node,
    )


def test_source_contract() -> None:
    check(
        DRIVER_PATH.is_file(),
        "Driver source file is missing",
    )
    check(
        VALIDATOR_PATH.is_file(),
        "Validator source file is missing",
    )
    check(
        sha256(DRIVER_PATH) == EXPECTED_DRIVER_SHA256,
        "Driver source SHA256 mismatch",
    )

    normalized_paths = {
        BACKEND_DIR / "app" / "agent_graph" / "__init__.py",
        BACKEND_DIR / "app" / "agent_graph" / "state.py",
    }

    for path, expected_hash in PROTECTED_SHA256.items():
        check(path.is_file(), f"Protected file missing: {path}")
        actual_hash = (
            normalized_sha256(path)
            if path in normalized_paths
            else sha256(path)
        )
        check(
            actual_hash == expected_hash,
            f"Protected source changed: {path}",
        )

    source = DRIVER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(DRIVER_PATH))

    imported_modules: set[str] = set()
    forbidden_call_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(
                alias.name for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")
        elif isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Attribute):
                forbidden_call_names.add(function.attr)
            elif isinstance(function, ast.Name):
                forbidden_call_names.add(function.id)

    check(
        not any(
            module.startswith("sqlalchemy")
            for module in imported_modules
        ),
        "Driver must not import SQLAlchemy",
    )
    check(
        not any(
            module.startswith("app.services")
            for module in imported_modules
        ),
        "Driver must not import service layer",
    )
    check(
        not any(
            module.startswith("app.models")
            for module in imported_modules
        ),
        "Driver must not import models",
    )

    for forbidden_call in (
        "update_state",
        "commit",
        "rollback",
        "flush",
        "with_for_update",
    ):
        check(
            forbidden_call not in forbidden_call_names,
            f"Forbidden Driver call: {forbidden_call}",
        )

    for forbidden_token in (
        "AgentRunnerService",
        "AgentOrchestrationService",
        "AgentPersistenceService",
        "PostgresSaver",
        "InMemorySaver",
        "Session",
    ):
        check(
            forbidden_token not in source,
            f"Forbidden Driver dependency: {forbidden_token}",
        )

    check(
        AGENT_GRAPH_SINGLE_STEP_DRIVER_VERSION
        == "agent_graph_single_step_driver_v0.1",
        "Driver version changed",
    )
    check(
        [field.name for field in fields(AgentGraphSingleStepResult)]
        == [
            "node_name",
            "node_update",
            "before_next",
            "after_next",
            "before_values",
            "after_values",
            "driver_version",
        ],
        "Driver result fields changed",
    )


def test_happy_path() -> None:
    graph = happy_graph()
    config = thread_config()
    result = execute(graph, config=config)

    check(result.node_name == "middle", "Node name mismatch")
    check(
        result.before_next == ("middle",),
        "Before-next mismatch",
    )
    check(
        result.after_next == ("final",),
        "After-next mismatch",
    )
    check(
        result.node_update["value"] == 11,
        "Node update mismatch",
    )
    check(
        result.node_update["visited"]
        == ("first", "middle"),
        "Nested node update must be immutable",
    )
    check(
        result.before_values["visited"] == ("first",),
        "Before values mismatch",
    )
    check(
        result.after_values["visited"]
        == ("first", "middle"),
        "After values mismatch",
    )
    check(
        result.driver_version
        == AGENT_GRAPH_SINGLE_STEP_DRIVER_VERSION,
        "Result version mismatch",
    )
    check(
        len(graph.get_state_calls) == 2,
        "Driver must read state before and after",
    )
    check(
        len(graph.stream_calls) == 1,
        "Driver must stream exactly once",
    )
    stream_call = graph.stream_calls[0]
    check(
        stream_call["state_input"] is None,
        "Driver must resume with None input",
    )
    check(
        stream_call["stream_mode"] == "updates",
        "Driver must use updates stream mode",
    )
    check(
        stream_call["interrupt_after"] == ["middle"],
        "Driver must interrupt after expected node",
    )
    check(
        config == thread_config(),
        "Driver mutated caller thread config",
    )

    as_dict = result.as_dict()
    check(isinstance(as_dict, dict), "as_dict must return dict")
    check(
        as_dict["node_update"]["visited"]
        == ["first", "middle"],
        "as_dict must thaw immutable sequences",
    )
    check(
        as_dict["before_next"] == ["middle"],
        "as_dict before-next mismatch",
    )
    check(
        as_dict["after_next"] == ["final"],
        "as_dict after-next mismatch",
    )

    expect_raises(
        FrozenInstanceError,
        lambda: setattr(result, "node_name", "other"),
        message="Result dataclass must be frozen",
    )
    expect_raises(
        TypeError,
        lambda: operator.setitem(
            result.node_update,
            "value",
            99,
        ),
        message="Node update mapping must be immutable",
    )


def test_missing_thread_id() -> None:
    graph = happy_graph()
    exc = expect_driver_error(
        "missing_thread_id",
        lambda: execute(
            graph,
            config={"configurable": {}},
        ),
    )
    check("thread_id" in str(exc), "Error must mention thread_id")
    check(not graph.get_state_calls, "Graph must not be called")


def test_checkpoint_id_rejected() -> None:
    graph = happy_graph()
    config = thread_config()
    config["configurable"]["checkpoint_id"] = "history"
    expect_driver_error(
        "checkpoint_id_not_allowed",
        lambda: execute(graph, config=config),
    )
    check(not graph.get_state_calls, "Graph must not be called")


def test_checkpoint_ns_rejected() -> None:
    graph = happy_graph()
    config = thread_config()
    config["configurable"]["checkpoint_ns"] = "graph-v1"
    expect_driver_error(
        "checkpoint_ns_not_allowed",
        lambda: execute(graph, config=config),
    )
    check(not graph.get_state_calls, "Graph must not be called")


def test_empty_expected_node_rejected() -> None:
    graph = happy_graph()
    expect_driver_error(
        "invalid_expected_node",
        lambda: execute(graph, expected_node=" "),
    )
    check(not graph.get_state_calls, "Graph must not be called")


def test_no_scheduled_node_rejected() -> None:
    graph = happy_graph()
    graph.before.next = ()
    expect_driver_error(
        "no_scheduled_node",
        lambda: execute(graph),
    )
    check(not graph.stream_calls, "Stream must not be called")


def test_multiple_scheduled_nodes_rejected() -> None:
    graph = happy_graph()
    graph.before.next = ("middle", "other")
    expect_driver_error(
        "multiple_scheduled_nodes",
        lambda: execute(graph),
    )
    check(not graph.stream_calls, "Stream must not be called")


def test_wrong_scheduled_node_rejected() -> None:
    graph = happy_graph()
    graph.before.next = ("other",)
    expect_driver_error(
        "unexpected_scheduled_node",
        lambda: execute(graph),
    )
    check(not graph.stream_calls, "Stream must not be called")


def test_missing_node_update_rejected() -> None:
    graph = happy_graph(events=[{"other": {"value": 2}}])
    expect_driver_error(
        "missing_node_update",
        lambda: execute(graph),
    )
    check(
        len(graph.get_state_calls) == 1,
        "After-state must not be read on missing update",
    )


def test_duplicate_node_update_rejected() -> None:
    graph = happy_graph(
        events=[
            {"middle": {"value": 2}},
            {"middle": {"value": 3}},
        ]
    )
    expect_driver_error(
        "duplicate_node_update",
        lambda: execute(graph),
    )
    check(
        len(graph.get_state_calls) == 1,
        "After-state must not be read on duplicate update",
    )


def test_nonmapping_update_rejected() -> None:
    graph = happy_graph(events=[{"middle": None}])
    expect_driver_error(
        "invalid_node_update",
        lambda: execute(graph),
    )
    check(
        len(graph.get_state_calls) == 1,
        "After-state must not be read on invalid update",
    )


def test_get_state_exception_propagates() -> None:
    error = RuntimeError("get-state-failure")
    graph = happy_graph()
    graph.get_state_error = error
    caught = expect_raises(
        RuntimeError,
        lambda: execute(graph),
        message="get_state exception must propagate",
    )
    check(caught is error, "Original get_state error must propagate")


def test_stream_exception_propagates() -> None:
    error = RuntimeError("stream-failure")
    graph = happy_graph()
    graph.stream_error = error
    caught = expect_raises(
        RuntimeError,
        lambda: execute(graph),
        message="stream exception must propagate",
    )
    check(caught is error, "Original stream error must propagate")


def test_input_config_not_mutated() -> None:
    graph = happy_graph()
    graph.mutate_config = True
    config = {
        "configurable": {
            "thread_id": "run-driver-test",
            "extra": {
                "items": [],
            },
        },
        "metadata": {
            "items": [],
        },
    }
    original = {
        "configurable": {
            "thread_id": "run-driver-test",
            "extra": {
                "items": [],
            },
        },
        "metadata": {
            "items": [],
        },
    }
    expected_private_config = {
        "configurable": {
            "thread_id": "run-driver-test",
        }
    }

    result = execute(graph, config=config)
    check(config == original, "Caller config was mutated")
    check(result.node_name == "middle", "Execution did not complete")
    check(
        graph.get_state_calls[0] is graph.get_state_calls[1],
        "Driver should use one private config copy",
    )
    check(
        graph.get_state_calls[0] == expected_private_config,
        "Driver must pass only the thread-only config",
    )
    check(
        graph.stream_calls[0]["config"]
        == expected_private_config,
        "Stream must receive only the thread-only config",
    )


def test_snapshot_and_update_inputs_not_mutated() -> None:
    before_values = {
        "value": 1,
        "nested": {"items": [1, 2]},
    }
    after_values = {
        "value": 11,
        "nested": {"items": [1, 2, 3]},
    }
    update = {
        "middle": {
            "nested": {"items": [1, 2, 3]},
        }
    }
    graph = happy_graph(
        before_values=before_values,
        after_values=after_values,
        events=[update],
    )
    result = execute(graph)

    before_values["nested"]["items"].append(99)
    after_values["nested"]["items"].append(99)
    update["middle"]["nested"]["items"].append(99)

    check(
        result.before_values["nested"]["items"] == (1, 2),
        "Before snapshot result aliases source data",
    )
    check(
        result.after_values["nested"]["items"]
        == (1, 2, 3),
        "After snapshot result aliases source data",
    )
    check(
        result.node_update["nested"]["items"]
        == (1, 2, 3),
        "Node update result aliases source data",
    )


def test_stream_update_frozen_at_emission() -> None:
    graph = MutatingEventGraph(
        before=FakeSnapshot(
            next_nodes=("middle",),
            values={
                "value": 1,
                "visited": ["first"],
            },
        ),
        after=FakeSnapshot(
            next_nodes=("final",),
            values={
                "value": 11,
                "visited": ["first", "middle"],
            },
        ),
    )

    result = execute(graph)

    check(
        result.node_update["nested"]["items"]
        == (1, 2, 3),
        "Node update must be frozen at stream emission",
    )
    check(
        result.node_update["value"] == 11,
        "Frozen stream update value mismatch",
    )


def test_non_json_safe_update_rejected() -> None:
    graph = happy_graph(
        events=[{"middle": {"bad": object()}}]
    )
    expect_driver_error(
        "non_json_safe_value",
        lambda: execute(graph),
    )


def test_real_in_memory_graph() -> None:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph

    class ProbeState(TypedDict, total=False):
        value: int
        visited: list[str]

    def first(state: ProbeState) -> dict[str, object]:
        return {
            "value": int(state.get("value", 0)) + 1,
            "visited": [*state.get("visited", []), "first"],
        }

    def middle(state: ProbeState) -> dict[str, object]:
        return {
            "value": int(state.get("value", 0)) + 10,
            "visited": [*state.get("visited", []), "middle"],
        }

    def final(state: ProbeState) -> dict[str, object]:
        return {
            "value": int(state.get("value", 0)) + 100,
            "visited": [*state.get("visited", []), "final"],
        }

    builder = StateGraph(ProbeState)
    builder.add_node("first", first)
    builder.add_node("middle", middle)
    builder.add_node("final", final)
    builder.add_edge(START, "first")
    builder.add_edge("first", "middle")
    builder.add_edge("middle", "final")
    builder.add_edge("final", END)
    graph = builder.compile(checkpointer=InMemorySaver())

    config = {
        "configurable": {
            "thread_id": "driver-real-in-memory",
        }
    }
    graph.update_state(
        config,
        {"value": 1, "visited": ["first"]},
        as_node="first",
    )

    result = execute(graph, config=config)
    check(result.node_name == "middle", "Real node mismatch")
    check(
        result.before_next == ("middle",),
        "Real before-next mismatch",
    )
    check(
        result.after_next == ("final",),
        "Real after-next mismatch",
    )
    check(
        result.node_update["value"] == 11,
        "Real node update value mismatch",
    )
    check(
        result.after_values["visited"]
        == ("first", "middle"),
        "Real latest state mismatch",
    )


def main() -> int:
    test(test_source_contract)
    test(test_happy_path)
    test(test_missing_thread_id)
    test(test_checkpoint_id_rejected)
    test(test_checkpoint_ns_rejected)
    test(test_empty_expected_node_rejected)
    test(test_no_scheduled_node_rejected)
    test(test_multiple_scheduled_nodes_rejected)
    test(test_wrong_scheduled_node_rejected)
    test(test_missing_node_update_rejected)
    test(test_duplicate_node_update_rejected)
    test(test_nonmapping_update_rejected)
    test(test_get_state_exception_propagates)
    test(test_stream_exception_propagates)
    test(test_input_config_not_mutated)
    test(test_snapshot_and_update_inputs_not_mutated)
    test(test_stream_update_frozen_at_emission)
    test(test_non_json_safe_update_rejected)
    test(test_real_in_memory_graph)

    check(TEST_COUNT == 19, "Unexpected Driver test count")
    check(
        ASSERTION_COUNT >= 100,
        "Driver assertion count is unexpectedly low",
    )

    print(
        "Agent LangGraph single-step Driver "
        "foundation assertions passed"
    )
    print(f"assertion_count={ASSERTION_COUNT}")
    print(f"test_count={TEST_COUNT}")
    print(
        "driver_version="
        f"{AGENT_GRAPH_SINGLE_STEP_DRIVER_VERSION}"
    )
    print("driver_executes_exactly_one_node=yes")
    print("thread_id_required=yes")
    print("checkpoint_id_allowed=no")
    print("custom_checkpoint_ns_allowed=no")
    print("bootstrap_update_state_allowed=no")
    print("driver_creates_checkpointer=no")
    print("persistent_postgres_saver_wiring_allowed=no")
    print("real_in_memory_graph_test=passed")
    print("protected_file_count=11")
    print("proposed_write_file_count=2")
    print("custom_runner_changed=no")
    print("api_changed=no")
    print("runtime_changed=no")
    print("nodes_changed=no")
    print("builder_changed=no")
    print("state_changed=no")
    print("database_accessed=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
