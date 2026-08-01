from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import inspect
import sys
from typing import Callable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.agent_clarification_request_service import (
    AGENT_CLARIFICATION_REQUEST_VERSION,
    WAITING_FOR_CLARIFICATION_STATUS,
    AgentClarificationRequest,
    AgentClarificationRequestError,
)
from app.services.agent_evidence_evaluation_service import (
    REQUEST_CLARIFICATION_NODE,
)
from app.services.agent_runner_service import (
    AGENT_RUNNER_REQUEST_CLARIFICATION_VERSION,
    AgentRunnerRequestClarificationResult,
    AgentRunnerService,
)


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


def base_state() -> dict[str, object]:
    return {
        "issue_id": 17,
        "issue_title": (
            "API authentication fails after token rotation"
        ),
        "issue_description": (
            "Requests return 401 after credentials changed."
        ),
        "issue_type": "API",
        "severity": "high",
        "status": "investigating",
        "project_name": "Enterprise API Rollout",
        "delivery_stage": "Implementation",
        "triage_confirmed": True,
        "selected_tool": None,
        "tool_results": [
            {
                "tool_name": "search_knowledge",
                "tool_version": "grounded_retrieval_v1",
                "call_identity": (
                    "search_knowledge:"
                    f"{'a' * 64}"
                ),
                "arguments": {"issue_id": 17},
                "result_json": {
                    "retrieval_status": "no_results"
                },
                "execution_status": "completed",
            }
        ],
        "retrieved_evidence": [],
        "evidence_sufficient": False,
        "evidence_reason": (
            "Approved Tool evidence is insufficient."
        ),
    }


def request() -> AgentClarificationRequest:
    return AgentClarificationRequest(
        clarification_question=(
            "Please provide the authentication method, "
            "the latest token-change timestamp, and the "
            "original error response."
        ),
        evidence_reason=(
            "Approved Tool evidence is insufficient."
        ),
    )


class RecordingClarificationService:
    def __init__(
        self,
        *,
        clarification_request: (
            AgentClarificationRequest | None
        ) = None,
        error: Exception | None = None,
        return_value: object | None = None,
    ) -> None:
        self.clarification_request = (
            clarification_request
            if clarification_request is not None
            else request()
        )
        self.error = error
        self.return_value = return_value
        self.states: list[dict[str, object]] = []

    def create_request(
        self,
        state: object,
    ) -> object:
        self.states.append(dict(state))
        if self.error is not None:
            raise self.error
        if self.return_value is not None:
            return self.return_value
        return self.clarification_request


class RecordingOrchestrationService:
    def __init__(self) -> None:
        self.calls: list[
            tuple[str, dict[str, object]]
        ] = []

    def interrupt_step_and_wait_run(
        self,
        db: object,
        **kwargs: object,
    ) -> tuple[object, object]:
        self.calls.append(
            (
                "interrupt_step_and_wait_run",
                {"db": db, **dict(kwargs)},
            )
        )
        waiting_run = SimpleNamespace(
            run_id=kwargs["run_id"],
            run_status=kwargs["waiting_status"],
            current_node=REQUEST_CLARIFICATION_NODE,
            resume_node="route_investigation",
            step_count=kwargs["step_index"],
            state_json=dict(kwargs["state_json"]),
        )
        interrupted_step = SimpleNamespace(
            step_index=kwargs["step_index"],
            node_name=REQUEST_CLARIFICATION_NODE,
            step_status="interrupted",
            output_state_json=dict(
                kwargs["output_state_json"]
            ),
        )
        return waiting_run, interrupted_step

    def fail_step(
        self,
        db: object,
        **kwargs: object,
    ) -> object:
        self.calls.append(
            (
                "fail_step",
                {"db": db, **dict(kwargs)},
            )
        )
        return SimpleNamespace(
            step_index=kwargs["step_index"],
            node_name=REQUEST_CLARIFICATION_NODE,
            step_status="failed",
            error_code=kwargs["error_code"],
        )


