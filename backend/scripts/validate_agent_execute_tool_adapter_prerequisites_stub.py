from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
import sys
from typing import Callable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.agent_orchestration_service import (  # noqa: E402
    AgentOrchestrationService,
)
from app.services.agent_persistence_service import (  # noqa: E402
    AgentPersistenceService,
    AgentToolCallReplayPersistenceError,
    AgentToolCallReplayReservation,
)
from app.services.agent_replay_aware_tool_execution_service import (  # noqa: E402
    AgentReplayAwareToolExecutionOutcome,
    AgentReplayAwareToolExecutionService,
)
from app.services.agent_tool_contract_service import (  # noqa: E402
    agent_tool_contract_service,
)
from app.services.agent_tool_executor_service import (  # noqa: E402
    AgentToolExecutionOutcome,
)
from app.services.agent_tool_registry import (  # noqa: E402
    SEARCH_KNOWLEDGE_TOOL,
    approved_agent_tool_registry,
)
from app.services.agent_tool_result_state_service import (  # noqa: E402
    AgentToolResultStateError,
    AgentToolResultStateOutcome,
    AgentToolResultStateService,
)
from app.services.agent_tool_selection_service import (  # noqa: E402
    AGENT_TOOL_SELECTION_VERSION,
)


ASSERTION_COUNT = 0
TEST_COUNT = 0

PROTECTED_HASHES = {
    "backend/app/agent_graph/builder.py": (
        "f6ab00a91bc28f712360a387d9db9635cc07098a9e2bf189e2241a27b77a843b"
    ),
    "backend/app/agent_graph/nodes.py": (
        "7c19866f93b1c9ad8ce9aec91abec84d9b537754453cfd145c602a5c4732889a"
    ),
    "backend/app/agent_graph/runtime.py": (
        "a8ff3e91790a0bff9dbcf1c1c4b210a414970a5783955a16e543de678ec864f0"
    ),
    "backend/app/agent_graph/state.py": (
        "cf13e5f7b435e6c2f1d2c6b3c05795a648d7396290ab36635a820cdb60e38e95"
    ),
    "backend/app/services/agent_guarded_tool_execution_service.py": (
        "39911205b51717773d667ffb19a13ad8cbaf08b0db1e844289c399410ddcc19c"
    ),
    "backend/app/services/agent_runner_service.py": (
        "fa853ab1bb2d8527d345515144e3c8102b115efdcf2281f9b913f76ac6bb8730"
    ),
}


def check(condition: bool, message: str) -> None:
    global ASSERTION_COUNT
    ASSERTION_COUNT += 1

    if not condition:
        raise AssertionError(message)


def test_case(callback: Callable[[], None]) -> None:
    global TEST_COUNT
    callback()
    TEST_COUNT += 1


