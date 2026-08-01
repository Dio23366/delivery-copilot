from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime
import inspect
from pathlib import Path
import textwrap
from types import SimpleNamespace
from unittest.mock import Mock


from app.services.agent_runner_service import (
    AGENT_RUNNER_FINAL_REVIEW_VERSION,
    AWAIT_FINAL_REVIEW_NODE,
    FINALIZE_RUN_NODE,
    FINAL_REVIEW_NODE,
    GENERATING_ANALYSIS_STATUS,
    WAITING_FOR_FINAL_REVIEW_STATUS,
    AgentRunnerFinalReviewResult,
    AgentRunnerService,
)


WAITING_SINCE = datetime(2026, 7, 29, 12, 0, 0)


def make_state() -> dict[str, object]:
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


def make_run() -> SimpleNamespace:
    return SimpleNamespace(
        run_id="run-final-review-001",
        run_status=GENERATING_ANALYSIS_STATUS,
        current_node=FINAL_REVIEW_NODE,
        step_count=7,
        tool_call_count=2,
        analysis_log_id=68,
        state_json=make_state(),
        waiting_since=None,
        resume_node=None,
    )


def make_step(
    *,
    state: dict[str, object] | None = None,
) -> SimpleNamespace:
    effective_state = (
        make_state()
        if state is None
        else deepcopy(state)
    )
    return SimpleNamespace(
        step_index=7,
        node_name=FINAL_REVIEW_NODE,
        step_status="running",
        input_state_json=effective_state,
        output_state_json=None,
        started_at=datetime(2026, 7, 29, 11, 59, 0),
        completed_at=None,
    )


def make_receipt() -> dict[str, object]:
    return {
        "final_review_wait_version": (
            "agent_final_review_wait_v0.1"
        ),
        "analysis_log_id": 68,
        "pending_approval": True,
        "completed_node": FINAL_REVIEW_NODE,
        "waiting_node": AWAIT_FINAL_REVIEW_NODE,
        "resume_node": FINALIZE_RUN_NODE,
    }


def make_wait_result() -> tuple[
    SimpleNamespace,
    SimpleNamespace,
    SimpleNamespace,
]:
    state = make_state()
    receipt = make_receipt()
    waiting_run = SimpleNamespace(
        run_id="run-final-review-001",
        run_status=WAITING_FOR_FINAL_REVIEW_STATUS,
        current_node=AWAIT_FINAL_REVIEW_NODE,
        step_count=8,
        tool_call_count=2,
        analysis_log_id=68,
        state_json=deepcopy(state),
        waiting_since=WAITING_SINCE,
        resume_node=FINALIZE_RUN_NODE,
    )
    completed_step = SimpleNamespace(
        step_index=7,
        node_name=FINAL_REVIEW_NODE,
        step_status="completed",
        input_state_json=deepcopy(state),
        output_state_json=deepcopy(receipt),
        completed_at=WAITING_SINCE,
    )
    await_step = SimpleNamespace(
        step_index=8,
        node_name=AWAIT_FINAL_REVIEW_NODE,
        step_status="interrupted",
        input_state_json=deepcopy(state),
        output_state_json=deepcopy(receipt),
        started_at=WAITING_SINCE,
        completed_at=WAITING_SINCE,
    )
    return waiting_run, completed_step, await_step


def make_service() -> tuple[
    AgentRunnerService,
    Mock,
]:
    service = object.__new__(
        AgentRunnerService
    )
    orchestration = Mock()
    orchestration.complete_final_review_and_wait_run.return_value = (
        make_wait_result()
    )
    service._orchestration_service = orchestration
    service._fail_step = Mock()
    return service, orchestration


def synchronize_step(
    run: SimpleNamespace,
    step: SimpleNamespace,
) -> None:
    step.input_state_json = deepcopy(
        run.state_json
    )


def invoke(
    service: AgentRunnerService,
    run: SimpleNamespace,
    step: SimpleNamespace,
) -> AgentRunnerFinalReviewResult:
    return service.advance_final_review(
        object(),
        agent_run=run,
        final_review_step=step,
    )


def assert_raises(
    expected: type[BaseException],
    fragment: str,
    callback,
) -> BaseException:
    try:
        callback()
    except expected as exc:
        assert fragment in str(exc)
        return exc
    raise AssertionError(
        f"Expected {expected.__name__}: {fragment}"
    )


def test_successful_call_and_result_contract() -> None:
    service, orchestration = make_service()
    run = make_run()
    step = make_step(state=run.state_json)
    db = object()

    result = service.advance_final_review(
        db,
        agent_run=run,
        final_review_step=step,
    )

    assert isinstance(
        result,
        AgentRunnerFinalReviewResult,
    )
    expected = (
        orchestration
        .complete_final_review_and_wait_run
        .return_value
    )
    assert result.agent_run is expected[0]
    assert result.final_review_step is expected[1]
    assert result.await_final_review_step is expected[2]
    assert result.state_json == make_state()

    (
        orchestration
        .complete_final_review_and_wait_run
        .assert_called_once_with(
            db,
            run_id="run-final-review-001",
            step_index=7,
        )
    )
    service._fail_step.assert_not_called()


