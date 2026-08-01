from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, dataclass
import hashlib
from pathlib import Path
import subprocess
from typing import Mapping

from app.agent_graph.coordinator import (
    AGENT_GRAPH_STEP_COORDINATOR_VERSION,
    AgentGraphCheckpointInspection,
    AgentGraphStepCoordinationResult,
    AgentGraphStepCoordinator,
    AgentGraphStepCoordinatorError,
)
from app.agent_graph.driver import (
    AgentGraphSingleStepDriver,
    AgentGraphSingleStepDriverError,
    AgentGraphSingleStepResult,
)
from app.agent_graph.state import (
    AGENT_LANGGRAPH_GRAPH_VERSION,
    AGENT_LANGGRAPH_STATE_SCHEMA_VERSION,
    LOAD_ISSUE_NODE,
    TRIAGE_ISSUE_NODE,
    build_initial_agent_graph_state,
)


EXPECTED_PROTECTED_HASHES = {
    "backend/app/agent_graph/__init__.py": (
        "4121837ac0c5a8ad0f2ea41647b61974"
        "d0e0f32196fef037a026b0e2ede7551f"
    ),
    "backend/app/agent_graph/builder.py": (
        "f6ab00a91bc28f712360a387d9db9635"
        "cc07098a9e2bf189e2241a27b77a843b"
    ),
    "backend/app/agent_graph/driver.py": (
        "c617e2423dc1d54c983d057dfe603ef0"
        "527cb78b049ad591d66e38578f8f0754"
    ),
    "backend/app/agent_graph/nodes.py": (
        "7c19866f93b1c9ad8ce9aec91abec84d"
        "9b537754453cfd145c602a5c4732889a"
    ),
    "backend/app/agent_graph/routing.py": (
        "2b145630da74c414bbd3656bdce8d3de"
        "5e35f9d2d308af4c0b3b60c7023adb1d"
    ),
    "backend/app/agent_graph/runtime.py": (
        "a8ff3e91790a0bff9dbcf1c1c4b210a"
        "414970a5783955a16e543de678ec864f0"
    ),
    "backend/app/agent_graph/state.py": (
        "cf13e5f7b435e6c2f1d2c6b3c05795"
        "a648d7396290ab36635a820cdb60e38e95"
    ),
    "backend/app/api/agent.py": (
        "a8550f3e807628b78efeff5eaa7299dd"
        "972fcb6738a1fd9b809aa146af6ea775"
    ),
    "backend/app/database.py": (
        "fafa27268568f1da139178d6f3b85145"
        "a8bf905c1b9a35b149fccae20933f3f2"
    ),
    "backend/app/db/session.py": (
        "f94e85a152c8ccfa11b6e53349980a59"
        "9da40d9924fb5443eb8a8dca28680ebe"
    ),
    "backend/app/models/agent_run.py": (
        "28918fb3f0cb618c06474baf4d54a845"
        "f459434ccb8c775e50d1370acb69169a"
    ),
    "backend/app/models/agent_step.py": (
        "f50933097aca8f7b7db57467397a97365"
        "40d913e22ec8a78dcb43289e91b4346"
    ),
    "backend/app/models/agent_tool_call.py": (
        "0c420f6447ea6c50dab62bec0e713e44"
        "bd4b9f2b6f14a06022d07a5834ac8a1d"
    ),
    "backend/app/services/agent_orchestration_service.py": (
        "69b204f3c08bebf8a105490079297dc7"
        "404b1a53345c1fb6f4f3f14a10840984"
    ),
    "backend/app/services/agent_persistence_service.py": (
        "cf788d558687340843ea10df61b76d68"
        "5f65a6190fd98e00eb1ced5e9af7fdf8"
    ),
    "backend/app/services/agent_replay_aware_tool_execution_service.py": (
        "f631c10235ccd4ef7f2155d771eae6c7"
        "d930e2a617f0d71e957b29da2dee282f"
    ),
    "backend/app/services/agent_runner_service.py": (
        "fa853ab1bb2d8527d345515144e3c81"
        "02b115efdcf2281f9b913f76ac6bb8730"
    ),
    "backend/app/services/agent_tool_executor_service.py": (
        "da6eb507a39eb1ff5e2ba9228c3065f9"
        "10e9ddfa2322409b7c838428fd72442f"
    ),
    "backend/app/services/agent_tool_result_state_service.py": (
        "03b0fa20755df08bb666694b25c07f61"
        "c85d13388ad2b5dabe7db48704b7f357"
    ),
}

