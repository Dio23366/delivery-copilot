from __future__ import annotations

from pathlib import Path
from types import MappingProxyType, SimpleNamespace
import inspect
import sys
from typing import Callable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.agent_guarded_tool_execution_service import (
    AgentGuardedToolExecutionOutcome,
)
from app.services.agent_runner_service import (
    AGENT_RUNNER_EXECUTE_TOOL_VERSION,
    EVALUATE_EVIDENCE_NODE,
    EXECUTE_TOOL_NODE,
    AgentRunnerExecuteToolResult,
    AgentRunnerService,
)
from app.services.agent_tool_result_state_service import (
    AGENT_TOOL_RESULT_STATE_VERSION,
    AgentToolResultStateError,
    AgentToolResultStateOutcome,
)
from app.services.agent_tool_selection_service import (
    AGENT_TOOL_SELECTION_VERSION,
)


TOOL_NAME = "search_knowledge"
TOOL_VERSION = "grounded_retrieval_v1"
CALL_IDENTITY = f"{TOOL_NAME}:{'a' * 64}"


class ControlledGuardedError(RuntimeError):
    def __init__(
        self,
        *,
        error_code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code


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


def selected_tool() -> dict[str, object]:
    return {
        "selection_version": AGENT_TOOL_SELECTION_VERSION,
        "tool_name": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "arguments": {"issue_id": 17},
        "call_identity": CALL_IDENTITY,
        "confidence": 0.92,
        "reason": "Grounded knowledge is preferred.",
    }


def base_state() -> dict[str, object]:
    return {
        "issue_id": 17,
        "triage_confirmed": True,
        "selected_tool": selected_tool(),
        "tool_results": [],
        "retrieved_evidence": [],
        "max_steps": 16,
        "max_tool_calls": 3,
    }


def guarded_outcome() -> AgentGuardedToolExecutionOutcome:
    decision = SimpleNamespace(
        tool_name=TOOL_NAME,
        tool_version=TOOL_VERSION,
        call_identity=CALL_IDENTITY,
        normalized_arguments={"issue_id": 17},
    )
    execution = SimpleNamespace(
        tool_call=SimpleNamespace(id=501),
        tool_name=TOOL_NAME,
        tool_version=TOOL_VERSION,
        call_identity=CALL_IDENTITY,
        result_json={
            "retrieval_status": "succeeded",
            "knowledge_evidence": [
                {
                    "citation_id": "K1",
                    "chunk_id": 21,
                }
            ],
        },
    )
    return AgentGuardedToolExecutionOutcome(
        decision=decision,
        execution=execution,
    )


def result_state_outcome() -> AgentToolResultStateOutcome:
    tool_result = {
        "tool_name": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "call_identity": CALL_IDENTITY,
        "arguments": {"issue_id": 17},
        "result_json": {
            "retrieval_status": "succeeded",
            "knowledge_evidence": [
                {
                    "citation_id": "K1",
                    "chunk_id": 21,
                }
            ],
        },
        "execution_status": "completed",
    }
    evidence = {
        "source_tool": TOOL_NAME,
        "source_call_identity": CALL_IDENTITY,
        "evidence_type": "knowledge_chunk",
        "payload": {
            "citation_id": "K1",
            "chunk_id": 21,
        },
    }
    update = {
        "selected_tool": None,
        "tool_results": [tool_result],
        "retrieved_evidence": [evidence],
    }
    return AgentToolResultStateOutcome(
        tool_result=MappingProxyType(tool_result),
        retrieved_evidence=(
            MappingProxyType(evidence),
        ),
        state_update=MappingProxyType(update),
    )


class RecordingGuardedService:
    def __init__(
        self,
        *,
        outcome: (
            AgentGuardedToolExecutionOutcome | None
        ) = None,
        error: Exception | None = None,
    ) -> None:
        self.outcome = (
            outcome
            if outcome is not None
            else guarded_outcome()
        )
        self.error = error
        self.calls: list[dict[str, object]] = []

    def execute_once(
        self,
        db: object,
        **kwargs: object,
    ) -> AgentGuardedToolExecutionOutcome:
        self.calls.append(
            {"db": db, **dict(kwargs)}
        )
        if self.error is not None:
            raise self.error
        return self.outcome


class RecordingResultStateService:
    def __init__(
        self,
        *,
        outcome: AgentToolResultStateOutcome | None = None,
        error: Exception | None = None,
    ) -> None:
        self.outcome = (
            outcome
            if outcome is not None
            else result_state_outcome()
        )
        self.error = error
        self.calls: list[
            tuple[
                dict[str, object],
                AgentGuardedToolExecutionOutcome,
            ]
        ] = []

    def apply(
        self,
        state: object,
        execution_outcome: (
            AgentGuardedToolExecutionOutcome
        ),
    ) -> AgentToolResultStateOutcome:
        self.calls.append(
            (dict(state), execution_outcome)
        )
        if self.error is not None:
            raise self.error
        return self.outcome


class RecordingOrchestrationService:
    def __init__(self) -> None:
        self.calls: list[
            tuple[str, dict[str, object]]
        ] = []

    def complete_step_and_advance_run(
        self,
        db: object,
        **kwargs: object,
    ) -> tuple[object, object, object]:
        self.calls.append(
            (
                "complete_step_and_advance_run",
                {"db": db, **dict(kwargs)},
            )
        )
        advanced_run = SimpleNamespace(
            run_id=kwargs["run_id"],
            run_status="running",
            current_node=kwargs["next_node"],
            step_count=int(kwargs["step_index"]) + 1,
            state_json=dict(kwargs["state_json"]),
        )
        completed_step = SimpleNamespace(
            step_index=kwargs["step_index"],
            node_name=EXECUTE_TOOL_NODE,
            step_status="completed",
            output_state_json=dict(
                kwargs["output_state_json"]
            ),
        )
        next_step = SimpleNamespace(
            step_index=int(kwargs["step_index"]) + 1,
            node_name=kwargs["next_node"],
            step_status="running",
            input_state_json=dict(
                kwargs["state_json"]
            ),
        )
        return advanced_run, completed_step, next_step

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
            node_name=EXECUTE_TOOL_NODE,
            step_status="failed",
            error_code=kwargs["error_code"],
        )


