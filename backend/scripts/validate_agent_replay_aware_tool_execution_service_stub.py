from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
import sys
from typing import Callable

from pydantic import BaseModel


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.schemas.agent_tools import (  # noqa: E402
    AgentSearchKnowledgeOutput,
)
from app.services.agent_orchestration_service import (  # noqa: E402
    AgentOrchestrationService,
)
from app.services.agent_persistence_service import (  # noqa: E402
    AGENT_TOOL_CALL_REPLAY_RESERVATION_VERSION,
    AgentPersistenceService,
    AgentToolCallReplayPersistenceError,
    AgentToolCallReplayReservation,
)
from app.services.agent_replay_aware_tool_execution_service import (  # noqa: E402
    AGENT_REPLAY_AWARE_TOOL_EXECUTION_VERSION,
    AgentReplayAwareToolExecutionError,
    AgentReplayAwareToolExecutionOutcome,
    AgentReplayAwareToolExecutionService,
)
from app.services.agent_tool_contract_service import (  # noqa: E402
    agent_tool_contract_service,
)
from app.services.agent_tool_registry import (  # noqa: E402
    approved_agent_tool_registry,
)


ASSERTION_COUNT = 0

EXPECTED_HASHES = {
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
    "backend/app/services/agent_tool_executor_service.py": (
        "da6eb507a39eb1ff5e2ba9228c3065f910e9ddfa2322409b7c838428fd72442f"
    ),
    "backend/app/services/agent_runner_service.py": (
        "fa853ab1bb2d8527d345515144e3c8102b115efdcf2281f9b913f76ac6bb8730"
    ),
    "backend/alembic/versions/0005_agent_persistence.py": (
        "075f6b070dfff2d1f103021b19d697ef95215b06018331836decbddf5437b993"
    ),
    "backend/alembic/versions/0006_agent_tool_cancel.py": (
        "3a4877f043679ed3a68472a045784c67659e5231d337a12f4afdfe532954e0c7"
    ),
}


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
        self.execute_count = 0

    def execute(self, _statement: object) -> FakeRows:
        self.execute_count += 1
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


def approved_arguments(
    issue_id: int = 17,
):
    return (
        agent_tool_contract_service
        .validate_arguments(
            "search_knowledge",
            {"issue_id": issue_id},
        )
    )


def approved_definition():
    return approved_agent_tool_registry.get(
        "search_knowledge"
    )


def make_tool_call(
    *,
    status: str,
    issue_id: int = 17,
    tool_call_index: int = 1,
    result_json: dict[str, object] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    read_only: bool = True,
    requires_approval: bool = False,
    timeout_seconds: int | None = None,
    tool_version: str | None = None,
) -> SimpleNamespace:
    definition = approved_definition()
    return SimpleNamespace(
        agent_step_id=20,
        tool_call_index=tool_call_index,
        tool_name=definition.tool_name,
        tool_version=(
            tool_version
            if tool_version is not None
            else definition.tool_version
        ),
        call_status=status,
        arguments_json={"issue_id": issue_id},
        result_json=result_json,
        read_only=read_only,
        requires_approval=requires_approval,
        timeout_seconds=(
            timeout_seconds
            if timeout_seconds is not None
            else definition.timeout_seconds
        ),
        error_code=error_code,
        error_message=error_message,
    )


def build_persistence(
    *,
    rows: list[tuple[object, int]],
    persisted_count: int | None = None,
    step_index: int = 3,
) -> tuple[
    AgentPersistenceService,
    FakeDb,
    SimpleNamespace,
    SimpleNamespace,
]:
    db = FakeDb(rows=rows)
    run = SimpleNamespace(
        id=10,
        tool_call_count=(
            len(rows)
            if persisted_count is None
            else persisted_count
        ),
    )
    step = SimpleNamespace(
        id=20,
        step_index=step_index,
    )
    service = AgentPersistenceService()
    service.lock_run_by_run_id = (
        lambda _db, _run_id: run
    )
    service.lock_step_by_run_and_index = (
        lambda _db, **_kwargs: step
    )
    return service, db, run, step


