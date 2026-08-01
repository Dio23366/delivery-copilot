from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import FrozenInstanceError
import inspect
import textwrap
from types import MappingProxyType, SimpleNamespace
from unittest.mock import Mock

from app.services.agent_runner_service import (
    AGENT_RUNNER_PERSIST_ANALYSIS_VERSION,
    FINAL_REVIEW_NODE,
    GENERATING_ANALYSIS_STATUS,
    PERSIST_ANALYSIS_NODE,
    AgentRunnerPersistAnalysisResult,
    AgentRunnerService,
)


def generated_analysis() -> dict[str, object]:
    return {
        "generation_version": "agent_analysis_generation_v0.1",
    }


def state() -> dict[str, object]:
    return {
        "issue_id": 17,
        "generated_analysis": generated_analysis(),
    }


def run(
    *,
    run_id: object = "run-persist-001",
    run_status: object = "running",
    current_node: object = PERSIST_ANALYSIS_NODE,
    step_count: object = 6,
    state_json: object | None = None,
    analysis_log_id: object = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        run_id=run_id,
        run_status=run_status,
        current_node=current_node,
        step_count=step_count,
        tool_call_count=2,
        state_json=(
            state()
            if state_json is None
            else state_json
        ),
        analysis_log_id=analysis_log_id,
    )


def step(
    *,
    index: object = 6,
    node_name: object = PERSIST_ANALYSIS_NODE,
    step_status: object = "running",
    input_state_json: object | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        step_index=index,
        node_name=node_name,
        step_status=step_status,
        input_state_json=(
            state()
            if input_state_json is None
            else input_state_json
        ),
    )


def success_objects() -> tuple[
    SimpleNamespace,
    SimpleNamespace,
    SimpleNamespace,
    SimpleNamespace,
]:
    persisted_state = {
        **state(),
        "analysis_log_id": 101,
        "pending_approval": True,
    }
    advanced_run = run(
        run_status=GENERATING_ANALYSIS_STATUS,
        current_node=FINAL_REVIEW_NODE,
        step_count=7,
        state_json=persisted_state,
        analysis_log_id=101,
    )
    completed_step = step(
        index=6,
        step_status="completed",
        input_state_json=state(),
    )
    analysis_log = SimpleNamespace(id=101)
    final_review_step = step(
        index=7,
        node_name=FINAL_REVIEW_NODE,
        step_status="running",
        input_state_json=persisted_state,
    )
    return (
        advanced_run,
        completed_step,
        analysis_log,
        final_review_step,
    )


DEFAULT_PERSISTENCE_RESULT = object()


def service_and_orchestration(
    *,
    persistence_result: object = DEFAULT_PERSISTENCE_RESULT,
) -> tuple[AgentRunnerService, Mock]:
    orchestration = Mock()
    orchestration.persist_generated_analysis_and_advance_to_final_review.return_value = (
        success_objects()
        if persistence_result is DEFAULT_PERSISTENCE_RESULT
        else persistence_result
    )
    runner = object.__new__(AgentRunnerService)
    runner._orchestration_service = orchestration
    return runner, orchestration


def call(
    runner: AgentRunnerService,
    *,
    agent_run: object | None = None,
    persist_step: object | None = None,
) -> AgentRunnerPersistAnalysisResult:
    return runner.advance_persist_analysis(
        object(),
        agent_run=(
            run()
            if agent_run is None
            else agent_run
        ),
        persist_analysis_step=(
            step()
            if persist_step is None
            else persist_step
        ),
    )


def assert_raises(
    exception_type: type[BaseException],
    message_fragment: str,
    callback,
) -> BaseException:
    try:
        callback()
    except exception_type as exc:
        assert message_fragment in str(exc)
        return exc
    raise AssertionError(
        f"Expected {exception_type.__name__}"
    )


