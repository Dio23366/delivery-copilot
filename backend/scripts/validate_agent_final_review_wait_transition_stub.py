from __future__ import annotations

import ast
from copy import deepcopy
from datetime import datetime
import inspect
from pathlib import Path
import sys
import textwrap
from types import SimpleNamespace
from unittest.mock import Mock


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.services.agent_orchestration_service import (  # noqa: E402
    AgentOrchestrationService,
)
from app.services.agent_persistence_service import (  # noqa: E402
    AGENT_FINAL_REVIEW_WAIT_VERSION,
    AWAIT_FINAL_REVIEW_NODE,
    FINALIZE_RUN_NODE,
    FINAL_REVIEW_NODE,
    WAITING_FOR_FINAL_REVIEW_STATUS,
    AgentPersistenceService,
)


INTERRUPTED_AT = datetime(2026, 7, 28, 15, 0, 0)
STARTED_AT = datetime(2026, 7, 28, 14, 59, 0)


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self.refreshed: list[object] = []
        self.events: list[str] = []

    def add(self, value: object) -> None:
        self.added.append(value)
        self.events.append(
            f"add:{getattr(value, 'node_name', type(value).__name__)}"
        )

    def flush(self) -> None:
        self.flush_count += 1
        self.events.append("flush")

    def commit(self) -> None:
        self.commit_count += 1
        self.events.append("commit")

    def rollback(self) -> None:
        self.rollback_count += 1
        self.events.append("rollback")

    def refresh(self, value: object) -> None:
        self.refreshed.append(value)
        self.events.append(
            f"refresh:{getattr(value, 'node_name', type(value).__name__)}"
        )


def state() -> dict[str, object]:
    return {
        "issue_id": 17,
        "analysis_log_id": 68,
        "pending_approval": True,
        "generated_analysis": {
            "generation_version": (
                "agent_analysis_generation_v0.1"
            ),
        },
    }


def fixture():
    current_state = state()
    run = SimpleNamespace(
        id=101,
        run_id="run-final-review-101",
        issue_id=17,
        analysis_log_id=68,
        run_status="generating_analysis",
        current_node=FINAL_REVIEW_NODE,
        state_json=deepcopy(current_state),
        step_count=7,
        waiting_since=None,
        resume_node=None,
        error_code="STALE",
        error_message="stale",
        completed_at=None,
    )
    step = SimpleNamespace(
        id=707,
        agent_run_id=101,
        step_index=7,
        node_name=FINAL_REVIEW_NODE,
        step_status="running",
        input_state_json=deepcopy(current_state),
        output_state_json=None,
        error_code="STALE_STEP",
        error_message="stale step",
        started_at=STARTED_AT,
        completed_at=None,
    )
    db = FakeSession()
    events: list[str] = []
    service = AgentPersistenceService.__new__(
        AgentPersistenceService
    )

    def lock_run(*args, **kwargs):
        events.append("lock_run")
        return run

    def lock_step(*args, **kwargs):
        events.append("lock_step")
        return step

    service.lock_run_by_run_id = Mock(
        side_effect=lock_run
    )
    service.lock_step_by_run_and_index = Mock(
        side_effect=lock_step
    )
    return service, db, run, step, current_state, events


def synchronize_step(
    service: AgentPersistenceService,
    run: SimpleNamespace,
    step: SimpleNamespace,
) -> None:
    step.input_state_json = deepcopy(run.state_json)
    service.lock_step_by_run_and_index.side_effect = (
        lambda *args, **kwargs: step
    )


def call(
    service: AgentPersistenceService,
    db: FakeSession,
):
    return service.complete_final_review_and_wait_run(
        db,
        run_id="run-final-review-101",
        step_index=7,
        interrupted_at=INTERRUPTED_AT,
    )


def assert_raises(
    expected: type[BaseException],
    fragment: str,
    callback,
) -> None:
    try:
        callback()
    except expected as exc:
        assert fragment in str(exc)
        return
    raise AssertionError(
        f"Expected {expected.__name__}: {fragment}"
    )