def expect_raises(
    exception_type: type[BaseException],
    callback: Callable[[], object],
) -> BaseException:
    try:
        callback()
    except exception_type as exc:
        return exc

    raise AssertionError(
        f"Expected {exception_type.__name__} to be raised"
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_sha256(path: Path) -> str:
    normalized = (
        path.read_bytes()
        .replace(b"\r\n", b"\n")
        .replace(b"\r", b"\n")
    )
    return hashlib.sha256(normalized).hexdigest()


class FakeRows:
    def __init__(
        self,
        rows: list[tuple[object, int]],
    ) -> None:
        self._rows = list(rows)

    def all(self) -> list[tuple[object, int]]:
        return list(self._rows)


class FakeDb:
    def __init__(
        self,
        *,
        rows: list[tuple[object, int]] | None = None,
    ) -> None:
        self.rows = list(rows or [])
        self.added: list[object] = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self.refreshed: list[object] = []

    def execute(self, _statement: object) -> FakeRows:
        return FakeRows(self.rows)

    def add(self, value: object) -> None:
        self.added.append(value)

    def flush(self) -> None:
        self.flush_count += 1

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def refresh(self, value: object) -> None:
        self.refreshed.append(value)


def validated_arguments():
    return agent_tool_contract_service.validate_arguments(
        SEARCH_KNOWLEDGE_TOOL,
        {"issue_id": 17},
    )


def definition():
    return approved_agent_tool_registry.get(
        SEARCH_KNOWLEDGE_TOOL
    )


def make_tool_call(
    *,
    status: str,
    result_json: dict[str, object] | None = None,
    tool_call_index: int = 1,
) -> SimpleNamespace:
    current = definition()
    return SimpleNamespace(
        agent_step_id=20,
        tool_call_index=tool_call_index,
        tool_name=current.tool_name,
        tool_version=current.tool_version,
        call_status=status,
        arguments_json={"issue_id": 17},
        result_json=result_json,
        read_only=True,
        requires_approval=False,
        timeout_seconds=current.timeout_seconds,
        error_code=None,
        error_message=None,
    )


def current_run(
    *,
    run_status: str = "running",
    current_node: str = "execute_tool",
    step_count: int = 3,
    tool_call_count: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=10,
        run_id="run-001",
        run_status=run_status,
        current_node=current_node,
        step_count=step_count,
        tool_call_count=tool_call_count,
    )


def current_step(
    *,
    step_status: str = "running",
    node_name: str = "execute_tool",
    step_index: int = 3,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=20,
        step_index=step_index,
        step_status=step_status,
        node_name=node_name,
    )


def build_current_persistence(
    *,
    run: SimpleNamespace | None = None,
    step: SimpleNamespace | None = None,
    rows: list[tuple[object, int]] | None = None,
) -> tuple[AgentPersistenceService, FakeDb]:
    service = AgentPersistenceService()
    db = FakeDb(rows=rows)
    actual_run = run if run is not None else current_run()
    actual_step = step if step is not None else current_step()
    service.lock_run_by_run_id = (
        lambda _db, _run_id: actual_run
    )
    service.lock_step_by_run_and_index = (
        lambda _db, **_kwargs: actual_step
    )
    return service, db


class RecordingCurrentPersistence:
    def __init__(
        self,
        *,
        reservation: AgentToolCallReplayReservation | None = None,
        error: Exception | None = None,
    ) -> None:
        self.reservation = reservation
        self.error = error
        self.calls: list[tuple[object, dict[str, object]]] = []

    def reserve_or_reuse_current_tool_call(
        self,
        db: object,
        **kwargs: object,
    ) -> AgentToolCallReplayReservation:
        self.calls.append((db, dict(kwargs)))
        if self.error is not None:
            raise self.error
        if self.reservation is None:
            raise RuntimeError("reservation is missing")
        return self.reservation


class RecordingCurrentOrchestration:
    def __init__(
        self,
        reservation: AgentToolCallReplayReservation,
    ) -> None:
        self.reservation = reservation
        self.calls: list[tuple[object, dict[str, object]]] = []

    def reserve_or_reuse_current_tool_call(
        self,
        db: object,
        **kwargs: object,
    ) -> AgentToolCallReplayReservation:
        self.calls.append((db, dict(kwargs)))
        return self.reservation


class NoDispatch:
    def __init__(self) -> None:
        self.call_count = 0

    def execute(self, *_args: object) -> object:
        self.call_count += 1
        raise AssertionError("Dispatch must not occur")


def no_result() -> dict[str, object]:
    return {
        "retrieval_status": "no_results",
        "retrieval_query": "controlled query",
        "knowledge_evidence": [],
        "knowledge_citations": [],
        "retrieval_error_code": None,
    }


def selected_tool() -> dict[str, object]:
    validated = validated_arguments()
    return {
        "selection_version": AGENT_TOOL_SELECTION_VERSION,
        "tool_name": validated.tool_name,
        "tool_version": validated.tool_version,
        "arguments": validated.as_dict(),
        "call_identity": validated.call_identity,
        "confidence": 0.9,
        "reason": "Controlled replay selection.",
    }


def base_state() -> dict[str, object]:
    return {
        "issue_id": 17,
        "selected_tool": selected_tool(),
        "tool_results": [],
        "retrieved_evidence": [],
    }


def replay_outcome(
    *,
    step_index: int = 3,
    result_json: dict[str, object] | None = None,
) -> AgentReplayAwareToolExecutionOutcome:
    validated = validated_arguments()
    tool_call = make_tool_call(
        status="completed",
        result_json=(
            result_json
            if result_json is not None
            else no_result()
        ),
    )
    reservation = AgentToolCallReplayReservation(
        tool_call=tool_call,
        call_identity=validated.call_identity,
        reservation_action="reused",
        step_index=step_index,
    )
    execution = AgentToolExecutionOutcome(
        tool_call=tool_call,
        tool_name=validated.tool_name,
        tool_version=validated.tool_version,
        call_identity=validated.call_identity,
        result_json=MappingProxyType(
            dict(
                result_json
                if result_json is not None
                else no_result()
            )
        ),
    )
    return AgentReplayAwareToolExecutionOutcome(
        reservation=reservation,
        execution=execution,
        replayed=True,
        dispatch_performed=False,
    )


def test_reservation_step_index_contract() -> None:
    reservation = AgentToolCallReplayReservation(
        tool_call=make_tool_call(status="created"),
        call_identity=validated_arguments().call_identity,
        reservation_action="created",
        step_index=3,
    )
    payload = reservation.as_dict()

    check(reservation.step_index == 3, "step_index missing")
    check(payload["step_index"] == 3, "serialization missing")
    check(
        AgentToolCallReplayReservation(
            tool_call=make_tool_call(status="created"),
            call_identity=validated_arguments().call_identity,
            reservation_action="created",
        ).step_index
        is None,
        "Explicit API backward compatibility changed",
    )
    expect_raises(
        ValueError,
        lambda: AgentToolCallReplayReservation(
            tool_call=make_tool_call(status="created"),
            call_identity=validated_arguments().call_identity,
            reservation_action="created",
            step_index=0,
        ),
    )
    check(True, "Invalid step_index must fail")
    expect_raises(
        FrozenInstanceError,
        lambda: setattr(reservation, "step_index", 4),
    )
    check(True, "Reservation must remain frozen")


def test_current_step_create_and_reuse() -> None:
    run = current_run()
    service, db = build_current_persistence(run=run)
    created = service.reserve_or_reuse_current_tool_call(
        db,
        run_id="run-001",
        tool_name=SEARCH_KNOWLEDGE_TOOL,
        arguments_json={"issue_id": 17},
        max_tool_calls=3,
    )

    check(created.step_index == 3, "Current Step was not returned")
    check(created.reservation_action == "created", "Create path changed")
    check(run.tool_call_count == 1, "ToolCall count was not incremented")
    check(db.flush_count == 1, "Create path must flush once")

    existing = make_tool_call(status="completed", result_json=no_result())
    reused_run = current_run(tool_call_count=1)
    reused_service, reused_db = build_current_persistence(
        run=reused_run,
        rows=[(existing, 3)],
    )
    reused = reused_service.reserve_or_reuse_current_tool_call(
        reused_db,
        run_id="run-001",
        tool_name=SEARCH_KNOWLEDGE_TOOL,
        arguments_json={"issue_id": 17},
        max_tool_calls=1,
    )

    check(reused.step_index == 3, "Reuse Step was not returned")
    check(reused.reservation_action == "reused", "Reuse path changed")
    check(reused.tool_call is existing, "Existing ToolCall not reused")
    check(reused_run.tool_call_count == 1, "Reuse changed count")


def test_current_step_guards() -> None:
    cases = (
        (
            current_run(run_status="waiting_for_clarification"),
            current_step(),
            "invalid_replay_run_status",
        ),
        (
            current_run(current_node="select_tool"),
            current_step(),
            "invalid_replay_current_node",
        ),
        (
            current_run(step_count=0),
            current_step(),
            "invalid_replay_step_count",
        ),
        (
            current_run(),
            current_step(step_status="completed"),
            "invalid_replay_step_status",
        ),
        (
            current_run(),
            current_step(node_name="select_tool"),
            "invalid_replay_step_node",
        ),
    )

    for run, step, error_code in cases:
        service, db = build_current_persistence(
            run=run,
            step=step,
        )
        exc = expect_raises(
            AgentToolCallReplayPersistenceError,
            lambda service=service, db=db: (
                service.reserve_or_reuse_current_tool_call(
                    db,
                    run_id="run-001",
                    tool_name=SEARCH_KNOWLEDGE_TOOL,
                    arguments_json={"issue_id": 17},
                    max_tool_calls=3,
                )
            ),
        )
        check(
            getattr(exc, "error_code", None) == error_code,
            f"Guard error changed: {error_code}",
        )


def test_current_step_orchestration_boundary() -> None:
    reservation = AgentToolCallReplayReservation(
        tool_call=make_tool_call(status="created"),
        call_identity=validated_arguments().call_identity,
        reservation_action="created",
        step_index=3,
    )
    persistence = RecordingCurrentPersistence(
        reservation=reservation
    )
    service = AgentOrchestrationService(
        persistence_service=persistence
    )
    db = FakeDb()
    actual = service.reserve_or_reuse_current_tool_call(
        db,
        run_id="run-001",
        tool_name=SEARCH_KNOWLEDGE_TOOL,
        arguments_json={"issue_id": 17},
        max_tool_calls=3,
    )

    check(actual is reservation, "Reservation result changed")
    check(db.commit_count == 1, "Orchestration must commit once")
    check(db.rollback_count == 0, "Success must not rollback")
    check(db.refreshed == [reservation.tool_call], "Refresh changed")
    check(len(persistence.calls) == 1, "Persistence call count changed")

    error = RuntimeError("reservation boom")
    failing = AgentOrchestrationService(
        persistence_service=RecordingCurrentPersistence(
            reservation=reservation,
            error=error,
        )
    )
    failed_db = FakeDb()
    raised = expect_raises(
        RuntimeError,
        lambda: failing.reserve_or_reuse_current_tool_call(
            failed_db,
            run_id="run-001",
            tool_name=SEARCH_KNOWLEDGE_TOOL,
            arguments_json={"issue_id": 17},
            max_tool_calls=3,
        ),
    )
    check(raised is error, "Original error must propagate")
    check(failed_db.commit_count == 0, "Failure must not commit")
    check(failed_db.rollback_count == 1, "Failure must rollback once")


def test_replay_service_current_step_path() -> None:
    outcome = replay_outcome()
    dispatch = NoDispatch()
    orchestration = RecordingCurrentOrchestration(
        outcome.reservation
    )
    service = AgentReplayAwareToolExecutionService(
        contract_service=agent_tool_contract_service,
        dispatch_service=dispatch,
        orchestration_service=orchestration,
        registry=approved_agent_tool_registry,
    )
    db = object()
    actual = service.execute_current_step(
        db,
        run_id="run-001",
        tool_name=SEARCH_KNOWLEDGE_TOOL,
        arguments={"issue_id": 17},
        max_tool_calls=3,
    )

    check(actual.replayed is True, "Completed reuse must be replayed")
    check(actual.dispatch_performed is False, "Reuse dispatched Tool")
    check(dispatch.call_count == 0, "Dispatch occurred")
    check(len(orchestration.calls) == 1, "Current reservation not used")
    check(
        "step_index" not in orchestration.calls[0][1],
        "Adapter supplied an explicit step_index",
    )
    check(
        actual.reservation.step_index == 3,
        "Resolved Step index was lost",
    )

    invalid = AgentToolCallReplayReservation(
        tool_call=make_tool_call(status="completed", result_json=no_result()),
        call_identity=validated_arguments().call_identity,
        reservation_action="reused",
    )
    invalid_service = AgentReplayAwareToolExecutionService(
        contract_service=agent_tool_contract_service,
        dispatch_service=dispatch,
        orchestration_service=RecordingCurrentOrchestration(invalid),
        registry=approved_agent_tool_registry,
    )
    expect_raises(
        RuntimeError,
        lambda: invalid_service.execute_current_step(
            db,
            run_id="run-001",
            tool_name=SEARCH_KNOWLEDGE_TOOL,
            arguments={"issue_id": 17},
            max_tool_calls=3,
        ),
    )
    check(True, "Missing resolved Step index must fail")


def test_replay_result_mapping_append_and_noop() -> None:
    service = AgentToolResultStateService()
    state = base_state()
    original = deepcopy(state)
    first = service.apply_replay(
        state,
        replay_outcome(),
    )

    check(isinstance(first, AgentToolResultStateOutcome), "Outcome type changed")
    update = first.to_state_update()
    check(update["selected_tool"] is None, "selected_tool not cleared")
    check(len(update["tool_results"]) == 1, "Tool result not appended")
    check(update["retrieved_evidence"] == [], "Unexpected evidence")
    check(state == original, "Input state was mutated")

    replay_state = {
        **base_state(),
        "tool_results": deepcopy(update["tool_results"]),
        "retrieved_evidence": deepcopy(update["retrieved_evidence"]),
    }
    second = service.apply_replay(
        replay_state,
        replay_outcome(),
    ).to_state_update()

    check(second["selected_tool"] is None, "No-op did not clear selection")
    check(second["tool_results"] == update["tool_results"], "No-op duplicated result")
    check(second["retrieved_evidence"] == [], "No-op changed evidence")


def test_replay_result_mapping_fail_closed() -> None:
    service = AgentToolResultStateService()
    first = service.apply_replay(
        base_state(),
        replay_outcome(),
    ).to_state_update()

    mismatched = deepcopy(first["tool_results"])
    mismatched[0]["result_json"] = {
        **dict(mismatched[0]["result_json"]),
        "retrieval_query": "mismatch",
    }
    mismatch_state = {
        **base_state(),
        "tool_results": mismatched,
        "retrieved_evidence": [],
    }
    exc = expect_raises(
        AgentToolResultStateError,
        lambda: service.apply_replay(
            mismatch_state,
            replay_outcome(),
        ),
    )
    check(
        getattr(exc, "error_code", None)
        == "replay_tool_result_mismatch",
        "Result mismatch error changed",
    )

    orphan_state = {
        **base_state(),
        "tool_results": [],
        "retrieved_evidence": [
            {
                "source_tool": SEARCH_KNOWLEDGE_TOOL,
                "source_call_identity": (
                    validated_arguments().call_identity
                ),
                "evidence_type": "knowledge_chunk",
                "payload": {"chunk_id": 1},
            }
        ],
    }
    orphan = expect_raises(
        AgentToolResultStateError,
        lambda: service.apply_replay(
            orphan_state,
            replay_outcome(),
        ),
    )
    check(
        getattr(orphan, "error_code", None)
        == "orphan_replay_evidence",
        "Orphan evidence error changed",
    )

    invalid_status = replay_outcome()
    invalid_status.execution.tool_call.call_status = "running"
    status_error = expect_raises(
        AgentToolResultStateError,
        lambda: service.apply_replay(
            base_state(),
            invalid_status,
        ),
    )
    check(
        getattr(status_error, "error_code", None)
        == "replay_tool_call_not_completed",
        "Non-completed status error changed",
    )


def call_terminals(path: Path) -> set[str]:
    tree = ast.parse(
        path.read_text(encoding="utf-8-sig")
    )
    values: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name):
            values.add(function.id)
        elif isinstance(function, ast.Attribute):
            values.add(function.attr)

    return values