def test_run_id_contract() -> None:
    for value in (
        None,
        "",
        " ",
        " run-final-review-001",
        17,
    ):
        service, _ = make_service()
        run = make_run()
        run.run_id = value
        step = make_step(state=run.state_json)
        assert_raises(
            ValueError,
            "normalized run_id",
            lambda service=service, run=run, step=step: (
                invoke(service, run, step)
            ),
        )


def test_run_status_contract() -> None:
    service, _ = make_service()
    run = make_run()
    run.run_status = "running"
    step = make_step(state=run.state_json)

    assert_raises(
        ValueError,
        "cannot enter final review wait",
        lambda: invoke(service, run, step),
    )


def test_current_node_contract() -> None:
    service, _ = make_service()
    run = make_run()
    run.current_node = "persist_analysis"
    step = make_step(state=run.state_json)

    assert_raises(
        ValueError,
        "unexpected final review node",
        lambda: invoke(service, run, step),
    )


def test_step_count_and_latest_contract() -> None:
    service, _ = make_service()
    run = make_run()
    run.step_count = True
    step = make_step(state=run.state_json)

    assert_raises(
        ValueError,
        "positive integer step_count",
        lambda: invoke(service, run, step),
    )

    service, _ = make_service()
    run = make_run()
    step = make_step(state=run.state_json)
    step.step_index = 6

    assert_raises(
        ValueError,
        "must be the latest Step",
        lambda: invoke(service, run, step),
    )


def test_run_state_mapping_contract() -> None:
    service, _ = make_service()
    run = make_run()
    run.state_json = []
    step = make_step()

    assert_raises(
        ValueError,
        "state_json must be a mapping",
        lambda: invoke(service, run, step),
    )


def test_step_node_and_status_contract() -> None:
    service, _ = make_service()
    run = make_run()
    step = make_step(state=run.state_json)
    step.node_name = AWAIT_FINAL_REVIEW_NODE

    assert_raises(
        ValueError,
        "unexpected final review node",
        lambda: invoke(service, run, step),
    )

    service, _ = make_service()
    run = make_run()
    step = make_step(state=run.state_json)
    step.step_status = "completed"

    assert_raises(
        ValueError,
        "must be running",
        lambda: invoke(service, run, step),
    )


def test_step_snapshot_contract() -> None:
    service, _ = make_service()
    run = make_run()
    step = make_step(state=run.state_json)
    step.input_state_json = []

    assert_raises(
        ValueError,
        "input state must be a mapping",
        lambda: invoke(service, run, step),
    )

    service, _ = make_service()
    run = make_run()
    step = make_step(state=run.state_json)
    step.input_state_json["issue_id"] = 99

    assert_raises(
        ValueError,
        "does not match Agent Run state",
        lambda: invoke(service, run, step),
    )


def test_analysis_link_contract() -> None:
    for value in (
        None,
        True,
        0,
        -1,
        "68",
    ):
        service, _ = make_service()
        run = make_run()
        run.analysis_log_id = value
        step = make_step(state=run.state_json)

        assert_raises(
            ValueError,
            "positive analysis_log_id",
            lambda service=service, run=run, step=step: (
                invoke(service, run, step)
            ),
        )

    service, _ = make_service()
    run = make_run()
    run.state_json["analysis_log_id"] = 69
    step = make_step(state=run.state_json)

    assert_raises(
        ValueError,
        "does not match Agent Run",
        lambda: invoke(service, run, step),
    )


def test_pending_approval_and_generated_analysis_contract() -> None:
    service, _ = make_service()
    run = make_run()
    run.state_json["pending_approval"] = False
    step = make_step(state=run.state_json)

    assert_raises(
        ValueError,
        "must require pending approval",
        lambda: invoke(service, run, step),
    )

    service, _ = make_service()
    run = make_run()
    run.state_json["generated_analysis"] = None
    step = make_step(state=run.state_json)

    assert_raises(
        ValueError,
        "must retain generated_analysis",
        lambda: invoke(service, run, step),
    )


def test_stale_wait_metadata_contract() -> None:
    service, _ = make_service()
    run = make_run()
    run.waiting_since = WAITING_SINCE
    step = make_step(state=run.state_json)

    assert_raises(
        ValueError,
        "cannot already be waiting",
        lambda: invoke(service, run, step),
    )

    service, _ = make_service()
    run = make_run()
    run.resume_node = FINALIZE_RUN_NODE
    step = make_step(state=run.state_json)

    assert_raises(
        ValueError,
        "cannot have a resume_node",
        lambda: invoke(service, run, step),
    )