def test_successful_atomic_wait_transition() -> None:
    service, db, run, step, original, events = fixture()
    result_run, completed_step, await_step = call(
        service,
        db,
    )

    assert result_run is run
    assert completed_step is step
    assert events == ["lock_run", "lock_step"]
    assert step.step_status == "completed"
    assert step.completed_at == INTERRUPTED_AT
    assert step.error_code is None
    assert step.error_message is None

    expected_receipt = {
        "final_review_wait_version": (
            AGENT_FINAL_REVIEW_WAIT_VERSION
        ),
        "analysis_log_id": 68,
        "pending_approval": True,
        "completed_node": FINAL_REVIEW_NODE,
        "waiting_node": AWAIT_FINAL_REVIEW_NODE,
        "resume_node": FINALIZE_RUN_NODE,
    }
    assert step.output_state_json == expected_receipt
    assert await_step.step_index == 8
    assert await_step.node_name == AWAIT_FINAL_REVIEW_NODE
    assert await_step.step_status == "interrupted"
    assert await_step.input_state_json == original
    assert await_step.output_state_json == expected_receipt
    assert await_step.started_at == INTERRUPTED_AT
    assert await_step.completed_at == INTERRUPTED_AT

    assert run.run_status == WAITING_FOR_FINAL_REVIEW_STATUS
    assert run.current_node == AWAIT_FINAL_REVIEW_NODE
    assert run.state_json == original
    assert run.step_count == 8
    assert run.waiting_since == INTERRUPTED_AT
    assert run.resume_node == FINALIZE_RUN_NODE
    assert run.error_code is None
    assert run.error_message is None
    assert run.completed_at is None

    assert db.added == [await_step]
    assert db.flush_count == 1
    assert db.commit_count == 0
    assert db.rollback_count == 0


def test_lock_order_and_single_step_creation() -> None:
    service, db, _, _, _, events = fixture()
    _, _, await_step = call(service, db)
    assert events == ["lock_run", "lock_step"]
    assert db.added == [await_step]
    assert db.events == [
        f"add:{AWAIT_FINAL_REVIEW_NODE}",
        "flush",
    ]


def test_missing_run_and_step_rejected() -> None:
    service, db, _, _, _, _ = fixture()
    service.lock_run_by_run_id.side_effect = None
    service.lock_run_by_run_id.return_value = None
    assert_raises(
        LookupError,
        "Agent run not found",
        lambda: call(service, db),
    )

    service, db, _, _, _, _ = fixture()
    service.lock_step_by_run_and_index.side_effect = None
    service.lock_step_by_run_and_index.return_value = None
    assert_raises(
        LookupError,
        "Final review Agent step not found",
        lambda: call(service, db),
    )


def test_run_status_and_node_rejected() -> None:
    service, db, run, _, _, _ = fixture()
    run.run_status = "running"
    assert_raises(
        ValueError,
        "cannot enter final review wait",
        lambda: call(service, db),
    )

    service, db, run, _, _, _ = fixture()
    run.current_node = "persist_analysis"
    assert_raises(
        ValueError,
        "unexpected final review node",
        lambda: call(service, db),
    )


def test_latest_step_index_rejected() -> None:
    service, db, run, _, _, _ = fixture()
    run.step_count = 8
    assert_raises(
        ValueError,
        "Only the latest Agent step",
        lambda: call(service, db),
    )


def test_analysis_link_contracts() -> None:
    for value in (None, True, 0, -1, "68"):
        service, db, run, _, _, _ = fixture()
        run.analysis_log_id = value
        assert_raises(
            ValueError,
            "positive analysis_log_id",
            lambda service=service, db=db: call(
                service,
                db,
            ),
        )


def test_step_node_and_status_rejected() -> None:
    service, db, _, step, _, _ = fixture()
    step.node_name = AWAIT_FINAL_REVIEW_NODE
    assert_raises(
        ValueError,
        "not final_review",
        lambda: call(service, db),
    )

    service, db, _, step, _, _ = fixture()
    step.step_status = "completed"
    assert_raises(
        ValueError,
        "must be running",
        lambda: call(service, db),
    )


def test_step_state_snapshot_contracts() -> None:
    service, db, _, step, _, _ = fixture()
    step.input_state_json = []
    assert_raises(
        ValueError,
        "must be a mapping",
        lambda: call(service, db),
    )

    service, db, _, step, _, _ = fixture()
    step.input_state_json["issue_id"] = 999
    assert_raises(
        ValueError,
        "does not match Agent Run state",
        lambda: call(service, db),
    )


def test_state_analysis_link_must_match() -> None:
    service, db, run, step, _, _ = fixture()
    run.state_json["analysis_log_id"] = 69
    synchronize_step(service, run, step)
    assert_raises(
        ValueError,
        "does not match Agent Run analysis link",
        lambda: call(service, db),
    )


def test_pending_approval_required() -> None:
    for value in (False, None, 1, "true"):
        service, db, run, step, _, _ = fixture()
        run.state_json["pending_approval"] = value
        synchronize_step(service, run, step)
        assert_raises(
            ValueError,
            "must require pending approval",
            lambda service=service, db=db: call(
                service,
                db,
            ),
        )


def test_generated_analysis_must_be_retained() -> None:
    service, db, run, step, _, _ = fixture()
    run.state_json["generated_analysis"] = None
    synchronize_step(service, run, step)
    assert_raises(
        ValueError,
        "must retain generated_analysis",
        lambda: call(service, db),
    )


def test_stale_waiting_metadata_rejected() -> None:
    service, db, run, _, _, _ = fixture()
    run.waiting_since = INTERRUPTED_AT
    assert_raises(
        ValueError,
        "cannot already be waiting",
        lambda: call(service, db),
    )

    service, db, run, _, _, _ = fixture()
    run.resume_node = FINALIZE_RUN_NODE
    assert_raises(
        ValueError,
        "cannot have a resume_node",
        lambda: call(service, db),
    )