def test_source_boundaries() -> None:
    normalized_paths = {
        "backend/app/agent_graph/state.py",
    }

    for relative, expected in PROTECTED_HASHES.items():
        path = REPO_ROOT / relative
        actual_hash = (
            normalized_sha256(path)
            if relative in normalized_paths
            else sha256(path)
        )
        check(
            actual_hash == expected,
            f"Protected source changed: {relative}",
        )

    persistence = (
        REPO_ROOT
        / "backend/app/services/agent_persistence_service.py"
    )
    orchestration = (
        REPO_ROOT
        / "backend/app/services/agent_orchestration_service.py"
    )
    replay = (
        REPO_ROOT
        / "backend/app/services/agent_replay_aware_tool_execution_service.py"
    )
    result_state = (
        REPO_ROOT
        / "backend/app/services/agent_tool_result_state_service.py"
    )

    persistence_text = persistence.read_text(encoding="utf-8-sig")
    orchestration_text = orchestration.read_text(encoding="utf-8-sig")
    replay_text = replay.read_text(encoding="utf-8-sig")
    result_text = result_state.read_text(encoding="utf-8-sig")

    check(
        "reserve_or_reuse_current_tool_call" in persistence_text,
        "Current-Step persistence method missing",
    )
    check(
        "reserve_or_reuse_current_tool_call" in orchestration_text,
        "Current-Step orchestration method missing",
    )
    check(
        "execute_current_step" in replay_text,
        "Current-Step replay method missing",
    )
    check(
        "def apply_replay(" in result_text,
        "Replay result-state method missing",
    )
    check(
        "def apply(" in result_text,
        "Existing result-state apply was removed",
    )
    check(
        "AgentRunnerService" not in replay_text,
        "Replay service depends on Custom Runner",
    )
    check(
        "checkpointer" not in replay_text.lower(),
        "Replay service calls Checkpointer",
    )
    check(
        {"commit", "rollback"}.isdisjoint(
            call_terminals(persistence)
        ),
        "Persistence owns transactions",
    )
    check(
        {"commit", "rollback", "flush", "with_for_update"}.isdisjoint(
            call_terminals(replay)
        ),
        "Replay service owns persistence boundaries",
    )
    check(
        {"commit", "rollback", "flush", "with_for_update"}.isdisjoint(
            call_terminals(result_state)
        ),
        "Result-state mapping is not pure",
    )
    runtime_source = (
        REPO_ROOT
        / "backend/app/agent_graph/runtime.py"
    ).read_text(encoding="utf-8-sig")
    check(
        "EXECUTE_TOOL_NODE" in runtime_source,
        "execute_tool Graph wiring is missing",
    )
    check(
        "build_execute_tool_runtime_node"
        in runtime_source,
        "execute_tool Runtime builder wiring is missing",
    )