def make_run(
    *,
    run_status: str = "running",
    current_node: str = REQUEST_CLARIFICATION_NODE,
    step_count: int = 8,
    state_json: dict[str, object] | None = None,
) -> object:
    return SimpleNamespace(
        run_id="run-001",
        run_status=run_status,
        current_node=current_node,
        step_count=step_count,
        state_json=(
            dict(state_json)
            if state_json is not None
            else base_state()
        ),
    )


def make_step(
    *,
    step_index: int = 8,
    node_name: str = REQUEST_CLARIFICATION_NODE,
    step_status: str = "running",
    input_state_json: dict[str, object] | None = None,
) -> object:
    return SimpleNamespace(
        step_index=step_index,
        node_name=node_name,
        step_status=step_status,
        input_state_json=(
            dict(input_state_json)
            if input_state_json is not None
            else base_state()
        ),
    )


def build_runner(
    *,
    clarification_request: (
        AgentClarificationRequest | None
    ) = None,
    error: Exception | None = None,
    return_value: object | None = None,
) -> tuple[
    AgentRunnerService,
    RecordingClarificationService,
    RecordingOrchestrationService,
]:
    clarification = RecordingClarificationService(
        clarification_request=clarification_request,
        error=error,
        return_value=return_value,
    )
    orchestration = RecordingOrchestrationService()
    runner = AgentRunnerService(
        orchestration_service=orchestration,
        clarification_request_service=clarification,
    )
    return runner, clarification, orchestration


def call(
    runner: AgentRunnerService,
    *,
    db: object | None = None,
    agent_run: object | None = None,
    request_step: object | None = None,
) -> AgentRunnerRequestClarificationResult:
    return runner.advance_request_clarification(
        db if db is not None else object(),
        agent_run=(
            agent_run
            if agent_run is not None
            else make_run()
        ),
        request_clarification_step=(
            request_step
            if request_step is not None
            else make_step()
        ),
    )


def test_version_and_node_are_frozen() -> None:
    assert AGENT_RUNNER_REQUEST_CLARIFICATION_VERSION == (
        "agent_runner_request_clarification_v0.1"
    )
    assert REQUEST_CLARIFICATION_NODE == (
        "request_clarification"
    )
    assert WAITING_FOR_CLARIFICATION_STATUS == (
        "waiting_for_clarification"
    )
    print("PASS: Runner clarification contract is frozen")


def test_success_interrupts_and_waits() -> None:
    runner, clarification, orchestration = (
        build_runner()
    )
    db = object()

    result = call(runner, db=db)

    assert isinstance(
        result,
        AgentRunnerRequestClarificationResult,
    )
    assert result.agent_run.run_status == (
        WAITING_FOR_CLARIFICATION_STATUS
    )
    assert result.agent_run.resume_node == (
        "route_investigation"
    )
    assert result.request_clarification_step.step_status == (
        "interrupted"
    )
    assert len(clarification.states) == 1
    assert len(orchestration.calls) == 1
    assert orchestration.calls[0][1]["db"] is db
    print("PASS: request_clarification interrupts and waits")


def test_waiting_call_uses_frozen_status() -> None:
    runner, _, orchestration = build_runner()

    call(runner)

    name, payload = orchestration.calls[0]
    assert name == "interrupt_step_and_wait_run"
    assert payload["waiting_status"] == (
        WAITING_FOR_CLARIFICATION_STATUS
    )
    assert payload["run_id"] == "run-001"
    assert payload["step_index"] == 8
    print("PASS: waiting call uses frozen status")


def test_state_update_is_controlled() -> None:
    clarification_request = request()
    runner, _, orchestration = build_runner(
        clarification_request=clarification_request
    )
    state = base_state()
    state["preserved_value"] = "keep-me"

    result = call(
        runner,
        agent_run=make_run(state_json=state),
        request_step=make_step(
            input_state_json=state
        ),
    )

    assert result.state_json["preserved_value"] == (
        "keep-me"
    )
    assert result.state_json[
        "clarification_question"
    ] == clarification_request.clarification_question
    assert result.state_json[
        "clarification_response"
    ] is None

    payload = orchestration.calls[0][1]
    assert payload["state_json"] == result.state_json
    assert payload["output_state_json"] == (
        clarification_request.as_dict()
    )
    print("PASS: clarification state update is controlled")