def test_time_order_rejected() -> None:
    service, db, _, step, _, _ = fixture()
    step.started_at = datetime(2026, 7, 28, 16, 0, 0)
    assert_raises(
        ValueError,
        "cannot precede final_review start time",
        lambda: call(service, db),
    )


def test_orchestration_commit_and_refresh() -> None:
    persistence = Mock()
    fixture_result = fixture()
    returned_objects = (
        fixture_result[2],
        fixture_result[3],
        SimpleNamespace(
            node_name=AWAIT_FINAL_REVIEW_NODE,
        ),
    )
    persistence.complete_final_review_and_wait_run.return_value = (
        returned_objects
    )
    orchestration = AgentOrchestrationService(
        persistence_service=persistence,
    )
    db = FakeSession()

    returned = orchestration.complete_final_review_and_wait_run(
        db,
        run_id="run-final-review-101",
        step_index=7,
        interrupted_at=INTERRUPTED_AT,
    )

    assert returned == returned_objects
    persistence.complete_final_review_and_wait_run.assert_called_once_with(
        db,
        run_id="run-final-review-101",
        step_index=7,
        interrupted_at=INTERRUPTED_AT,
    )
    assert db.commit_count == 1
    assert db.rollback_count == 0
    assert len(db.refreshed) == 3


def test_orchestration_rolls_back() -> None:
    persistence = Mock()
    persistence.complete_final_review_and_wait_run.side_effect = (
        RuntimeError("boom")
    )
    orchestration = AgentOrchestrationService(
        persistence_service=persistence,
    )
    db = FakeSession()

    assert_raises(
        RuntimeError,
        "boom",
        lambda: orchestration.complete_final_review_and_wait_run(
            db,
            run_id="run-final-review-101",
            step_index=7,
        ),
    )
    assert db.commit_count == 0
    assert db.rollback_count == 1
    assert not db.refreshed


def test_persistence_source_contract() -> None:
    source = inspect.getsource(
        AgentPersistenceService
        .complete_final_review_and_wait_run
    )
    tree = ast.parse(textwrap.dedent(source))
    calls: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        parts: list[str] = []
        current = node.func
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            calls.append(
                ".".join(reversed(parts))
            )

    assert calls.count(
        "self.lock_run_by_run_id"
    ) == 1
    assert calls.count(
        "self.lock_step_by_run_and_index"
    ) == 1
    assert calls.count("db.add") == 1
    assert calls.count("db.flush") == 1
    assert "db.commit" not in calls
    assert "db.rollback" not in calls
    assert "db.refresh" not in calls
    assert "AIAnalysisLog" not in source


def test_orchestration_source_contract() -> None:
    source = inspect.getsource(
        AgentOrchestrationService
        .complete_final_review_and_wait_run
    )
    tree = ast.parse(textwrap.dedent(source))
    calls: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        parts: list[str] = []
        current = node.func
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            calls.append(
                ".".join(reversed(parts))
            )

    target = (
        "self._persistence_service."
        "complete_final_review_and_wait_run"
    )
    assert calls.count(target) == 1
    assert calls.count("db.commit") == 1
    assert calls.count("db.rollback") == 1
    assert calls.count("db.refresh") == 3
    assert "db.add" not in calls
    assert "db.flush" not in calls


def test_contract_constants() -> None:
    assert AGENT_FINAL_REVIEW_WAIT_VERSION == (
        "agent_final_review_wait_v0.1"
    )
    assert FINAL_REVIEW_NODE == "final_review"
    assert AWAIT_FINAL_REVIEW_NODE == "await_final_review"
    assert WAITING_FOR_FINAL_REVIEW_STATUS == (
        "waiting_for_final_review"
    )
    assert FINALIZE_RUN_NODE == "finalize_run"


TESTS = (
    test_successful_atomic_wait_transition,
    test_lock_order_and_single_step_creation,
    test_missing_run_and_step_rejected,
    test_run_status_and_node_rejected,
    test_latest_step_index_rejected,
    test_analysis_link_contracts,
    test_step_node_and_status_rejected,
    test_step_state_snapshot_contracts,
    test_state_analysis_link_must_match,
    test_pending_approval_required,
    test_generated_analysis_must_be_retained,
    test_stale_waiting_metadata_rejected,
    test_time_order_rejected,
    test_orchestration_commit_and_refresh,
    test_orchestration_rolls_back,
    test_persistence_source_contract,
    test_orchestration_source_contract,
    test_contract_constants,
)


def main() -> None:
    for test in TESTS:
        test()

    print(
        "Agent final review wait transition assertions passed "
        f"{len(TESTS)}/{len(TESTS)}"
    )


if __name__ == "__main__":
    main()