def main() -> int:
    for callback in (
        test_reservation_step_index_contract,
        test_current_step_create_and_reuse,
        test_current_step_guards,
        test_current_step_orchestration_boundary,
        test_replay_service_current_step_path,
        test_replay_result_mapping_append_and_noop,
        test_replay_result_mapping_fail_closed,
        test_source_boundaries,
    ):
        test_case(callback)

    print("=== COPY THIS SUMMARY ===")
    print("stage=completed")
    print(
        "operation=validate_execute_tool_adapter_prerequisites"
    )
    print(f"assertion_count={ASSERTION_COUNT}")
    print(f"test_count={TEST_COUNT}")
    print("current_step_resolution=passed")
    print("current_step_guard_count=5")
    print("reservation_step_index=passed")
    print("explicit_step_index_api=preserved")
    print("orchestration_transaction_boundary=passed")
    print("replay_execute_current_step=passed")
    print("replay_result_append=passed")
    print("replay_result_exact_no_op=passed")
    print("replay_result_mismatch_fail_closed=passed")
    print("existing_result_apply=preserved")
    print("graph_execute_tool_wired=yes")
    print("runtime_modified=yes")
    print("nodes_modified=yes")
    print("state_modified=no")
    print("builder_modified=no")
    print("schema_migration_created=no")
    print("runner_dependency=no")
    print("checkpointer_calls=0")
    print("database_accessed=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
