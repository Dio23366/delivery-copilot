from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from types import SimpleNamespace

from app.services.agent_orchestration_service import (
    AgentOrchestrationService,
)
from app.services.agent_persistence_service import (
    AgentPersistenceService,
)


FIXED_COMPLETED_AT = datetime(
    2026,
    7,
    26,
    10,
    0,
    0,
)
FIXED_NEXT_STARTED_AT = datetime(
    2026,
    7,
    26,
    10,
    0,
    1,
)


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self.refreshed: list[object] = []

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


def build_persistence_fixture(
    *,
    run_status: str = "running",
    current_node: str = "load_issue",
    step_count: int = 1,
    step_status: str = "running",
    step_node: str = "load_issue",
):
    service = AgentPersistenceService.__new__(
        AgentPersistenceService
    )
    db = FakeSession()

    agent_run = SimpleNamespace(
        id=101,
        run_id="run-001",
        run_status=run_status,
        current_node=current_node,
        state_json={"issue_id": 17},
        step_count=step_count,
        waiting_since=None,
        resume_node=None,
        error_code=None,
        error_message=None,
        completed_at=None,
    )

    current_step = SimpleNamespace(
        id=201,
        agent_run_id=101,
        step_index=1,
        node_name=step_node,
        step_status=step_status,
        input_state_json={"issue_id": 17},
        output_state_json=None,
        error_code=None,
        error_message=None,
        started_at=FIXED_COMPLETED_AT,
        completed_at=None,
    )

    service.lock_run_by_run_id = (
        lambda received_db, run_id: agent_run
    )
    service.lock_step_by_run_and_index = (
        lambda received_db,
        *,
        agent_run_id,
        step_index: current_step
    )

    return service, db, agent_run, current_step


def assert_value_error(
    callback: Callable[[], object],
    expected_text: str,
) -> None:
    try:
        callback()
    except ValueError as exc:
        assert expected_text in str(exc)
        return

    raise AssertionError(
        "Expected ValueError containing: "
        + expected_text
    )


def test_persistence_success() -> None:
    (
        service,
        db,
        agent_run,
        current_step,
    ) = build_persistence_fixture()

    state = {
        "issue_id": 17,
        "current_node": "triage_issue",
        "issue_context": {
            "title": "Authentication failure",
        },
    }

    (
        returned_run,
        returned_completed_step,
        next_step,
    ) = service.complete_step_and_advance_run(
        db,
        run_id="run-001",
        step_index=1,
        next_node="triage_issue",
        state_json=state,
        completed_at=FIXED_COMPLETED_AT,
        next_started_at=FIXED_NEXT_STARTED_AT,
    )

    assert returned_run is agent_run
    assert returned_completed_step is current_step
    assert current_step.step_status == "completed"
    assert current_step.output_state_json == state
    assert (
        current_step.completed_at
        == FIXED_COMPLETED_AT
    )

    assert agent_run.current_node == "triage_issue"
    assert agent_run.state_json == state
    assert agent_run.step_count == 2

    assert next_step.step_index == 2
    assert next_step.node_name == "triage_issue"
    assert next_step.step_status == "running"
    assert next_step.input_state_json == state
    assert (
        next_step.started_at
        == FIXED_NEXT_STARTED_AT
    )

    assert db.added == [next_step]
    assert db.flush_count == 1


def test_blank_next_node_is_rejected() -> None:
    service, db, _, _ = build_persistence_fixture()

    assert_value_error(
        lambda: service.complete_step_and_advance_run(
            db,
            run_id="run-001",
            step_index=1,
            next_node="   ",
            state_json={},
        ),
        "must be nonblank",
    )


def test_run_must_be_running() -> None:
    service, db, _, _ = build_persistence_fixture(
        run_status=(
            "waiting_for_triage_confirmation"
        )
    )

    assert_value_error(
        lambda: service.complete_step_and_advance_run(
            db,
            run_id="run-001",
            step_index=1,
            next_node="triage_issue",
            state_json={},
        ),
        "cannot advance from status",
    )


def test_current_step_must_be_latest() -> None:
    service, db, _, _ = build_persistence_fixture(
        step_count=2
    )

    assert_value_error(
        lambda: service.complete_step_and_advance_run(
            db,
            run_id="run-001",
            step_index=1,
            next_node="triage_issue",
            state_json={},
        ),
        "latest Agent step",
    )


def test_step_must_be_running() -> None:
    service, db, _, _ = build_persistence_fixture(
        step_status="completed"
    )

    assert_value_error(
        lambda: service.complete_step_and_advance_run(
            db,
            run_id="run-001",
            step_index=1,
            next_node="triage_issue",
            state_json={},
        ),
        "Agent step cannot advance",
    )


def test_step_node_must_match_run() -> None:
    service, db, _, _ = build_persistence_fixture(
        step_node="triage_issue"
    )

    assert_value_error(
        lambda: service.complete_step_and_advance_run(
            db,
            run_id="run-001",
            step_index=1,
            next_node="triage_issue",
            state_json={},
        ),
        "node mismatch",
    )


class SuccessfulPersistence:
    def __init__(self) -> None:
        self.calls = 0

    def complete_step_and_advance_run(
        self,
        db,
        **kwargs,
    ):
        self.calls += 1

        return (
            SimpleNamespace(name="run"),
            SimpleNamespace(name="completed"),
            SimpleNamespace(name="next"),
        )


class FailingPersistence:
    def complete_step_and_advance_run(
        self,
        db,
        **kwargs,
    ):
        raise RuntimeError("controlled failure")


def test_orchestration_success_commits() -> None:
    persistence = SuccessfulPersistence()
    service = AgentOrchestrationService.__new__(
        AgentOrchestrationService
    )
    service._persistence_service = persistence
    db = FakeSession()

    values = service.complete_step_and_advance_run(
        db,
        run_id="run-001",
        step_index=1,
        next_node="triage_issue",
        state_json={"issue_id": 17},
    )

    assert len(values) == 3
    assert persistence.calls == 1
    assert db.commit_count == 1
    assert db.rollback_count == 0
    assert len(db.refreshed) == 3


def test_orchestration_failure_rolls_back() -> None:
    service = AgentOrchestrationService.__new__(
        AgentOrchestrationService
    )
    service._persistence_service = (
        FailingPersistence()
    )
    db = FakeSession()

    try:
        service.complete_step_and_advance_run(
            db,
            run_id="run-001",
            step_index=1,
            next_node="triage_issue",
            state_json={"issue_id": 17},
        )
    except RuntimeError as exc:
        assert str(exc) == "controlled failure"
    else:
        raise AssertionError(
            "Expected controlled failure"
        )

    assert db.commit_count == 0
    assert db.rollback_count == 1
    assert db.refreshed == []


TESTS: tuple[Callable[[], None], ...] = (
    test_persistence_success,
    test_blank_next_node_is_rejected,
    test_run_must_be_running,
    test_current_step_must_be_latest,
    test_step_must_be_running,
    test_step_node_must_match_run,
    test_orchestration_success_commits,
    test_orchestration_failure_rolls_back,
)


def main() -> None:
    for test in TESTS:
        test()
        print(f"passed={test.__name__}")

    print(f"validator_test_count={len(TESTS)}")
    print(
        "atomic_transition="
        "complete_step+save_state+"
        "advance_run+append_step"
    )
    print(
        "agent_step_advance_stub_validation=passed"
    )


if __name__ == "__main__":
    main()