def make_run(
    *,
    run_status: str = "running",
    current_node: str = EXECUTE_TOOL_NODE,
    step_count: int = 6,
    state_json: dict[str, object] | None = None,
) -> object:
    return SimpleNamespace(
        run_id="run-001",
        run_status=run_status,
        current_node=current_node,
        step_count=step_count,
        tool_call_count=0,
        state_json=(
            dict(state_json)
            if state_json is not None
            else base_state()
        ),
    )


def make_step(
    *,
    step_index: int = 6,
    node_name: str = EXECUTE_TOOL_NODE,
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
    guarded_error: Exception | None = None,
    result_error: Exception | None = None,
) -> tuple[
    AgentRunnerService,
    RecordingGuardedService,
    RecordingResultStateService,
    RecordingOrchestrationService,
]:
    guarded = RecordingGuardedService(
        error=guarded_error
    )
    result_state = RecordingResultStateService(
        error=result_error
    )
    orchestration = RecordingOrchestrationService()
    runner = AgentRunnerService(
        orchestration_service=orchestration,
        guarded_tool_execution_service=guarded,
        tool_result_state_service=result_state,
    )
    return (
        runner,
        guarded,
        result_state,
        orchestration,
    )


def call(
    runner: AgentRunnerService,
    *,
    db: object | None = None,
    agent_run: object | None = None,
    execute_step: object | None = None,
) -> AgentRunnerExecuteToolResult:
    return runner.advance_execute_tool(
        db if db is not None else object(),
        agent_run=(
            agent_run
            if agent_run is not None
            else make_run()
        ),
        execute_tool_step=(
            execute_step
            if execute_step is not None
            else make_step()
        ),
    )