def test_successful_persist_dispatch() -> None:
    runner, orchestration = service_and_orchestration()
    original_state = state()
    agent_run = run(
        state_json=deepcopy(original_state),
    )
    persist_step = step(
        input_state_json=deepcopy(original_state),
    )

    result = call(
        runner,
        agent_run=agent_run,
        persist_step=persist_step,
    )

    assert isinstance(
        result,
        AgentRunnerPersistAnalysisResult,
    )
    assert result.agent_run.run_status == (
        GENERATING_ANALYSIS_STATUS
    )
    assert result.agent_run.current_node == (
        FINAL_REVIEW_NODE
    )
    assert result.analysis_log.id == 101
    assert result.persist_analysis_step.step_status == (
        "completed"
    )
    assert result.final_review_step.node_name == (
        FINAL_REVIEW_NODE
    )
    assert result.final_review_step.step_status == (
        "running"
    )
    assert result.state_json["analysis_log_id"] == 101
    assert result.state_json["pending_approval"] is True
    assert "generated_analysis" in result.state_json
    assert agent_run.state_json == original_state
    assert persist_step.input_state_json == original_state

    orchestration.persist_generated_analysis_and_advance_to_final_review.assert_called_once()
    called = orchestration.persist_generated_analysis_and_advance_to_final_review.call_args
    assert called.args == (called.args[0],)
    assert called.kwargs == {
        "run_id": "run-persist-001",
        "step_index": 6,
    }
    orchestration.fail_step.assert_not_called()


def test_result_is_frozen() -> None:
    runner, _ = service_and_orchestration()
    result = call(runner)

    assert_raises(
        FrozenInstanceError,
        "cannot assign",
        lambda: setattr(
            result,
            "state_json",
            {},
        ),
    )


def test_run_id_contracts() -> None:
    for invalid in (
        None,
        17,
        "",
        " ",
        " run-persist-001",
        "run-persist-001 ",
    ):
        runner, orchestration = (
            service_and_orchestration()
        )
        assert_raises(
            ValueError,
            "normalized run_id",
            lambda invalid=invalid: call(
                runner,
                agent_run=run(run_id=invalid),
            ),
        )
        orchestration.persist_generated_analysis_and_advance_to_final_review.assert_not_called()


def test_run_status_and_node_contracts() -> None:
    runner, orchestration = service_and_orchestration()
    assert_raises(
        ValueError,
        "from status",
        lambda: call(
            runner,
            agent_run=run(run_status="generating_analysis"),
        ),
    )

    assert_raises(
        ValueError,
        "unexpected persistence node",
        lambda: call(
            runner,
            agent_run=run(current_node="generate_analysis"),
        ),
    )
    orchestration.persist_generated_analysis_and_advance_to_final_review.assert_not_called()


def test_step_count_and_latest_contracts() -> None:
    for invalid_count in (
        None,
        True,
        0,
        -1,
        1.5,
    ):
        runner, _ = service_and_orchestration()
        assert_raises(
            ValueError,
            "positive integer step_count",
            lambda invalid_count=invalid_count: call(
                runner,
                agent_run=run(step_count=invalid_count),
            ),
        )

    runner, _ = service_and_orchestration()
    assert_raises(
        ValueError,
        "latest Step",
        lambda: call(
            runner,
            agent_run=run(step_count=7),
            persist_step=step(index=6),
        ),
    )


def test_step_node_and_status_contracts() -> None:
    runner, orchestration = service_and_orchestration()
    assert_raises(
        ValueError,
        "unexpected persistence node",
        lambda: call(
            runner,
            persist_step=step(
                node_name="generate_analysis",
            ),
        ),
    )
    assert_raises(
        ValueError,
        "must be running",
        lambda: call(
            runner,
            persist_step=step(
                step_status="completed",
            ),
        ),
    )
    orchestration.persist_generated_analysis_and_advance_to_final_review.assert_not_called()


def test_state_snapshot_and_generated_contracts() -> None:
    runner, orchestration = service_and_orchestration()
    assert_raises(
        ValueError,
        "state_json must be a mapping",
        lambda: call(
            runner,
            agent_run=run(state_json=[]),
        ),
    )
    assert_raises(
        ValueError,
        "input state must be a mapping",
        lambda: call(
            runner,
            persist_step=step(input_state_json=[]),
        ),
    )
    assert_raises(
        ValueError,
        "snapshot",
        lambda: call(
            runner,
            persist_step=step(
                input_state_json={"different": True},
            ),
        ),
    )

    missing = state()
    missing.pop("generated_analysis")
    assert_raises(
        ValueError,
        "must contain generated_analysis",
        lambda: call(
            runner,
            agent_run=run(state_json=missing),
            persist_step=step(
                input_state_json=missing,
            ),
        ),
    )

    invalid = {
        **state(),
        "generated_analysis": [],
    }
    assert_raises(
        ValueError,
        "must contain generated_analysis",
        lambda: call(
            runner,
            agent_run=run(state_json=invalid),
            persist_step=step(
                input_state_json=invalid,
            ),
        ),
    )
    orchestration.persist_generated_analysis_and_advance_to_final_review.assert_not_called()