def test_orchestration_failure_is_persisted_safely() -> None:
    service, orchestration = make_service()
    run = make_run()
    step = make_step(state=run.state_json)
    failure = RuntimeError(
        "secret database detail"
    )
    (
        orchestration
        .complete_final_review_and_wait_run
        .side_effect
    ) = failure

    db = object()
    caught = assert_raises(
        RuntimeError,
        "secret database detail",
        lambda: service.advance_final_review(
            db,
            agent_run=run,
            final_review_step=step,
        ),
    )
    assert caught is failure

    service._fail_step.assert_called_once_with(
        db,
        run_id="run-final-review-001",
        step_index=7,
        node_name=FINAL_REVIEW_NODE,
        error_code="final_review_wait_failed",
        error_message=(
            "RuntimeError occurred while entering "
            "final review wait"
        ),
        output_state_json={
            "runner_final_review_version": (
                AGENT_RUNNER_FINAL_REVIEW_VERSION
            ),
            "error_code": "final_review_wait_failed",
        },
    )
    called = service._fail_step.call_args
    assert "secret database detail" not in (
        called.kwargs["error_message"]
    )


def test_invalid_orchestration_result_shape() -> None:
    for value in (
        None,
        [],
        (object(),),
        (object(), object()),
        (object(), object(), object(), object()),
    ):
        service, orchestration = make_service()
        (
            orchestration
            .complete_final_review_and_wait_run
            .return_value
        ) = value
        run = make_run()
        step = make_step(state=run.state_json)

        assert_raises(
            TypeError,
            "invalid result",
            lambda service=service, run=run, step=step: (
                invoke(service, run, step)
            ),
        )


def test_waiting_run_lifecycle_contract() -> None:
    mutations = (
        ("run_status", "running", "waiting_for_final_review"),
        ("current_node", FINAL_REVIEW_NODE, "await_final_review"),
        ("resume_node", None, "finalize_run"),
        ("waiting_since", None, "waiting_since"),
        ("analysis_log_id", 69, "analysis link changed"),
        ("step_count", 7, "step_count changed"),
    )

    for field_name, value, fragment in mutations:
        service, orchestration = make_service()
        result = list(make_wait_result())
        setattr(result[0], field_name, value)
        (
            orchestration
            .complete_final_review_and_wait_run
            .return_value
        ) = tuple(result)
        run = make_run()
        step = make_step(state=run.state_json)

        assert_raises(
            RuntimeError,
            fragment,
            lambda service=service, run=run, step=step: (
                invoke(service, run, step)
            ),
        )


def test_waiting_state_contract() -> None:
    service, orchestration = make_service()
    result = list(make_wait_result())
    result[0].state_json["issue_id"] = 99
    (
        orchestration
        .complete_final_review_and_wait_run
        .return_value
    ) = tuple(result)
    run = make_run()
    step = make_step(state=run.state_json)

    assert_raises(
        RuntimeError,
        "must preserve Agent state",
        lambda: invoke(service, run, step),
    )

    service, orchestration = make_service()
    result = list(make_wait_result())
    result[0].state_json = []
    (
        orchestration
        .complete_final_review_and_wait_run
        .return_value
    ) = tuple(result)
    run = make_run()
    step = make_step(state=run.state_json)

    assert_raises(
        TypeError,
        "state_json must be a mapping",
        lambda: invoke(service, run, step),
    )


def test_completed_final_review_step_contract() -> None:
    mutations = (
        ("step_index", 6, "index changed"),
        ("node_name", AWAIT_FINAL_REVIEW_NODE, "must be final_review"),
        ("step_status", "running", "must be completed"),
    )

    for field_name, value, fragment in mutations:
        service, orchestration = make_service()
        result = list(make_wait_result())
        setattr(result[1], field_name, value)
        (
            orchestration
            .complete_final_review_and_wait_run
            .return_value
        ) = tuple(result)
        run = make_run()
        step = make_step(state=run.state_json)

        assert_raises(
            RuntimeError,
            fragment,
            lambda service=service, run=run, step=step: (
                invoke(service, run, step)
            ),
        )


def test_await_final_review_step_contract() -> None:
    mutations = (
        ("step_index", 9, "immediately follow"),
        ("node_name", FINAL_REVIEW_NODE, "must be await_final_review"),
        ("step_status", "running", "must be interrupted"),
    )

    for field_name, value, fragment in mutations:
        service, orchestration = make_service()
        result = list(make_wait_result())
        setattr(result[2], field_name, value)
        (
            orchestration
            .complete_final_review_and_wait_run
            .return_value
        ) = tuple(result)
        run = make_run()
        step = make_step(state=run.state_json)

        assert_raises(
            RuntimeError,
            fragment,
            lambda service=service, run=run, step=step: (
                invoke(service, run, step)
            ),
        )

    service, orchestration = make_service()
    result = list(make_wait_result())
    result[2].input_state_json["issue_id"] = 99
    (
        orchestration
        .complete_final_review_and_wait_run
        .return_value
    ) = tuple(result)
    run = make_run()
    step = make_step(state=run.state_json)

    assert_raises(
        RuntimeError,
        "input state must match",
        lambda: invoke(service, run, step),
    )