def test_original_state_is_not_mutated() -> None:
    runner, _, _ = build_runner()
    state = base_state()

    result = call(
        runner,
        agent_run=make_run(state_json=state),
        request_step=make_step(
            input_state_json=state
        ),
    )

    assert "clarification_question" not in state
    assert "clarification_response" not in state
    assert result.state_json[
        "clarification_response"
    ] is None
    print("PASS: original Agent state is not mutated")


def test_result_preserves_waiting_objects() -> None:
    runner, _, _ = build_runner()

    result = call(runner)

    assert result.request_clarification_step.step_status == (
        "interrupted"
    )
    assert result.clarification_request == request()
    assert result.agent_run.run_status == (
        WAITING_FOR_CLARIFICATION_STATUS
    )
    print("PASS: result preserves waiting objects")


def test_invalid_run_status_is_rejected() -> None:
    runner, clarification, orchestration = (
        build_runner()
    )

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            agent_run=make_run(
                run_status=(
                    WAITING_FOR_CLARIFICATION_STATUS
                )
            ),
        ),
    )

    assert "status" in str(error)
    assert clarification.states == []
    assert orchestration.calls == []
    print("PASS: invalid Run status is rejected")


def test_invalid_current_node_is_rejected() -> None:
    runner, clarification, orchestration = (
        build_runner()
    )

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            agent_run=make_run(
                current_node="evaluate_evidence"
            ),
        ),
    )

    assert "current node" in str(error)
    assert clarification.states == []
    assert orchestration.calls == []
    print("PASS: invalid current node is rejected")


def test_invalid_step_node_is_rejected() -> None:
    runner, clarification, orchestration = (
        build_runner()
    )

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            request_step=make_step(
                node_name="evaluate_evidence"
            ),
        ),
    )

    assert "clarification node" in str(error)
    assert clarification.states == []
    assert orchestration.calls == []
    print("PASS: invalid Step node is rejected")


def test_non_running_step_is_rejected() -> None:
    runner, clarification, orchestration = (
        build_runner()
    )

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            request_step=make_step(
                step_status="completed"
            ),
        ),
    )

    assert "must be running" in str(error)
    assert clarification.states == []
    assert orchestration.calls == []
    print("PASS: non-running Step is rejected")


def test_step_index_mismatch_is_rejected() -> None:
    runner, clarification, orchestration = (
        build_runner()
    )

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            agent_run=make_run(step_count=9),
            request_step=make_step(step_index=8),
        ),
    )

    assert "latest Step" in str(error)
    assert clarification.states == []
    assert orchestration.calls == []
    print("PASS: non-latest Step is rejected")


def test_state_snapshot_mismatch_is_rejected() -> None:
    runner, clarification, orchestration = (
        build_runner()
    )
    step_state = base_state()
    step_state["issue_id"] = 18

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            request_step=make_step(
                input_state_json=step_state
            ),
        ),
    )

    assert "state snapshot" in str(error)
    assert clarification.states == []
    assert orchestration.calls == []
    print("PASS: mismatched state snapshot is rejected")


def test_controlled_service_error_fails_step() -> None:
    service_error = AgentClarificationRequestError(
        error_code="missing_issue_context",
        message=(
            "Clarification requires persisted Issue context."
        ),
    )
    runner, _, orchestration = build_runner(
        error=service_error
    )

    error = expect_raises(
        AgentClarificationRequestError,
        lambda: call(runner),
    )

    assert error is service_error
    assert [name for name, _ in orchestration.calls] == [
        "fail_step"
    ]
    payload = orchestration.calls[0][1]
    assert payload["error_code"] == (
        "missing_issue_context"
    )
    assert payload["output_state_json"] == {
        "request_version": (
            AGENT_CLARIFICATION_REQUEST_VERSION
        ),
        "error_code": "missing_issue_context",
    }
    print("PASS: controlled service error fails the Step")