def test_existing_analysis_links_rejected() -> None:
    runner, orchestration = service_and_orchestration()
    assert_raises(
        ValueError,
        "already has an analysis_log_id",
        lambda: call(
            runner,
            agent_run=run(analysis_log_id=101),
        ),
    )

    linked_state = {
        **state(),
        "analysis_log_id": 101,
    }
    assert_raises(
        ValueError,
        "state already has an analysis_log_id",
        lambda: call(
            runner,
            agent_run=run(state_json=linked_state),
            persist_step=step(
                input_state_json=linked_state,
            ),
        ),
    )
    orchestration.persist_generated_analysis_and_advance_to_final_review.assert_not_called()


def test_orchestration_failure_is_sanitized_and_recorded() -> None:
    runner, orchestration = service_and_orchestration()
    orchestration.persist_generated_analysis_and_advance_to_final_review.side_effect = RuntimeError(
        "database-secret-value"
    )

    exc = assert_raises(
        RuntimeError,
        "database-secret-value",
        lambda: call(runner),
    )
    assert str(exc) == "database-secret-value"

    orchestration.fail_step.assert_called_once()
    called = orchestration.fail_step.call_args
    assert called.kwargs["run_id"] == "run-persist-001"
    assert called.kwargs["step_index"] == 6
    assert called.kwargs["error_code"] == (
        "persist_analysis_failed"
    )
    assert called.kwargs["error_message"] == (
        "RuntimeError occurred while persisting "
        "Agent analysis"
    )
    assert "database-secret-value" not in (
        called.kwargs["error_message"]
    )
    assert called.kwargs["output_state_json"] == {
        "runner_persistence_version": (
            AGENT_RUNNER_PERSIST_ANALYSIS_VERSION
        ),
        "error_code": "persist_analysis_failed",
    }


def test_invalid_orchestration_result_rejected() -> None:
    for invalid in (
        None,
        (),
        (1, 2, 3),
        (1, 2, 3, 4, 5),
        [1, 2, 3, 4],
    ):
        runner, orchestration = service_and_orchestration(
            persistence_result=invalid,
        )
        assert_raises(
            TypeError,
            "invalid result",
            lambda runner=runner: call(runner),
        )
        orchestration.fail_step.assert_not_called()


def test_analysis_id_and_link_contracts() -> None:
    for invalid_id in (
        None,
        True,
        0,
        -1,
        "101",
    ):
        objects = list(success_objects())
        objects[2] = SimpleNamespace(id=invalid_id)
        runner, _ = service_and_orchestration(
            persistence_result=tuple(objects),
        )
        assert_raises(
            TypeError,
            "positive integer id",
            lambda runner=runner: call(runner),
        )

    objects = list(success_objects())
    objects[0].analysis_log_id = 999
    runner, _ = service_and_orchestration(
        persistence_result=tuple(objects),
    )
    assert_raises(
        RuntimeError,
        "analysis link",
        lambda: call(runner),
    )


def test_persisted_state_contracts() -> None:
    cases = []

    objects = list(success_objects())
    objects[0].state_json = []
    cases.append(
        (tuple(objects), TypeError, "state_json must be a mapping")
    )

    objects = list(success_objects())
    objects[0].state_json["analysis_log_id"] = 999
    cases.append(
        (tuple(objects), RuntimeError, "does not match")
    )

    objects = list(success_objects())
    objects[0].state_json["pending_approval"] = False
    cases.append(
        (tuple(objects), RuntimeError, "require approval")
    )

    objects = list(success_objects())
    objects[0].state_json.pop("generated_analysis")
    cases.append(
        (tuple(objects), RuntimeError, "retain generated_analysis")
    )

    for result, error_type, fragment in cases:
        runner, _ = service_and_orchestration(
            persistence_result=result,
        )
        assert_raises(
            error_type,
            fragment,
            lambda runner=runner: call(runner),
        )