EXPECTED_SCOPE = [
    "?? backend/app/agent_graph/coordinator.py",
    (
        "?? backend/scripts/"
        "validate_agent_graph_step_coordinator_foundation.py"
    ),
]

assertion_count = 0
test_count = 0


def check(condition: bool, message: str) -> None:
    global assertion_count
    assertion_count += 1
    if not condition:
        raise AssertionError(message)


def test(name: str, callback) -> None:
    global test_count
    callback()
    test_count += 1
    print(f"test={name}:passed")


@dataclass
class Snapshot:
    values: Mapping[str, object]
    next: tuple[str, ...]


class FakeGraph:
    def __init__(
        self,
        snapshot: Snapshot,
        *,
        read_error: Exception | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.read_error = read_error
        self.get_state_calls: list[
            Mapping[str, object]
        ] = []
        self.update_state_calls = 0

    def get_state(
        self,
        config: Mapping[str, object],
    ) -> Snapshot:
        self.get_state_calls.append(config)
        if self.read_error is not None:
            raise self.read_error
        return self.snapshot

    def update_state(self, *args, **kwargs) -> None:
        self.update_state_calls += 1
        raise AssertionError(
            "Coordinator must not call update_state"
        )


class ProviderSpy:
    def __init__(
        self,
        graph: object | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.graph = graph
        self.error = error
        self.call_count = 0

    def __call__(self) -> object:
        self.call_count += 1
        if self.error is not None:
            raise self.error
        return self.graph


class DriverSpy(AgentGraphSingleStepDriver):
    def __init__(
        self,
        *,
        error: AgentGraphSingleStepDriverError
        | None = None,
    ) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def execute_next_node(
        self,
        compiled_graph: object,
        *,
        thread_config: Mapping[str, object],
        expected_node: str,
    ) -> AgentGraphSingleStepResult:
        self.calls.append(
            {
                "compiled_graph": compiled_graph,
                "thread_config": thread_config,
                "expected_node": expected_node,
            }
        )
        if self.error is not None:
            raise self.error
        return AgentGraphSingleStepResult(
            node_name=expected_node,
            node_update={"visited": expected_node},
            before_next=(expected_node,),
            after_next=("triage_issue",),
            before_values={"before": True},
            after_values={"after": True},
        )


def valid_state(
    *,
    run_id: str = "run-123",
    issue_id: int = 42,
    current_node: str = LOAD_ISSUE_NODE,
    transition_count: int = 0,
) -> dict[str, object]:
    state = dict(
        build_initial_agent_graph_state(
            run_id=run_id,
            issue_id=issue_id,
        )
    )
    state["current_node"] = current_node
    state["transition_count"] = transition_count
    return state


def execute(
    *,
    persisted_state: Mapping[str, object] | None = None,
    checkpoint_values: Mapping[str, object] | None = None,
    checkpoint_next: tuple[str, ...] = (LOAD_ISSUE_NODE,),
    expected_node: str = LOAD_ISSUE_NODE,
    run_id: str = "run-123",
    provider_error: Exception | None = None,
    read_error: Exception | None = None,
    driver_error: AgentGraphSingleStepDriverError
    | None = None,
):
    persisted = (
        valid_state()
        if persisted_state is None
        else persisted_state
    )
    values = (
        persisted
        if checkpoint_values is None
        else checkpoint_values
    )
    graph = FakeGraph(
        Snapshot(
            values=values,
            next=checkpoint_next,
        ),
        read_error=read_error,
    )
    provider = ProviderSpy(
        graph,
        error=provider_error,
    )
    driver = DriverSpy(error=driver_error)
    coordinator = AgentGraphStepCoordinator(
        compiled_graph_provider=provider,
        driver=driver,
    )

    try:
        result = coordinator.execute_next_node(
            run_id=run_id,
            expected_node=expected_node,
            persisted_state=persisted,
        )
        return (
            result,
            None,
            coordinator,
            provider,
            graph,
            driver,
        )
    except Exception as exc:
        return (
            None,
            exc,
            coordinator,
            provider,
            graph,
            driver,
        )


def assert_blocked(
    *,
    expected_code: str,
    expected_relation: str | None,
    **kwargs,
) -> tuple[
    AgentGraphStepCoordinatorError,
    ProviderSpy,
    FakeGraph,
    DriverSpy,
]:
    (
        result,
        error,
        _coordinator,
        provider,
        graph,
        driver,
    ) = execute(**kwargs)
    check(result is None, "Blocked result must be None")
    check(
        isinstance(
            error,
            AgentGraphStepCoordinatorError,
        ),
        f"Unexpected error type: {type(error).__name__}",
    )
    check(
        error.error_code == expected_code,
        (
            f"error_code mismatch: {error.error_code} "
            f"!= {expected_code}"
        ),
    )
    check(
        error.relation == expected_relation,
        (
            f"relation mismatch: {error.relation} "
            f"!= {expected_relation}"
        ),
    )
    check(
        len(driver.calls) == 0,
        "Driver must not run for blocked relation",
    )
    check(
        graph.update_state_calls == 0,
        "Coordinator must not call update_state",
    )
    return error, provider, graph, driver


def test_public_contract() -> None:
    check(
        AGENT_GRAPH_STEP_COORDINATOR_VERSION
        == "agent_graph_step_coordinator_v0.1",
        "Coordinator version mismatch",
    )
    public_types = {
        AgentGraphStepCoordinatorError.__name__,
        AgentGraphCheckpointInspection.__name__,
        AgentGraphStepCoordinationResult.__name__,
        AgentGraphStepCoordinator.__name__,
    }
    check(
        public_types
        == {
            "AgentGraphStepCoordinatorError",
            "AgentGraphCheckpointInspection",
            "AgentGraphStepCoordinationResult",
            "AgentGraphStepCoordinator",
        },
        "Public type contract mismatch",
    )


def test_constructor_contract() -> None:
    try:
        AgentGraphStepCoordinator(
            compiled_graph_provider=None,
        )
    except TypeError:
        pass
    else:
        raise AssertionError(
            "Non-callable provider must fail"
        )

    try:
        AgentGraphStepCoordinator(
            compiled_graph_provider=lambda: object(),
            driver=object(),
        )
    except TypeError:
        pass
    else:
        raise AssertionError(
            "Invalid Driver must fail"
        )
    check(True, "Constructor contract passed")


def test_invalid_run_id() -> None:
    _, error, _, provider, _, driver = execute(
        run_id=" run-123"
    )
    check(
        isinstance(
            error,
            AgentGraphStepCoordinatorError,
        ),
        "Invalid run_id must raise Coordinator error",
    )
    check(
        error.error_code == "invalid_run_id",
        "Invalid run_id error code mismatch",
    )
    check(provider.call_count == 0, "Provider must not run")
    check(len(driver.calls) == 0, "Driver must not run")


def test_invalid_expected_node() -> None:
    _, error, _, provider, _, driver = execute(
        expected_node="not-a-node"
    )
    check(
        error.error_code == "invalid_expected_node",
        "Invalid expected_node code mismatch",
    )
    check(provider.call_count == 0, "Provider must not run")
    check(len(driver.calls) == 0, "Driver must not run")


def test_invalid_persisted_state() -> None:
    _, error, _, provider, _, driver = execute(
        persisted_state={"run_id": "run-123"}
    )
    check(
        error.error_code == "invalid_persisted_state",
        "Invalid persisted state code mismatch",
    )
    check(provider.call_count == 0, "Provider must not run")
    check(len(driver.calls) == 0, "Driver must not run")


def test_persisted_run_identity_mismatch() -> None:
    persisted = valid_state(run_id="other-run")
    _, error, _, provider, _, driver = execute(
        run_id="run-123",
        persisted_state=persisted,
    )
    check(
        error.error_code
        == "persisted_run_identity_mismatch",
        "Persisted run identity code mismatch",
    )
    check(provider.call_count == 0, "Provider must not run")
    check(len(driver.calls) == 0, "Driver must not run")


def test_provider_failure() -> None:
    error, provider, graph, driver = assert_blocked(
        expected_code="compiled_graph_provider_failed",
        expected_relation=None,
        provider_error=RuntimeError("provider failed"),
    )
    check(provider.call_count == 1, "Provider call count mismatch")
    check(len(graph.get_state_calls) == 0, "Graph must not be read")
    check(error.__cause__ is not None, "Provider cause missing")
    check(len(driver.calls) == 0, "Driver must not run")


def test_provider_invalid_product() -> None:
    persisted = valid_state()
    provider = ProviderSpy(object())
    driver = DriverSpy()
    coordinator = AgentGraphStepCoordinator(
        compiled_graph_provider=provider,
        driver=driver,
    )
    try:
        coordinator.execute_next_node(
            run_id="run-123",
            expected_node=LOAD_ISSUE_NODE,
            persisted_state=persisted,
        )
    except AgentGraphStepCoordinatorError as exc:
        check(
            exc.error_code
            == "compiled_graph_provider_failed",
            "Invalid graph product code mismatch",
        )
    else:
        raise AssertionError(
            "Invalid graph product must fail"
        )
    check(provider.call_count == 1, "Provider call count mismatch")
    check(len(driver.calls) == 0, "Driver must not run")


def test_checkpoint_read_failure() -> None:
    error, provider, graph, driver = assert_blocked(
        expected_code="checkpoint_read_failed",
        expected_relation="checkpoint_read_failure",
        read_error=RuntimeError("read failed"),
    )
    check(provider.call_count == 1, "Provider call count mismatch")
    check(len(graph.get_state_calls) == 1, "Read count mismatch")
    check(error.__cause__ is not None, "Read cause missing")
    check(len(driver.calls) == 0, "Driver must not run")


def test_checkpoint_missing() -> None:
    error, provider, graph, _driver = assert_blocked(
        expected_code="checkpoint_bootstrap_required",
        expected_relation="checkpoint_missing",
        checkpoint_values={},
        checkpoint_next=(),
    )
    check(provider.call_count == 1, "Provider call count mismatch")
    check(len(graph.get_state_calls) == 1, "Read count mismatch")
    check(error.inspection is not None, "Inspection missing")
    check(
        error.inspection.as_dict()["checkpoint_next"] == [],
        "Missing checkpoint next mismatch",
    )


def test_identity_mismatch_run_id() -> None:
    checkpoint = valid_state(run_id="other-run")
    error, _, _, _ = assert_blocked(
        expected_code="checkpoint_identity_mismatch",
        expected_relation="checkpoint_identity_mismatch",
        checkpoint_values=checkpoint,
    )
    check(error.inspection is not None, "Inspection missing")


def test_identity_mismatch_issue_id() -> None:
    checkpoint = valid_state(issue_id=99)
    assert_blocked(
        expected_code="checkpoint_identity_mismatch",
        expected_relation="checkpoint_identity_mismatch",
        checkpoint_values=checkpoint,
    )


def test_identity_mismatch_schema() -> None:
    checkpoint = valid_state()
    checkpoint["state_schema_version"] = "wrong"
    assert_blocked(
        expected_code="checkpoint_identity_mismatch",
        expected_relation="checkpoint_identity_mismatch",
        checkpoint_values=checkpoint,
    )


def test_identity_mismatch_graph_version() -> None:
    checkpoint = valid_state()
    checkpoint["graph_version"] = "wrong"
    assert_blocked(
        expected_code="checkpoint_identity_mismatch",
        expected_relation="checkpoint_identity_mismatch",
        checkpoint_values=checkpoint,
    )


def test_database_ahead() -> None:
    persisted = valid_state(transition_count=2)
    checkpoint = valid_state(transition_count=1)
    assert_blocked(
        expected_code=(
            "database_ahead_reconciliation_required"
        ),
        expected_relation="database_ahead",
        persisted_state=persisted,
        checkpoint_values=checkpoint,
    )


def test_graph_ahead() -> None:
    persisted = valid_state(transition_count=1)
    checkpoint = valid_state(transition_count=2)
    assert_blocked(
        expected_code=(
            "graph_ahead_reconciliation_required"
        ),
        expected_relation="graph_ahead",
        persisted_state=persisted,
        checkpoint_values=checkpoint,
    )


def test_checkpoint_state_validation_failure() -> None:
    checkpoint = valid_state()
    checkpoint["current_node"] = "not-a-node"
    assert_blocked(
        expected_code="checkpoint_state_mismatch",
        expected_relation="checkpoint_state_mismatch",
        checkpoint_values=checkpoint,
    )


def test_equal_transition_state_mismatch() -> None:
    persisted = valid_state()
    checkpoint = valid_state()
    checkpoint["triage_confirmed"] = True
    assert_blocked(
        expected_code="checkpoint_state_mismatch",
        expected_relation="checkpoint_state_mismatch",
        persisted_state=persisted,
        checkpoint_values=checkpoint,
    )


def test_scheduled_node_mismatch() -> None:
    assert_blocked(
        expected_code="checkpoint_state_mismatch",
        expected_relation="checkpoint_state_mismatch",
        checkpoint_next=(TRIAGE_ISSUE_NODE,),
        expected_node=LOAD_ISSUE_NODE,
    )


def test_matched_checkpoint() -> None:
    (
        result,
        error,
        _coordinator,
        provider,
        graph,
        driver,
    ) = execute()
    check(error is None, f"Unexpected error: {error}")
    check(
        isinstance(
            result,
            AgentGraphStepCoordinationResult,
        ),
        "Coordination result type mismatch",
    )
    check(provider.call_count == 1, "Provider call count mismatch")
    check(
        len(graph.get_state_calls) == 1,
        "Coordinator checkpoint read count mismatch",
    )
    check(len(driver.calls) == 1, "Driver call count mismatch")
    call = driver.calls[0]
    check(
        call["compiled_graph"] is graph,
        "Driver graph identity mismatch",
    )
    check(
        call["thread_config"]
        == {"configurable": {"thread_id": "run-123"}},
        "Thread config mismatch",
    )
    check(
        set(call["thread_config"]["configurable"])
        == {"thread_id"},
        "Thread config must be thread_id-only",
    )
    check(
        result.inspection.relation
        == "checkpoint_matches_persisted_state",
        "Matched relation mismatch",
    )
    check(
        result.driver_result.node_name
        == LOAD_ISSUE_NODE,
        "Driver result node mismatch",
    )
    check(graph.update_state_calls == 0, "update_state called")


def test_current_node_is_not_expected_node() -> None:
    persisted = valid_state(
        current_node=LOAD_ISSUE_NODE
    )
    (
        result,
        error,
        _coordinator,
        _provider,
        _graph,
        driver,
    ) = execute(
        persisted_state=persisted,
        checkpoint_values=dict(persisted),
        checkpoint_next=(TRIAGE_ISSUE_NODE,),
        expected_node=TRIAGE_ISSUE_NODE,
    )
    check(error is None, f"Unexpected error: {error}")
    check(
        result.inspection.persisted_state["current_node"]
        == LOAD_ISSUE_NODE,
        "Persisted current_node changed unexpectedly",
    )
    check(
        result.inspection.expected_node
        == TRIAGE_ISSUE_NODE,
        "Expected node mismatch",
    )
    check(len(driver.calls) == 1, "Driver must run once")


def test_driver_error_propagation() -> None:
    driver_error = AgentGraphSingleStepDriverError(
        error_code="driver_contract_failure",
        message="driver failed",
    )
    (
        result,
        error,
        _coordinator,
        provider,
        graph,
        driver,
    ) = execute(driver_error=driver_error)
    check(result is None, "Result must be None")
    check(error is driver_error, "Driver error was rewritten")
    check(
        error.error_code == "driver_contract_failure",
        "Driver error code changed",
    )
    check(provider.call_count == 1, "Provider call count mismatch")
    check(len(graph.get_state_calls) == 1, "Read count mismatch")
    check(len(driver.calls) == 1, "Driver call count mismatch")


def test_immutability_and_as_dict() -> None:
    result, error, *_ = execute()
    check(error is None, f"Unexpected error: {error}")

    try:
        result.inspection.relation = "changed"
    except (FrozenInstanceError, AttributeError):
        pass
    else:
        raise AssertionError("Inspection must be frozen")

    try:
        result.inspection.persisted_state["run_id"] = "changed"
    except TypeError:
        pass
    else:
        raise AssertionError("Persisted state must be immutable")

    payload = result.as_dict()
    check(
        payload["coordinator_version"]
        == AGENT_GRAPH_STEP_COORDINATOR_VERSION,
        "Result version mismatch",
    )
    check(
        payload["inspection"]["thread_config"]
        == {"configurable": {"thread_id": "run-123"}},
        "Inspection as_dict mismatch",
    )
    check(
        isinstance(
            payload["driver_result"],
            dict,
        ),
        "Driver result as_dict mismatch",
    )


def test_relation_precedence() -> None:
    checkpoint = valid_state(
        run_id="different",
        transition_count=9,
    )
    error, *_ = assert_blocked(
        expected_code="checkpoint_identity_mismatch",
        expected_relation="checkpoint_identity_mismatch",
        checkpoint_values=checkpoint,
        checkpoint_next=(TRIAGE_ISSUE_NODE,),
    )
    check(
        error.relation
        == "checkpoint_identity_mismatch",
        "Identity must precede transition and next mismatch",
    )

    missing_error, *_ = assert_blocked(
        expected_code="checkpoint_bootstrap_required",
        expected_relation="checkpoint_missing",
        checkpoint_values={},
        checkpoint_next=(),
    )
    check(
        missing_error.relation == "checkpoint_missing",
        "Missing precedence mismatch",
    )


def test_source_ownership_guard() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    coordinator_path = (
        repo_root
        / "backend/app/agent_graph/coordinator.py"
    )
    source = coordinator_path.read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)

    imported_modules = []
    update_state_calls = []
    saver_names = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(
                alias.name
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            imported_modules.append(node.module or "")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "update_state"
        ):
            update_state_calls.append(node.lineno)
        elif isinstance(node, ast.Name) and node.id in {
            "InMemorySaver",
            "PostgresSaver",
            "Session",
            "AgentRunnerService",
            "AgentOrchestrationService",
            "AgentPersistenceService",
        }:
            saver_names.append((node.id, node.lineno))

    forbidden_prefixes = (
        "sqlalchemy",
        "app.api",
        "app.models",
        "app.services",
    )
    check(
        not any(
            module.startswith(forbidden_prefixes)
            for module in imported_modules
        ),
        f"Forbidden import found: {imported_modules}",
    )
    check(
        not update_state_calls,
        f"update_state call found: {update_state_calls}",
    )
    check(
        not saver_names,
        f"Forbidden ownership name found: {saver_names}",
    )
    check(
        "commit(" not in source
        and "rollback(" not in source
        and "with_for_update" not in source,
        "Database ownership token found",
    )


def test_git_scope_and_protected_hashes() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    status = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.splitlines()
    check(status == EXPECTED_SCOPE, f"Scope mismatch: {status}")

    cached = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "--cached",
            "--name-only",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    unstaged = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "--name-only",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    check(cached == "", "Temporary index must be empty")
    check(unstaged == "", "Tracked files must be unchanged")

    for relative, expected_hash in (
        EXPECTED_PROTECTED_HASHES.items()
    ):
        actual_hash = hashlib.sha256(
            (repo_root / relative).read_bytes()
        ).hexdigest()
        check(
            actual_hash == expected_hash,
            f"Protected hash mismatch: {relative}",
        )


TESTS = [
    ("public_contract", test_public_contract),
    ("constructor_contract", test_constructor_contract),
    ("invalid_run_id", test_invalid_run_id),
    ("invalid_expected_node", test_invalid_expected_node),
    ("invalid_persisted_state", test_invalid_persisted_state),
    (
        "persisted_run_identity_mismatch",
        test_persisted_run_identity_mismatch,
    ),
    ("provider_failure", test_provider_failure),
    ("provider_invalid_product", test_provider_invalid_product),
    ("checkpoint_read_failure", test_checkpoint_read_failure),
    ("checkpoint_missing", test_checkpoint_missing),
    ("identity_mismatch_run_id", test_identity_mismatch_run_id),
    ("identity_mismatch_issue_id", test_identity_mismatch_issue_id),
    ("identity_mismatch_schema", test_identity_mismatch_schema),
    (
        "identity_mismatch_graph_version",
        test_identity_mismatch_graph_version,
    ),
    ("database_ahead", test_database_ahead),
    ("graph_ahead", test_graph_ahead),
    (
        "checkpoint_state_validation_failure",
        test_checkpoint_state_validation_failure,
    ),
    (
        "equal_transition_state_mismatch",
        test_equal_transition_state_mismatch,
    ),
    ("scheduled_node_mismatch", test_scheduled_node_mismatch),
    ("matched_checkpoint", test_matched_checkpoint),
    (
        "current_node_is_not_expected_node",
        test_current_node_is_not_expected_node,
    ),
    ("driver_error_propagation", test_driver_error_propagation),
    ("immutability_and_as_dict", test_immutability_and_as_dict),
    ("relation_precedence", test_relation_precedence),
    ("source_ownership_guard", test_source_ownership_guard),
    (
        "git_scope_and_protected_hashes",
        test_git_scope_and_protected_hashes,
    ),
]


def main() -> None:
    for name, callback in TESTS:
        test(name, callback)

    check(test_count == 26, "Test count mismatch")
    check(
        assertion_count >= 150,
        "Assertion count is below the frozen minimum",
    )

    print(
        "Agent Graph Step Coordinator foundation "
        "assertions passed"
    )
    print(
        "coordinator_version="
        + AGENT_GRAPH_STEP_COORDINATOR_VERSION
    )
    print(
        "contract_id="
        "agent_graph_step_coordinator_foundation_scope_v0.1"
    )
    print("foundation_mode=matched_checkpoint_only")
    print(
        "checkpoint_mutation_policy="
        "no_update_state_no_bootstrap_no_reconciliation"
    )
    print("production_wiring_policy=unwired")
    print("write_file_count=2")
    print("existing_file_modification_count=0")
    print("protected_file_count=19")
    print(f"assertion_count={assertion_count}")
    print(f"test_count={test_count}")
    print("stage=completed")


if __name__ == "__main__":
    main()