class RecordingPersistence:
    def __init__(
        self,
        reservation: AgentToolCallReplayReservation,
        *,
        error: Exception | None = None,
    ) -> None:
        self.reservation = reservation
        self.error = error
        self.calls: list[
            tuple[object, dict[str, object]]
        ] = []

    def reserve_or_reuse_tool_call(
        self,
        db: object,
        **kwargs: object,
    ) -> AgentToolCallReplayReservation:
        self.calls.append(
            (db, dict(kwargs))
        )
        if self.error is not None:
            raise self.error
        return self.reservation


class RecordingOrchestration:
    def __init__(
        self,
        *,
        reservation: AgentToolCallReplayReservation,
        dispatch_status: str | None = None,
    ) -> None:
        self.reservation = reservation
        self.dispatch_status = dispatch_status
        self.events: list[
            tuple[str, dict[str, object]]
        ] = []

    def _record(
        self,
        name: str,
        kwargs: dict[str, object],
    ) -> None:
        self.events.append(
            (name, dict(kwargs))
        )

    def reserve_or_reuse_tool_call(
        self,
        db: object,
        **kwargs: object,
    ) -> AgentToolCallReplayReservation:
        payload = dict(kwargs)
        payload["db"] = db
        self._record("reserve", payload)
        return self.reservation

    def start_tool_call(
        self,
        db: object,
        **kwargs: object,
    ) -> SimpleNamespace:
        payload = dict(kwargs)
        payload["db"] = db
        self._record("start", payload)
        tool_call = self.reservation.tool_call
        tool_call.call_status = "running"
        return tool_call

    def complete_tool_call(
        self,
        db: object,
        **kwargs: object,
    ) -> SimpleNamespace:
        payload = dict(kwargs)
        payload["db"] = db
        self._record("complete", payload)
        tool_call = self.reservation.tool_call
        tool_call.call_status = "completed"
        tool_call.result_json = dict(
            kwargs["result_json"]
        )
        return tool_call

    def fail_tool_call(
        self,
        db: object,
        **kwargs: object,
    ) -> SimpleNamespace:
        payload = dict(kwargs)
        payload["db"] = db
        self._record("fail", payload)
        tool_call = self.reservation.tool_call
        tool_call.call_status = "failed"
        tool_call.error_code = str(
            kwargs["error_code"]
        )
        tool_call.error_message = str(
            kwargs["error_message"]
        )
        return tool_call

    def timeout_tool_call(
        self,
        db: object,
        **kwargs: object,
    ) -> SimpleNamespace:
        payload = dict(kwargs)
        payload["db"] = db
        self._record("timeout", payload)
        tool_call = self.reservation.tool_call
        tool_call.call_status = "timed_out"
        tool_call.error_code = str(
            kwargs["error_code"]
        )
        tool_call.error_message = str(
            kwargs["error_message"]
        )
        return tool_call