def test_advanced_run_boundary_contracts() -> None:
    objects = list(success_objects())
    objects[0].run_status = "running"
    runner, _ = service_and_orchestration(
        persistence_result=tuple(objects),
    )
    assert_raises(
        RuntimeError,
        "enter generating_analysis",
        lambda: call(runner),
    )

    objects = list(success_objects())
    objects[0].current_node = PERSIST_ANALYSIS_NODE
    runner, _ = service_and_orchestration(
        persistence_result=tuple(objects),
    )
    assert_raises(
        RuntimeError,
        "advance to final_review",
        lambda: call(runner),
    )


def test_completed_and_final_step_contracts() -> None:
    cases = []

    objects = list(success_objects())
    objects[1].step_index = 5
    cases.append((tuple(objects), "index changed"))

    objects = list(success_objects())
    objects[1].node_name = "generate_analysis"
    cases.append((tuple(objects), "must be persist_analysis"))

    objects = list(success_objects())
    objects[1].step_status = "running"
    cases.append((tuple(objects), "must be completed"))

    objects = list(success_objects())
    objects[3].step_index = 8
    cases.append((tuple(objects), "immediately follow"))

    objects = list(success_objects())
    objects[3].node_name = PERSIST_ANALYSIS_NODE
    cases.append((tuple(objects), "must be final_review"))

    objects = list(success_objects())
    objects[3].step_status = "completed"
    cases.append((tuple(objects), "must be running"))

    for result, fragment in cases:
        runner, _ = service_and_orchestration(
            persistence_result=result,
        )
        assert_raises(
            RuntimeError,
            fragment,
            lambda runner=runner: call(runner),
        )


def test_source_contract_and_transaction_neutrality() -> None:
    assert AGENT_RUNNER_PERSIST_ANALYSIS_VERSION == (
        "agent_runner_persist_analysis_v0.1"
    )
    source = inspect.getsource(
        AgentRunnerService.advance_persist_analysis
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
        "self._orchestration_service."
        "persist_generated_analysis_and_advance_to_final_review"
    ) == 1
    assert calls.count("self._fail_step") == 1

    for forbidden in (
        "db.add",
        "db.commit",
        "db.rollback",
        "db.refresh",
        "db.flush",
        "db.delete",
    ):
        assert forbidden not in calls

    assert "AIAnalysisLog(" not in source
    assert "analysis_log_id" in source
    assert "pending_approval" in source
    assert "generated_analysis" in source
    assert "FINAL_REVIEW_NODE" in source
    assert "GENERATING_ANALYSIS_STATUS" in source

    result_fields = tuple(
        AgentRunnerPersistAnalysisResult
        .__dataclass_fields__
    )
    assert result_fields == (
        "agent_run",
        "persist_analysis_step",
        "analysis_log",
        "final_review_step",
        "state_json",
    )

    immutable_state = MappingProxyType(state())
    immutable_step_state = MappingProxyType(state())
    runner, _ = service_and_orchestration()
    result = call(
        runner,
        agent_run=run(state_json=immutable_state),
        persist_step=step(
            input_state_json=immutable_step_state,
        ),
    )
    assert result.state_json["analysis_log_id"] == 101


TESTS = (
    test_successful_persist_dispatch,
    test_result_is_frozen,
    test_run_id_contracts,
    test_run_status_and_node_contracts,
    test_step_count_and_latest_contracts,
    test_step_node_and_status_contracts,
    test_state_snapshot_and_generated_contracts,
    test_existing_analysis_links_rejected,
    test_orchestration_failure_is_sanitized_and_recorded,
    test_invalid_orchestration_result_rejected,
    test_analysis_id_and_link_contracts,
    test_persisted_state_contracts,
    test_advanced_run_boundary_contracts,
    test_completed_and_final_step_contracts,
    test_source_contract_and_transaction_neutrality,
)


def main() -> None:
    for test in TESTS:
        test()

    print(
        "Agent Runner persist_analysis assertions passed "
        f"{len(TESTS)}/{len(TESTS)}"
    )


if __name__ == "__main__":
    main()