def test_version_and_nodes_are_frozen() -> None:
    assert AGENT_RUNNER_EXECUTE_TOOL_VERSION == (
        "agent_runner_execute_tool_v0.1"
    )
    assert EXECUTE_TOOL_NODE == "execute_tool"
    assert EVALUATE_EVIDENCE_NODE == "evaluate_evidence"
    print("PASS: Runner execute_tool contract is frozen")


def test_happy_path_executes_maps_and_advances() -> None:
    (
        runner,
        guarded,
        result_state,
        orchestration,
    ) = build_runner()
    db = object()

    result = call(runner, db=db)

    assert isinstance(
        result,
        AgentRunnerExecuteToolResult,
    )
    assert result.agent_run.current_node == (
        EVALUATE_EVIDENCE_NODE
    )
    assert result.evaluate_evidence_step.node_name == (
        EVALUATE_EVIDENCE_NODE
    )
    assert len(guarded.calls) == 1
    assert len(result_state.calls) == 1
    assert len(orchestration.calls) == 1
    assert guarded.calls[0]["db"] is db
    print("PASS: execute_tool maps and advances")


def test_guarded_execution_arguments_are_exact() -> None:
    runner, guarded, _, _ = build_runner()

    call(runner)

    payload = guarded.calls[0]
    assert payload["run_id"] == "run-001"
    assert payload["step_index"] == 6
    assert payload["tool_name"] == TOOL_NAME
    assert payload["arguments"] == {"issue_id": 17}
    assert payload["max_tool_calls"] == 3
    print("PASS: Guarded execution arguments are exact")


def test_result_state_receives_persisted_state() -> None:
    runner, _, result_state, _ = build_runner()
    state = base_state()
    state["preserved_value"] = "keep-me"

    call(
        runner,
        agent_run=make_run(state_json=state),
        execute_step=make_step(
            input_state_json=state
        ),
    )

    observed_state, observed_outcome = (
        result_state.calls[0]
    )
    assert observed_state == state
    assert observed_outcome is guarded_outcome() or (
        isinstance(
            observed_outcome,
            AgentGuardedToolExecutionOutcome,
        )
    )
    print("PASS: result-state mapping receives persisted state")


def test_state_update_is_persisted() -> None:
    runner, _, _, orchestration = build_runner()

    result = call(runner)
    update = result.result_state_outcome.to_state_update()

    assert result.state_json["selected_tool"] is None
    assert len(result.state_json["tool_results"]) == 1
    assert len(
        result.state_json["retrieved_evidence"]
    ) == 1

    method, payload = orchestration.calls[0]
    assert method == "complete_step_and_advance_run"
    assert payload["next_node"] == (
        EVALUATE_EVIDENCE_NODE
    )
    assert payload["state_json"] == result.state_json
    assert payload["output_state_json"] == (
        result.result_state_outcome.as_dict()
    )
    assert update["selected_tool"] is None
    print("PASS: controlled result state is persisted")


def test_original_state_is_not_mutated() -> None:
    runner, _, _, _ = build_runner()
    state = base_state()
    original_selected = dict(
        state["selected_tool"]
    )

    result = call(
        runner,
        agent_run=make_run(state_json=state),
        execute_step=make_step(
            input_state_json=state
        ),
    )

    assert state["selected_tool"] == original_selected
    assert state["tool_results"] == []
    assert state["retrieved_evidence"] == []
    assert result.state_json["selected_tool"] is None
    print("PASS: original Agent state is not mutated")


def test_invalid_run_status_is_rejected() -> None:
    runner, guarded, result_state, orchestration = (
        build_runner()
    )

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            agent_run=make_run(
                run_status="waiting_for_human"
            ),
        ),
    )

    assert "status" in str(error)
    assert guarded.calls == []
    assert result_state.calls == []
    assert orchestration.calls == []
    print("PASS: invalid Run status is rejected")