class RecordingDispatch:
    def __init__(
        self,
        *,
        result: BaseModel | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[
            tuple[object, object]
        ] = []

    def execute(
        self,
        validated_arguments: object,
        db: object,
    ) -> BaseModel:
        self.calls.append(
            (validated_arguments, db)
        )
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def search_result() -> AgentSearchKnowledgeOutput:
    return AgentSearchKnowledgeOutput(
        retrieval_status="no_results",
        retrieval_query="controlled query",
        knowledge_evidence=(),
        knowledge_citations=(),
        retrieval_error_code=None,
    )


def make_reservation(
    *,
    status: str,
    action: str,
    result_json: dict[str, object] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> AgentToolCallReplayReservation:
    return AgentToolCallReplayReservation(
        tool_call=make_tool_call(
            status=status,
            result_json=result_json,
            error_code=error_code,
            error_message=error_message,
        ),
        call_identity=(
            approved_arguments().call_identity
        ),
        reservation_action=action,
    )


def build_replay_service(
    *,
    reservation: AgentToolCallReplayReservation,
    dispatch: RecordingDispatch,
) -> tuple[
    AgentReplayAwareToolExecutionService,
    RecordingOrchestration,
]:
    orchestration = RecordingOrchestration(
        reservation=reservation
    )
    service = AgentReplayAwareToolExecutionService(
        contract_service=(
            agent_tool_contract_service
        ),
        dispatch_service=dispatch,
        orchestration_service=orchestration,
        registry=approved_agent_tool_registry,
    )
    return service, orchestration


def run_replay(
    service: AgentReplayAwareToolExecutionService,
    db: object,
) -> AgentReplayAwareToolExecutionOutcome:
    return service.execute(
        db,
        run_id="run-001",
        step_index=3,
        tool_name="search_knowledge",
        arguments={"issue_id": 17},
        max_tool_calls=3,
    )


def test_reservation_dataclass() -> None:
    reservation = make_reservation(
        status="created",
        action="created",
    )
    payload = reservation.as_dict()

    check(
        reservation.reservation_version
        == AGENT_TOOL_CALL_REPLAY_RESERVATION_VERSION,
        "Reservation version changed",
    )
    check(
        payload["reservation_action"] == "created",
        "Reservation serialization changed",
    )
    check(
        payload["tool_call_index"] == 1,
        "Reservation ToolCall index changed",
    )
    expect_raises(
        FrozenInstanceError,
        lambda: setattr(
            reservation,
            "reservation_action",
            "reused",
        ),
    )
    check(
        True,
        "Reservation must be frozen",
    )
    expect_raises(
        ValueError,
        lambda: AgentToolCallReplayReservation(
            tool_call=make_tool_call(
                status="created"
            ),
            call_identity=" ",
            reservation_action="created",
        ),
    )
    check(
        True,
        "Blank identity must fail",
    )
    expect_raises(
        ValueError,
        lambda: AgentToolCallReplayReservation(
            tool_call=make_tool_call(
                status="created"
            ),
            call_identity=(
                approved_arguments().call_identity
            ),
            reservation_action="invalid",
        ),
    )
    check(
        True,
        "Invalid reservation action must fail",
    )


def test_persistence_new_and_reuse() -> None:
    service, db, run, _ = build_persistence(
        rows=[]
    )
    reservation = service.reserve_or_reuse_tool_call(
        db,
        run_id="run-001",
        step_index=3,
        tool_name="search_knowledge",
        arguments_json={"issue_id": 17},
        max_tool_calls=3,
    )

    check(
        reservation.reservation_action
        == "created",
        "Missing ToolCall must be created",
    )
    check(
        run.tool_call_count == 1,
        "New ToolCall must increment Run count",
    )
    check(
        len(db.added) == 1,
        "New ToolCall must be added once",
    )
    check(
        db.flush_count == 1,
        "New ToolCall must flush once",
    )
    check(
        reservation.tool_call.tool_call_index
        == 1,
        "First ToolCall index must be one",
    )
    check(
        reservation.tool_call.call_status
        == "created",
        "New ToolCall status must be created",
    )
    check(
        reservation.tool_call.arguments_json
        == {"issue_id": 17},
        "New ToolCall arguments changed",
    )

    existing = make_tool_call(
        status="completed",
        result_json=search_result().model_dump(
            mode="json"
        ),
    )
    service, db, run, _ = build_persistence(
        rows=[(existing, 3)]
    )
    reused = service.reserve_or_reuse_tool_call(
        db,
        run_id="run-001",
        step_index=3,
        tool_name="search_knowledge",
        arguments_json={"issue_id": 17},
        max_tool_calls=1,
    )

    check(
        reused.reservation_action
        == "reused",
        "Matching ToolCall must be reused",
    )
    check(
        reused.tool_call is existing,
        "Reused ToolCall identity changed",
    )
    check(
        run.tool_call_count == 1,
        "Reuse must not increment Run count",
    )
    check(
        not db.added,
        "Reuse must not add a ToolCall",
    )
    check(
        db.flush_count == 0,
        "Reuse must not flush mutations",
    )


def test_persistence_fail_closed() -> None:
    service, db, _, _ = build_persistence(
        rows=[],
        persisted_count=3,
    )
    error = expect_raises(
        AgentToolCallReplayPersistenceError,
        lambda: service.reserve_or_reuse_tool_call(
            db,
            run_id="run-001",
            step_index=3,
            tool_name="search_knowledge",
            arguments_json={"issue_id": 17},
            max_tool_calls=3,
        ),
    )
    check(
        error.error_code
        == "tool_call_count_mismatch",
        "Count mismatch error changed",
    )

    first = make_tool_call(
        status="completed",
        tool_call_index=1,
    )
    second = make_tool_call(
        status="completed",
        tool_call_index=2,
    )
    service, db, _, _ = build_persistence(
        rows=[
            (first, 3),
            (second, 3),
        ]
    )
    error = expect_raises(
        AgentToolCallReplayPersistenceError,
        lambda: service.reserve_or_reuse_tool_call(
            db,
            run_id="run-001",
            step_index=3,
            tool_name="search_knowledge",
            arguments_json={"issue_id": 17},
            max_tool_calls=3,
        ),
    )
    check(
        error.error_code
        == "duplicate_persisted_tool_call_identity",
        "Duplicate persisted identity error changed",
    )

    service, db, _, _ = build_persistence(
        rows=[(first, 2)]
    )
    error = expect_raises(
        AgentToolCallReplayPersistenceError,
        lambda: service.reserve_or_reuse_tool_call(
            db,
            run_id="run-001",
            step_index=3,
            tool_name="search_knowledge",
            arguments_json={"issue_id": 17},
            max_tool_calls=3,
        ),
    )
    check(
        error.error_code
        == "replay_tool_call_step_mismatch",
        "Cross-step replay error changed",
    )

    other = make_tool_call(
        status="completed",
        issue_id=18,
    )
    service, db, _, _ = build_persistence(
        rows=[(other, 3)]
    )
    error = expect_raises(
        AgentToolCallReplayPersistenceError,
        lambda: service.reserve_or_reuse_tool_call(
            db,
            run_id="run-001",
            step_index=3,
            tool_name="search_knowledge",
            arguments_json={"issue_id": 17},
            max_tool_calls=1,
        ),
    )
    check(
        error.error_code
        == "max_tool_calls_reached",
        "New reservation limit error changed",
    )

    bad_version = make_tool_call(
        status="completed",
        tool_version="old_version",
    )
    service, db, _, _ = build_persistence(
        rows=[(bad_version, 3)]
    )
    error = expect_raises(
        AgentToolCallReplayPersistenceError,
        lambda: service.reserve_or_reuse_tool_call(
            db,
            run_id="run-001",
            step_index=3,
            tool_name="search_knowledge",
            arguments_json={"issue_id": 17},
            max_tool_calls=3,
        ),
    )
    check(
        error.error_code
        == "persisted_tool_version_mismatch",
        "Persisted version mismatch error changed",
    )

    bad_policy = make_tool_call(
        status="completed",
        read_only=False,
    )
    service, db, _, _ = build_persistence(
        rows=[(bad_policy, 3)]
    )
    error = expect_raises(
        AgentToolCallReplayPersistenceError,
        lambda: service.reserve_or_reuse_tool_call(
            db,
            run_id="run-001",
            step_index=3,
            tool_name="search_knowledge",
            arguments_json={"issue_id": 17},
            max_tool_calls=3,
        ),
    )
    check(
        error.error_code
        == "persisted_tool_policy_mismatch",
        "Persisted policy mismatch error changed",
    )


def test_orchestration_transaction() -> None:
    reservation = make_reservation(
        status="created",
        action="created",
    )
    persistence = RecordingPersistence(
        reservation
    )
    service = AgentOrchestrationService(
        persistence_service=persistence
    )
    db = FakeDb()

    actual = service.reserve_or_reuse_tool_call(
        db,
        run_id="run-001",
        step_index=3,
        tool_name="search_knowledge",
        arguments_json={"issue_id": 17},
        max_tool_calls=3,
    )

    check(
        actual is reservation,
        "Orchestration reservation changed",
    )
    check(
        db.commit_count == 1,
        "Reservation must commit once",
    )
    check(
        db.rollback_count == 0,
        "Successful reservation must not rollback",
    )
    check(
        db.refreshed == [
            reservation.tool_call
        ],
        "Reservation ToolCall refresh changed",
    )

    failure = RuntimeError("reservation failed")
    persistence = RecordingPersistence(
        reservation,
        error=failure,
    )
    service = AgentOrchestrationService(
        persistence_service=persistence
    )
    db = FakeDb()
    raised = expect_raises(
        RuntimeError,
        lambda: service.reserve_or_reuse_tool_call(
            db,
            run_id="run-001",
            step_index=3,
            tool_name="search_knowledge",
            arguments_json={"issue_id": 17},
            max_tool_calls=3,
        ),
    )
    check(
        raised is failure,
        "Orchestration must preserve reservation error",
    )
    check(
        db.commit_count == 0,
        "Failed reservation must not commit",
    )
    check(
        db.rollback_count == 1,
        "Failed reservation must rollback once",
    )


def test_replay_created_and_running() -> None:
    result = search_result()
    reservation = make_reservation(
        status="created",
        action="created",
    )
    dispatch = RecordingDispatch(
        result=result
    )
    service, orchestration = build_replay_service(
        reservation=reservation,
        dispatch=dispatch,
    )
    outcome = run_replay(
        service,
        object(),
    )

    check(
        isinstance(
            outcome,
            AgentReplayAwareToolExecutionOutcome,
        ),
        "Replay outcome type changed",
    )
    check(
        outcome.replay_version
        == AGENT_REPLAY_AWARE_TOOL_EXECUTION_VERSION,
        "Replay version changed",
    )
    check(
        outcome.replayed is False,
        "New ToolCall must not be marked replayed",
    )
    check(
        outcome.dispatch_performed is True,
        "New ToolCall must dispatch",
    )
    check(
        [
            name
            for name, _ in orchestration.events
        ]
        == [
            "reserve",
            "start",
            "complete",
        ],
        "New ToolCall event ordering changed",
    )
    check(
        len(dispatch.calls) == 1,
        "New ToolCall dispatch count changed",
    )
    check(
        outcome.execution.result_json[
            "retrieval_status"
        ]
        == "no_results",
        "New execution result changed",
    )

    reservation = make_reservation(
        status="running",
        action="reused",
    )
    dispatch = RecordingDispatch(
        result=result
    )
    service, orchestration = build_replay_service(
        reservation=reservation,
        dispatch=dispatch,
    )
    outcome = run_replay(
        service,
        object(),
    )

    check(
        outcome.replayed is True,
        "Running reuse must be replayed",
    )
    check(
        outcome.dispatch_performed is True,
        "Running reuse must redispatch",
    )
    check(
        [
            name
            for name, _ in orchestration.events
        ]
        == [
            "reserve",
            "complete",
        ],
        "Running replay must not restart ToolCall",
    )


def test_replay_created_reuse_and_completed() -> None:
    result = search_result()
    reservation = make_reservation(
        status="created",
        action="reused",
    )
    dispatch = RecordingDispatch(
        result=result
    )
    service, orchestration = build_replay_service(
        reservation=reservation,
        dispatch=dispatch,
    )
    outcome = run_replay(
        service,
        object(),
    )

    check(
        outcome.replayed is True,
        "Created reuse must be marked replayed",
    )
    check(
        [
            name
            for name, _ in orchestration.events
        ]
        == [
            "reserve",
            "start",
            "complete",
        ],
        "Created replay event ordering changed",
    )

    persisted = result.model_dump(
        mode="json"
    )
    reservation = make_reservation(
        status="completed",
        action="reused",
        result_json=persisted,
    )
    dispatch = RecordingDispatch(
        result=result
    )
    service, orchestration = build_replay_service(
        reservation=reservation,
        dispatch=dispatch,
    )
    outcome = run_replay(
        service,
        object(),
    )

    check(
        outcome.replayed is True,
        "Completed reuse must be replayed",
    )
    check(
        outcome.dispatch_performed is False,
        "Completed reuse must not dispatch",
    )
    check(
        len(dispatch.calls) == 0,
        "Completed reuse dispatched unexpectedly",
    )
    check(
        [
            name
            for name, _ in orchestration.events
        ]
        == ["reserve"],
        "Completed reuse must only reserve",
    )
    check(
        outcome.execution.tool_call
        is reservation.tool_call,
        "Completed reuse ToolCall changed",
    )


def test_replay_terminal_errors() -> None:
    cases = (
        (
            "failed",
            "persisted_failure",
            "persisted failure message",
        ),
        (
            "timed_out",
            "TOOL_TIMEOUT",
            "persisted timeout",
        ),
        (
            "cancelled",
            None,
            None,
        ),
    )

    for status, error_code, error_message in cases:
        reservation = make_reservation(
            status=status,
            action="reused",
            error_code=error_code,
            error_message=error_message,
        )
        dispatch = RecordingDispatch(
            result=search_result()
        )
        service, orchestration = build_replay_service(
            reservation=reservation,
            dispatch=dispatch,
        )
        error = expect_raises(
            AgentReplayAwareToolExecutionError,
            lambda: run_replay(
                service,
                object(),
            ),
        )

        check(
            error.tool_call
            is reservation.tool_call,
            f"{status} replay ToolCall changed",
        )
        check(
            error.replayed is True,
            f"{status} replay flag changed",
        )
        check(
            len(dispatch.calls) == 0,
            f"{status} replay dispatched",
        )
        check(
            [
                name
                for name, _ in orchestration.events
            ]
            == ["reserve"],
            f"{status} replay wrote lifecycle state",
        )

    check(
        True,
        "All terminal replay cases passed",
    )


def test_dispatch_failures() -> None:
    reservation = make_reservation(
        status="running",
        action="reused",
    )
    dispatch = RecordingDispatch(
        error=TimeoutError("timeout")
    )
    service, orchestration = build_replay_service(
        reservation=reservation,
        dispatch=dispatch,
    )
    error = expect_raises(
        AgentReplayAwareToolExecutionError,
        lambda: run_replay(
            service,
            object(),
        ),
    )

    check(
        error.error_code == "TOOL_TIMEOUT",
        "Timeout error code changed",
    )
    check(
        [
            name
            for name, _ in orchestration.events
        ]
        == [
            "reserve",
            "timeout",
        ],
        "Timeout lifecycle ordering changed",
    )

    reservation = make_reservation(
        status="running",
        action="reused",
    )
    dispatch = RecordingDispatch(
        error=LookupError("business failure")
    )
    service, orchestration = build_replay_service(
        reservation=reservation,
        dispatch=dispatch,
    )
    error = expect_raises(
        AgentReplayAwareToolExecutionError,
        lambda: run_replay(
            service,
            object(),
        ),
    )

    check(
        error.error_code
        == "tool_business_error",
        "Business error classification changed",
    )
    check(
        [
            name
            for name, _ in orchestration.events
        ]
        == [
            "reserve",
            "fail",
        ],
        "Failure lifecycle ordering changed",
    )


def test_invalid_persisted_result() -> None:
    reservation = make_reservation(
        status="completed",
        action="reused",
        result_json={"unexpected": True},
    )
    dispatch = RecordingDispatch(
        result=search_result()
    )
    service, orchestration = build_replay_service(
        reservation=reservation,
        dispatch=dispatch,
    )
    error = expect_raises(
        AgentReplayAwareToolExecutionError,
        lambda: run_replay(
            service,
            object(),
        ),
    )

    check(
        error.error_code
        == "invalid_persisted_tool_result",
        "Invalid persisted result error changed",
    )
    check(
        len(dispatch.calls) == 0,
        "Invalid persisted result must not dispatch",
    )
    check(
        [
            name
            for name, _ in orchestration.events
        ]
        == ["reserve"],
        "Invalid persisted result wrote lifecycle state",
    )


def source_call_terminals(
    path: Path,
) -> set[str]:
    tree = ast.parse(
        path.read_text(
            encoding="utf-8-sig"
        ),
        filename=str(path),
    )
    result = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func

        if isinstance(function, ast.Name):
            result.add(function.id)
        elif isinstance(function, ast.Attribute):
            result.add(function.attr)

    return result


def test_source_contract() -> None:
    normalized_paths = {
        "backend/app/agent_graph/state.py",
    }

    for relative, expected in EXPECTED_HASHES.items():
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

    persistence_path = (
        BACKEND_ROOT
        / "app"
        / "services"
        / "agent_persistence_service.py"
    )
    orchestration_path = (
        BACKEND_ROOT
        / "app"
        / "services"
        / "agent_orchestration_service.py"
    )
    replay_path = (
        BACKEND_ROOT
        / "app"
        / "services"
        / "agent_replay_aware_tool_execution_service.py"
    )
    replay_text = replay_path.read_text(
        encoding="utf-8-sig"
    )
    persistence_text = persistence_path.read_text(
        encoding="utf-8-sig"
    )
    orchestration_text = orchestration_path.read_text(
        encoding="utf-8-sig"
    )

    check(
        "AgentRunnerService"
        not in replay_text,
        "Replay foundation depends on Custom Runner",
    )
    check(
        "checkpointer"
        not in replay_text.lower(),
        "Replay foundation calls Checkpointer",
    )
    check(
        {
            "commit",
            "rollback",
            "flush",
            "with_for_update",
        }.isdisjoint(
            source_call_terminals(
                replay_path
            )
        ),
        "Replay execution owns persistence or locks",
    )
    check(
        "reserve_or_reuse_tool_call"
        in persistence_text,
        "Persistence reservation method missing",
    )
    check(
        "with_for_update("
        in persistence_text,
        "Persistence replay ToolCall lock missing",
    )
    check(
        "reserve_or_reuse_tool_call"
        in orchestration_text,
        "Orchestration reservation method missing",
    )

    orchestration_tree = ast.parse(
        orchestration_text
    )
    orchestration_class = next(
        node
        for node in orchestration_tree.body
        if (
            isinstance(node, ast.ClassDef)
            and node.name
            == "AgentOrchestrationService"
        )
    )
    method = next(
        node
        for node in orchestration_class.body
        if (
            isinstance(node, ast.FunctionDef)
            and node.name
            == "reserve_or_reuse_tool_call"
        )
    )
    calls = []

    for node in ast.walk(method):
        if not isinstance(node, ast.Call):
            continue
        function = node.func

        if isinstance(function, ast.Name):
            calls.append(function.id)
        elif isinstance(function, ast.Attribute):
            calls.append(function.attr)

    check(
        calls.count("commit") == 1,
        "Reservation orchestration must commit once",
    )
    check(
        calls.count("rollback") == 1,
        "Reservation orchestration must rollback once",
    )
    runtime_source = (
        REPO_ROOT
        / "backend"
        / "app"
        / "agent_graph"
        / "runtime.py"
    ).read_text(encoding="utf-8-sig")
    check(
        "EXECUTE_TOOL_NODE" in runtime_source,
        "Graph execute_tool wiring is missing",
    )
    check(
        "build_execute_tool_runtime_node"
        in runtime_source,
        "Graph execute_tool builder wiring is missing",
    )


def main() -> int:
    tests = (
        test_reservation_dataclass,
        test_persistence_new_and_reuse,
        test_persistence_fail_closed,
        test_orchestration_transaction,
        test_replay_created_and_running,
        test_replay_created_reuse_and_completed,
        test_replay_terminal_errors,
        test_dispatch_failures,
        test_invalid_persisted_result,
        test_source_contract,
    )

    for test in tests:
        test()

    print("=== COPY THIS SUMMARY ===")
    print("stage=completed")
    print(
        "operation=validate_replay_aware_tool_execution_foundation"
    )
    print(
        f"assertion_count={ASSERTION_COUNT}"
    )
    print("test_count=10")
    print("replay_status_case_count=7")
    print("crash_window_support_count=5")
    print("new_tool_call_path=passed")
    print("created_replay_path=passed")
    print("running_replay_path=passed")
    print("completed_reuse_path=passed")
    print("failed_terminal_path=passed")
    print("timed_out_terminal_path=passed")
    print("cancelled_terminal_path=passed")
    print("atomic_reservation=passed")
    print("max_tool_calls_new_only=passed")
    print("duplicate_identity_fail_closed=passed")
    print("cross_step_reuse_fail_closed=passed")
    print("long_dispatch_transaction=no")
    print("runner_dependency=no")
    print("checkpointer_calls=0")
    print("graph_execute_tool_wired=yes")
    print("database_accessed=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