def test_unexpected_service_error_is_sanitized() -> None:
    runner, _, orchestration = build_runner(
        error=RuntimeError("secret internal detail")
    )

    expect_raises(
        RuntimeError,
        lambda: call(runner),
    )

    assert [name for name, _ in orchestration.calls] == [
        "fail_step"
    ]
    payload = orchestration.calls[0][1]
    assert payload["error_code"] == (
        "request_clarification_failed"
    )
    assert payload["error_message"] == (
        "RuntimeError occurred while preparing "
        "Agent clarification"
    )
    assert "secret" not in payload["error_message"]
    print("PASS: unexpected service error is sanitized")


def test_invalid_request_type_fails_step() -> None:
    runner, _, orchestration = build_runner(
        return_value={
            "clarification_question": "invalid"
        }
    )

    expect_raises(
        TypeError,
        lambda: call(runner),
    )

    assert [name for name, _ in orchestration.calls] == [
        "fail_step"
    ]
    assert orchestration.calls[0][1][
        "error_code"
    ] == "request_clarification_failed"
    print("PASS: invalid request type fails the Step")


def test_orchestration_error_is_not_double_failed() -> None:
    runner, _, orchestration = build_runner()

    def broken_interrupt(
        db: object,
        **kwargs: object,
    ) -> tuple[object, object]:
        orchestration.calls.append(
            (
                "interrupt_step_and_wait_run",
                {"db": db, **dict(kwargs)},
            )
        )
        raise RuntimeError("transaction failed")

    orchestration.interrupt_step_and_wait_run = (
        broken_interrupt
    )

    error = expect_raises(
        RuntimeError,
        lambda: call(runner),
    )

    assert "transaction failed" in str(error)
    assert [name for name, _ in orchestration.calls] == [
        "interrupt_step_and_wait_run"
    ]
    print("PASS: orchestration error is not double-failed")


def test_no_next_step_is_created() -> None:
    runner, _, orchestration = build_runner()

    result = call(runner)

    assert result.agent_run.step_count == 8
    assert [name for name, _ in orchestration.calls] == [
        "interrupt_step_and_wait_run"
    ]
    print("PASS: waiting transition creates no next Step")


def test_source_preserves_transaction_boundaries() -> None:
    source = inspect.getsource(
        AgentRunnerService.advance_request_clarification
    )

    forbidden = (
        "db.commit(",
        "db.rollback(",
        "db.flush(",
        "db.refresh(",
        "agent_persistence_service",
        "mark_step_interrupted_and_run_waiting(",
        "resume_waiting_investigation_run(",
        "resume_waiting_investigation_run_and_append_step(",
        "complete_step_and_advance_run(",
    )
    found = [
        token for token in forbidden
        if token in source
    ]

    assert not found, found
    assert ".create_request(" in source
    assert "interrupt_step_and_wait_run(" in source
    assert "_fail_step(" in source
    assert "WAITING_FOR_CLARIFICATION_STATUS" in source
    print("PASS: Runner preserves waiting transaction boundaries")


def main() -> None:
    tests = (
        test_version_and_node_are_frozen,
        test_success_interrupts_and_waits,
        test_waiting_call_uses_frozen_status,
        test_state_update_is_controlled,
        test_original_state_is_not_mutated,
        test_result_preserves_waiting_objects,
        test_invalid_run_status_is_rejected,
        test_invalid_current_node_is_rejected,
        test_invalid_step_node_is_rejected,
        test_non_running_step_is_rejected,
        test_step_index_mismatch_is_rejected,
        test_state_snapshot_mismatch_is_rejected,
        test_controlled_service_error_fails_step,
        test_unexpected_service_error_is_sanitized,
        test_invalid_request_type_fails_step,
        test_orchestration_error_is_not_double_failed,
        test_no_next_step_is_created,
        test_source_preserves_transaction_boundaries,
    )

    for test in tests:
        test()

    print(
        "Agent Runner request_clarification assertions "
        "passed (18/18)"
    )


if __name__ == "__main__":
    main()