def test_invalid_current_node_is_rejected() -> None:
    runner, guarded, result_state, orchestration = (
        build_runner()
    )

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            agent_run=make_run(
                current_node="select_tool"
            ),
        ),
    )

    assert "current node" in str(error)
    assert guarded.calls == []
    assert result_state.calls == []
    assert orchestration.calls == []
    print("PASS: invalid current node is rejected")


def test_invalid_execute_step_is_rejected() -> None:
    invalid_steps = (
        make_step(node_name="select_tool"),
        make_step(step_status="completed"),
    )

    for invalid_step in invalid_steps:
        (
            runner,
            guarded,
            result_state,
            orchestration,
        ) = build_runner()

        expect_raises(
            ValueError,
            lambda invalid_step=invalid_step: call(
                runner,
                execute_step=invalid_step,
            ),
        )
        assert guarded.calls == []
        assert result_state.calls == []
        assert orchestration.calls == []

    print("PASS: invalid execute_tool Step is rejected")


def test_step_index_mismatch_is_rejected() -> None:
    runner, guarded, result_state, orchestration = (
        build_runner()
    )

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            agent_run=make_run(step_count=7),
            execute_step=make_step(step_index=6),
        ),
    )

    assert "latest Step" in str(error)
    assert guarded.calls == []
    assert result_state.calls == []
    assert orchestration.calls == []
    print("PASS: non-latest execute_tool Step is rejected")


def test_state_snapshot_mismatch_is_rejected() -> None:
    runner, guarded, result_state, orchestration = (
        build_runner()
    )
    step_state = base_state()
    step_state["issue_id"] = 18

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            execute_step=make_step(
                input_state_json=step_state
            ),
        ),
    )

    assert "state snapshot" in str(error)
    assert guarded.calls == []
    assert result_state.calls == []
    assert orchestration.calls == []
    print("PASS: mismatched Step state is rejected")


def test_missing_selected_tool_is_rejected() -> None:
    runner, guarded, result_state, orchestration = (
        build_runner()
    )
    state = base_state()
    state["selected_tool"] = None

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            agent_run=make_run(state_json=state),
            execute_step=make_step(
                input_state_json=state
            ),
        ),
    )

    assert "selected_tool" in str(error)
    assert guarded.calls == []
    assert result_state.calls == []
    assert orchestration.calls == []
    print("PASS: missing selected_tool is rejected")


def test_malformed_selected_tool_fails_before_execution() -> None:
    runner, guarded, result_state, orchestration = (
        build_runner()
    )
    state = base_state()
    state["selected_tool"]["selection_version"] = (
        "unsupported"
    )

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            agent_run=make_run(state_json=state),
            execute_step=make_step(
                input_state_json=state
            ),
        ),
    )

    assert "selection_version" in str(error)
    assert guarded.calls == []
    assert result_state.calls == []
    assert orchestration.calls == []
    print("PASS: malformed selected_tool fails before execution")


def test_invalid_max_tool_calls_is_rejected() -> None:
    for value in (None, 0, -1, True, "3"):
        (
            runner,
            guarded,
            result_state,
            orchestration,
        ) = build_runner()
        state = base_state()
        state["max_tool_calls"] = value

        expect_raises(
            ValueError,
            lambda state=state: call(
                runner,
                agent_run=make_run(
                    state_json=state
                ),
                execute_step=make_step(
                    input_state_json=state
                ),
            ),
        )
        assert guarded.calls == []
        assert result_state.calls == []
        assert orchestration.calls == []

    print("PASS: invalid max_tool_calls is rejected")