def test_wait_receipt_contract() -> None:
    service, orchestration = make_service()
    result = list(make_wait_result())
    result[1].output_state_json["analysis_log_id"] = 69
    result[2].output_state_json = deepcopy(
        result[1].output_state_json
    )
    (
        orchestration
        .complete_final_review_and_wait_run
        .return_value
    ) = tuple(result)
    run = make_run()
    step = make_step(state=run.state_json)

    assert_raises(
        RuntimeError,
        "unexpected analysis_log_id",
        lambda: invoke(service, run, step),
    )

    service, orchestration = make_service()
    result = list(make_wait_result())
    result[2].output_state_json = []
    (
        orchestration
        .complete_final_review_and_wait_run
        .return_value
    ) = tuple(result)
    run = make_run()
    step = make_step(state=run.state_json)

    assert_raises(
        RuntimeError,
        "must share a wait receipt",
        lambda: invoke(service, run, step),
    )

    service, orchestration = make_service()
    result = list(make_wait_result())
    result[1].output_state_json = deepcopy(
        result[2].output_state_json
    )
    result[1].output_state_json[
        "final_review_wait_version"
    ] = ""
    result[2].output_state_json = deepcopy(
        result[1].output_state_json
    )
    (
        orchestration
        .complete_final_review_and_wait_run
        .return_value
    ) = tuple(result)
    run = make_run()
    step = make_step(state=run.state_json)

    assert_raises(
        RuntimeError,
        "must expose a version",
        lambda: invoke(service, run, step),
    )


def test_source_layer_and_transaction_contract() -> None:
    source = inspect.getsource(
        AgentRunnerService.advance_final_review
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
        "self._orchestration_service."
        "complete_final_review_and_wait_run"
    )
    assert calls.count(target) == 1
    assert calls.count("self._fail_step") == 1

    assert "db.add" not in calls
    assert "db.flush" not in calls
    assert "db.commit" not in calls
    assert "db.rollback" not in calls
    assert "db.refresh" not in calls
    assert "AIAnalysisLog" not in source

    runner_path = Path(
        inspect.getsourcefile(
            AgentRunnerService
        )
        or ""
    )
    runner_source = runner_path.read_text(
        encoding="utf-8"
    )
    assert "agent_persistence_service" not in (
        runner_source
    )
    assert (
        "complete_final_review_and_wait_run"
        in runner_source
    )
    ast.parse(runner_source)


def test_constants_and_frozen_result_contract() -> None:
    assert AGENT_RUNNER_FINAL_REVIEW_VERSION == (
        "agent_runner_final_review_v0.1"
    )
    assert FINAL_REVIEW_NODE == "final_review"
    assert AWAIT_FINAL_REVIEW_NODE == (
        "await_final_review"
    )
    assert GENERATING_ANALYSIS_STATUS == (
        "generating_analysis"
    )
    assert WAITING_FOR_FINAL_REVIEW_STATUS == (
        "waiting_for_final_review"
    )
    assert FINALIZE_RUN_NODE == "finalize_run"

    result = AgentRunnerFinalReviewResult(
        agent_run=object(),
        final_review_step=object(),
        await_final_review_step=object(),
        state_json={},
    )
    assert result.__dataclass_params__.frozen is True

    try:
        result.state_json = {}
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError(
            "AgentRunnerFinalReviewResult must be frozen"
        )


TESTS = (
    test_successful_call_and_result_contract,
    test_run_id_contract,
    test_run_status_contract,
    test_current_node_contract,
    test_step_count_and_latest_contract,
    test_run_state_mapping_contract,
    test_step_node_and_status_contract,
    test_step_snapshot_contract,
    test_analysis_link_contract,
    test_pending_approval_and_generated_analysis_contract,
    test_stale_wait_metadata_contract,
    test_orchestration_failure_is_persisted_safely,
    test_invalid_orchestration_result_shape,
    test_waiting_run_lifecycle_contract,
    test_waiting_state_contract,
    test_completed_final_review_step_contract,
    test_await_final_review_step_contract,
    test_wait_receipt_contract,
    test_source_layer_and_transaction_contract,
    test_constants_and_frozen_result_contract,
)


def main() -> None:
    for test in TESTS:
        test()

    print(
        "Agent Runner final_review assertions passed "
        f"{len(TESTS)}/{len(TESTS)}"
    )


if __name__ == "__main__":
    main()