def test_controlled_guarded_error_fails_step() -> None:
    guarded_error = ControlledGuardedError(
        error_code="duplicate_tool_call",
        message="Duplicate Tool call rejected.",
    )
    runner, _, result_state, orchestration = (
        build_runner(
            guarded_error=guarded_error
        )
    )

    error = expect_raises(
        ControlledGuardedError,
        lambda: call(runner),
    )

    assert error is guarded_error
    assert result_state.calls == []
    assert [name for name, _ in orchestration.calls] == [
        "fail_step"
    ]
    payload = orchestration.calls[0][1]
    assert payload["error_code"] == (
        "duplicate_tool_call"
    )
    assert payload["output_state_json"] == {
        "execute_version": (
            AGENT_RUNNER_EXECUTE_TOOL_VERSION
        ),
        "error_code": "duplicate_tool_call",
    }
    print("PASS: controlled Guarded error fails the Step")


def test_result_state_error_fails_step() -> None:
    result_error = AgentToolResultStateError(
        error_code="policy_execution_mismatch",
        message="Controlled outcome mismatch.",
    )
    runner, guarded, _, orchestration = (
        build_runner(result_error=result_error)
    )

    error = expect_raises(
        AgentToolResultStateError,
        lambda: call(runner),
    )

    assert error is result_error
    assert len(guarded.calls) == 1
    assert [name for name, _ in orchestration.calls] == [
        "fail_step"
    ]
    assert orchestration.calls[0][1][
        "error_code"
    ] == "policy_execution_mismatch"
    print("PASS: result-state error fails the Step")


def test_unexpected_execution_error_is_sanitized() -> None:
    runner, _, result_state, orchestration = (
        build_runner(
            guarded_error=RuntimeError(
                "secret adapter detail"
            )
        )
    )

    expect_raises(
        RuntimeError,
        lambda: call(runner),
    )

    assert result_state.calls == []
    assert [name for name, _ in orchestration.calls] == [
        "fail_step"
    ]
    payload = orchestration.calls[0][1]
    assert payload["error_code"] == (
        "execute_tool_failed"
    )
    assert payload["error_message"] == (
        "RuntimeError occurred while executing "
        "an Agent Tool"
    )
    assert "secret" not in payload["error_message"]
    print("PASS: unexpected execution error is sanitized")


def test_source_preserves_execution_boundaries() -> None:
    source = inspect.getsource(
        AgentRunnerService.advance_execute_tool
    )

    forbidden = (
        "db.commit(",
        "db.rollback(",
        "db.flush(",
        "db.refresh(",
        "agent_persistence_service",
        "create_tool_call(",
        "start_tool_call(",
        "complete_tool_call(",
        "fail_tool_call(",
        "timeout_tool_call(",
        "cancel_tool_call(",
        "retry",
    )
    found = [
        token for token in forbidden
        if token in source
    ]

    assert not found, found
    assert ".execute_once(" in source
    assert ".apply(" in source
    assert "complete_step_and_advance_run(" in source
    assert "_fail_step(" in source
    print("PASS: Runner execute_tool preserves boundaries")


def main() -> None:
    tests = (
        test_version_and_nodes_are_frozen,
        test_happy_path_executes_maps_and_advances,
        test_guarded_execution_arguments_are_exact,
        test_result_state_receives_persisted_state,
        test_state_update_is_persisted,
        test_original_state_is_not_mutated,
        test_invalid_run_status_is_rejected,
        test_invalid_current_node_is_rejected,
        test_invalid_execute_step_is_rejected,
        test_step_index_mismatch_is_rejected,
        test_state_snapshot_mismatch_is_rejected,
        test_missing_selected_tool_is_rejected,
        test_malformed_selected_tool_fails_before_execution,
        test_invalid_max_tool_calls_is_rejected,
        test_controlled_guarded_error_fails_step,
        test_result_state_error_fails_step,
        test_unexpected_execution_error_is_sanitized,
        test_source_preserves_execution_boundaries,
    )

    for test in tests:
        test()

    print(
        "Agent Runner execute_tool assertions "
        "passed (18/18)"
    )


if __name__ == "__main__":
    main()
