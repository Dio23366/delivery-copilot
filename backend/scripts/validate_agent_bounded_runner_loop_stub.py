from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.services.agent_runner_service import (
    AGENT_RUNNER_BOUNDED_LOOP_VERSION,
    BOUNDED_LOOP_STOP_TERMINAL,
    BOUNDED_LOOP_STOP_TRANSITION_CAP,
    BOUNDED_LOOP_STOP_UNIMPLEMENTED,
    BOUNDED_LOOP_STOP_WAITING,
    DEFAULT_MAX_TRANSITIONS_PER_CALL,
    AWAIT_FINAL_REVIEW_NODE,
    EVALUATE_EVIDENCE_NODE,
    EXECUTE_TOOL_NODE,
    FINAL_REVIEW_NODE,
    GENERATE_ANALYSIS_NODE,
    PERSIST_ANALYSIS_NODE,
    WAITING_FOR_FINAL_REVIEW_STATUS,
    REQUEST_CLARIFICATION_NODE,
    ROUTE_INVESTIGATION_NODE,
    SELECT_TOOL_NODE,
    AgentRunnerBoundedLoopError,
    AgentRunnerBoundedLoopResult,
    AgentRunnerService,
)


def make_run(
    *,
    node: str,
    status: str = "running",
    step_count: int = 1,
    tool_call_count: int = 0,
    state: dict[str, object] | None = None,
) -> SimpleNamespace:
    effective_state = {
        "max_steps": 16,
        "max_tool_calls": 3,
    }
    if state is not None:
        effective_state.update(state)

    return SimpleNamespace(
        run_id="run-loop-001",
        run_status=status,
        current_node=node,
        step_count=step_count,
        tool_call_count=tool_call_count,
        state_json=effective_state,
    )


def make_step(
    *,
    node: str,
    index: int,
    status: str = "running",
) -> SimpleNamespace:
    return SimpleNamespace(
        step_index=index,
        node_name=node,
        step_status=status,
    )


def advanced(
    run: SimpleNamespace,
    *,
    next_node: str,
    status: str = "running",
    step_status: str = "running",
) -> tuple[SimpleNamespace, SimpleNamespace]:
    next_index = run.step_count + 1
    next_run = make_run(
        node=next_node,
        status=status,
        step_count=next_index,
        tool_call_count=run.tool_call_count,
        state=dict(run.state_json),
    )
    next_step = make_step(
        node=next_node,
        index=next_index,
        status=step_status,
    )
    return next_run, next_step


class RecordingOrchestrationService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def complete_step_and_limit_run(
        self,
        db: object,
        **kwargs: object,
    ) -> tuple[SimpleNamespace, SimpleNamespace]:
        self.calls.append(
            {
                "db": db,
                **dict(kwargs),
            }
        )
        state = dict(kwargs["state_json"])
        limited_run = make_run(
            node="limit_exceeded",
            status="limit_exceeded",
            step_count=int(kwargs["step_index"]),
            tool_call_count=int(
                state.get("tool_call_count", 0)
            ),
            state=state,
        )
        completed_step = make_step(
            node=str(
                kwargs["output_state_json"].get(
                    "source_node",
                    "limit_exceeded",
                )
            ),
            index=int(kwargs["step_index"]),
            status="completed",
        )
        return limited_run, completed_step


def make_service() -> tuple[
    AgentRunnerService,
    RecordingOrchestrationService,
]:
    service = object.__new__(
        AgentRunnerService
    )
    orchestration = RecordingOrchestrationService()
    service._orchestration_service = orchestration

    service.advance_investigation_route = Mock()
    service.advance_select_tool = Mock()
    service.advance_execute_tool = Mock()
    service.advance_evaluate_evidence = Mock()
    service.advance_generate_analysis = Mock()
    service.advance_persist_analysis = Mock()
    service.advance_final_review = Mock()
    service.advance_request_clarification = Mock()

    return service, orchestration


def assert_loop_result(
    result: object,
) -> AgentRunnerBoundedLoopResult:
    assert isinstance(
        result,
        AgentRunnerBoundedLoopResult,
    )
    assert result.loop_version == (
        AGENT_RUNNER_BOUNDED_LOOP_VERSION
    )
    return result


def error_code(
    callback,
) -> str:
    try:
        callback()
    except AgentRunnerBoundedLoopError as exc:
        return exc.error_code
    raise AssertionError(
        "Expected AgentRunnerBoundedLoopError"
    )


def test_full_investigation_path_stops_waiting_for_final_review() -> None:
    service, orchestration = make_service()
    db = object()

    route_run = make_run(
        node=ROUTE_INVESTIGATION_NODE,
    )
    route_step = make_step(
        node=ROUTE_INVESTIGATION_NODE,
        index=1,
    )
    select_run, select_step = advanced(
        route_run,
        next_node=SELECT_TOOL_NODE,
    )
    execute_run, execute_step = advanced(
        select_run,
        next_node=EXECUTE_TOOL_NODE,
    )
    evaluate_run, evaluate_step = advanced(
        execute_run,
        next_node=EVALUATE_EVIDENCE_NODE,
    )
    analysis_run, analysis_step = advanced(
        evaluate_run,
        next_node=GENERATE_ANALYSIS_NODE,
    )
    persist_run, persist_step = advanced(
        analysis_run,
        next_node=PERSIST_ANALYSIS_NODE,
    )
    final_review_run, final_review_step = advanced(
        persist_run,
        next_node=FINAL_REVIEW_NODE,
        status="generating_analysis",
    )
    waiting_run = make_run(
        node=AWAIT_FINAL_REVIEW_NODE,
        status=WAITING_FOR_FINAL_REVIEW_STATUS,
        step_count=final_review_run.step_count + 1,
        state=dict(final_review_run.state_json),
    )
    await_final_review_step = make_step(
        node=AWAIT_FINAL_REVIEW_NODE,
        index=waiting_run.step_count,
        status="interrupted",
    )

    service.advance_investigation_route.return_value = (
        SimpleNamespace(
            agent_run=select_run,
            route_investigation_step=make_step(
                node=ROUTE_INVESTIGATION_NODE,
                index=1,
                status="completed",
            ),
            next_step=select_step,
        )
    )
    service.advance_select_tool.return_value = (
        SimpleNamespace(
            agent_run=execute_run,
            execute_tool_step=execute_step,
        )
    )
    service.advance_execute_tool.return_value = (
        SimpleNamespace(
            agent_run=evaluate_run,
            evaluate_evidence_step=evaluate_step,
        )
    )
    service.advance_evaluate_evidence.return_value = (
        SimpleNamespace(
            agent_run=analysis_run,
            evaluate_evidence_step=make_step(
                node=EVALUATE_EVIDENCE_NODE,
                index=4,
                status="completed",
            ),
            next_step=analysis_step,
        )
    )
    service.advance_generate_analysis.return_value = (
        SimpleNamespace(
            agent_run=persist_run,
            generate_analysis_step=make_step(
                node=GENERATE_ANALYSIS_NODE,
                index=5,
                status="completed",
            ),
            persist_analysis_step=persist_step,
        )
    )
    service.advance_persist_analysis.return_value = (
        SimpleNamespace(
            agent_run=final_review_run,
            persist_analysis_step=make_step(
                node=PERSIST_ANALYSIS_NODE,
                index=6,
                status="completed",
            ),
            analysis_log=SimpleNamespace(id=101),
            final_review_step=final_review_step,
        )
    )
    service.advance_final_review.return_value = (
        SimpleNamespace(
            agent_run=waiting_run,
            final_review_step=make_step(
                node=FINAL_REVIEW_NODE,
                index=7,
                status="completed",
            ),
            await_final_review_step=(
                await_final_review_step
            ),
        )
    )

    result = assert_loop_result(
        service.advance_investigation_until_boundary(
            db,
            agent_run=route_run,
            current_step=route_step,
        )
    )

    assert result.agent_run is waiting_run
    assert result.current_step is await_final_review_step
    assert result.transition_count == 7
    assert result.stop_reason == BOUNDED_LOOP_STOP_WAITING
    assert result.visited_nodes == (
        ROUTE_INVESTIGATION_NODE,
        SELECT_TOOL_NODE,
        EXECUTE_TOOL_NODE,
        EVALUATE_EVIDENCE_NODE,
        GENERATE_ANALYSIS_NODE,
        PERSIST_ANALYSIS_NODE,
        FINAL_REVIEW_NODE,
    )
    service.advance_generate_analysis.assert_called_once_with(
        db,
        agent_run=analysis_run,
        generate_analysis_step=analysis_step,
    )
    service.advance_persist_analysis.assert_called_once_with(
        db,
        agent_run=persist_run,
        persist_analysis_step=persist_step,
    )
    service.advance_final_review.assert_called_once_with(
        db,
        agent_run=final_review_run,
        final_review_step=final_review_step,
    )
    assert not orchestration.calls

def test_clarification_path_stops_waiting() -> None:
    service, _ = make_service()
    db = object()

    evaluate_run = make_run(
        node=EVALUATE_EVIDENCE_NODE,
        step_count=2,
    )
    evaluate_step = make_step(
        node=EVALUATE_EVIDENCE_NODE,
        index=2,
    )
    request_run, request_step = advanced(
        evaluate_run,
        next_node=REQUEST_CLARIFICATION_NODE,
    )
    waiting_run = make_run(
        node=REQUEST_CLARIFICATION_NODE,
        status="waiting_for_clarification",
        step_count=request_run.step_count,
        state=dict(request_run.state_json),
    )
    interrupted_step = make_step(
        node=REQUEST_CLARIFICATION_NODE,
        index=request_step.step_index,
        status="interrupted",
    )

    service.advance_evaluate_evidence.return_value = (
        SimpleNamespace(
            agent_run=request_run,
            evaluate_evidence_step=make_step(
                node=EVALUATE_EVIDENCE_NODE,
                index=2,
                status="completed",
            ),
            next_step=request_step,
        )
    )
    service.advance_request_clarification.return_value = (
        SimpleNamespace(
            agent_run=waiting_run,
            request_clarification_step=interrupted_step,
        )
    )

    result = assert_loop_result(
        service.advance_investigation_until_boundary(
            db,
            agent_run=evaluate_run,
            current_step=evaluate_step,
        )
    )

    assert result.agent_run is waiting_run
    assert result.current_step is interrupted_step
    assert result.transition_count == 2
    assert result.stop_reason == BOUNDED_LOOP_STOP_WAITING
    assert result.visited_nodes == (
        EVALUATE_EVIDENCE_NODE,
        REQUEST_CLARIFICATION_NODE,
    )


def test_existing_limit_result_stops_terminal() -> None:
    service, _ = make_service()
    db = object()

    route_run = make_run(
        node=ROUTE_INVESTIGATION_NODE,
    )
    route_step = make_step(
        node=ROUTE_INVESTIGATION_NODE,
        index=1,
    )
    limited_run = make_run(
        node="limit_exceeded",
        status="limit_exceeded",
    )
    completed_step = make_step(
        node=ROUTE_INVESTIGATION_NODE,
        index=1,
        status="completed",
    )

    service.advance_investigation_route.return_value = (
        SimpleNamespace(
            agent_run=limited_run,
            route_investigation_step=completed_step,
            next_step=None,
        )
    )

    result = assert_loop_result(
        service.advance_investigation_until_boundary(
            db,
            agent_run=route_run,
            current_step=route_step,
        )
    )

    assert result.agent_run is limited_run
    assert result.current_step is completed_step
    assert result.transition_count == 1
    assert result.stop_reason == BOUNDED_LOOP_STOP_TERMINAL


def assert_budget_terminal(
    *,
    node: str,
    step_count: int,
    tool_call_count: int,
    state: dict[str, object],
    expected_error_code: str,
) -> None:
    service, orchestration = make_service()
    db = object()
    run = make_run(
        node=node,
        step_count=step_count,
        tool_call_count=tool_call_count,
        state=state,
    )
    step = make_step(
        node=node,
        index=step_count,
    )

    result = assert_loop_result(
        service.advance_investigation_until_boundary(
            db,
            agent_run=run,
            current_step=step,
        )
    )

    assert result.stop_reason == BOUNDED_LOOP_STOP_TERMINAL
    assert result.transition_count == 1
    assert result.visited_nodes == (node,)
    assert len(orchestration.calls) == 1
    call = orchestration.calls[0]
    assert call["error_code"] == expected_error_code
    assert call["step_index"] == step_count
    assert call["state_json"]["max_steps"] == (
        state.get("max_steps", 16)
    )
    assert call["state_json"]["max_tool_calls"] == (
        state.get("max_tool_calls", 3)
    )

    service.advance_investigation_route.assert_not_called()
    service.advance_select_tool.assert_not_called()
    service.advance_execute_tool.assert_not_called()
    service.advance_evaluate_evidence.assert_not_called()
    service.advance_generate_analysis.assert_not_called()
    service.advance_request_clarification.assert_not_called()


def test_max_steps_precheck_terminalizes() -> None:
    assert_budget_terminal(
        node=SELECT_TOOL_NODE,
        step_count=4,
        tool_call_count=1,
        state={
            "max_steps": 4,
            "max_tool_calls": 3,
        },
        expected_error_code="max_steps_reached",
    )


def test_max_tool_calls_precheck_select() -> None:
    assert_budget_terminal(
        node=SELECT_TOOL_NODE,
        step_count=2,
        tool_call_count=3,
        state={
            "max_steps": 16,
            "max_tool_calls": 3,
        },
        expected_error_code="max_tool_calls_reached",
    )


def test_max_tool_calls_precheck_execute() -> None:
    assert_budget_terminal(
        node=EXECUTE_TOOL_NODE,
        step_count=3,
        tool_call_count=3,
        state={
            "max_steps": 16,
            "max_tool_calls": 3,
        },
        expected_error_code="max_tool_calls_reached",
    )


def test_transition_cap_stops_without_extra_dispatch() -> None:
    service, _ = make_service()
    db = object()

    route_run = make_run(
        node=ROUTE_INVESTIGATION_NODE,
    )
    route_step = make_step(
        node=ROUTE_INVESTIGATION_NODE,
        index=1,
    )
    select_run, select_step = advanced(
        route_run,
        next_node=SELECT_TOOL_NODE,
    )
    execute_run, execute_step = advanced(
        select_run,
        next_node=EXECUTE_TOOL_NODE,
    )

    service.advance_investigation_route.return_value = (
        SimpleNamespace(
            agent_run=select_run,
            route_investigation_step=route_step,
            next_step=select_step,
        )
    )
    service.advance_select_tool.return_value = (
        SimpleNamespace(
            agent_run=execute_run,
            execute_tool_step=execute_step,
        )
    )

    result = assert_loop_result(
        service.advance_investigation_until_boundary(
            db,
            agent_run=route_run,
            current_step=route_step,
            max_transitions=2,
        )
    )

    assert result.agent_run is execute_run
    assert result.current_step is execute_step
    assert result.transition_count == 2
    assert result.stop_reason == (
        BOUNDED_LOOP_STOP_TRANSITION_CAP
    )
    assert result.visited_nodes == (
        ROUTE_INVESTIGATION_NODE,
        SELECT_TOOL_NODE,
    )
    service.advance_execute_tool.assert_not_called()


def test_invalid_transition_cap_rejected() -> None:
    service, _ = make_service()
    run = make_run(
        node=ROUTE_INVESTIGATION_NODE,
    )
    step = make_step(
        node=ROUTE_INVESTIGATION_NODE,
        index=1,
    )

    for value in (
        True,
        0,
        -1,
        1.5,
        "2",
    ):
        try:
            service.advance_investigation_until_boundary(
                object(),
                agent_run=run,
                current_step=step,
                max_transitions=value,
            )
        except ValueError as exc:
            assert "positive integer" in str(exc)
        else:
            raise AssertionError(
                f"Invalid max_transitions accepted: {value!r}"
            )


def test_initial_waiting_and_terminal_return_immediately() -> None:
    service, _ = make_service()

    waiting = service.advance_investigation_until_boundary(
        object(),
        agent_run=make_run(
            node=REQUEST_CLARIFICATION_NODE,
            status="waiting_for_clarification",
        ),
        current_step=None,
    )
    assert waiting.stop_reason == BOUNDED_LOOP_STOP_WAITING
    assert waiting.transition_count == 0

    terminal = service.advance_investigation_until_boundary(
        object(),
        agent_run=make_run(
            node="limit_exceeded",
            status="limit_exceeded",
        ),
        current_step=None,
    )
    assert terminal.stop_reason == BOUNDED_LOOP_STOP_TERMINAL
    assert terminal.transition_count == 0


def test_final_review_status_pairing_fails_closed() -> None:
    service, _ = make_service()

    assert error_code(
        lambda: service.advance_investigation_until_boundary(
            object(),
            agent_run=make_run(
                node=GENERATE_ANALYSIS_NODE,
                status="generating_analysis",
            ),
            current_step=make_step(
                node=GENERATE_ANALYSIS_NODE,
                index=1,
            ),
        )
    ) == "run_status_node_mismatch"

    assert error_code(
        lambda: service.advance_investigation_until_boundary(
            object(),
            agent_run=make_run(
                node=FINAL_REVIEW_NODE,
                status="running",
            ),
            current_step=make_step(
                node=FINAL_REVIEW_NODE,
                index=1,
            ),
        )
    ) == "run_status_node_mismatch"


def test_unknown_status_and_nodes_fail_closed() -> None:
    service, _ = make_service()

    assert error_code(
        lambda: service.advance_investigation_until_boundary(
            object(),
            agent_run=make_run(
                node=ROUTE_INVESTIGATION_NODE,
                status="created",
            ),
            current_step=None,
        )
    ) == "unsupported_run_status"

    assert error_code(
        lambda: service.advance_investigation_until_boundary(
            object(),
            agent_run=make_run(
                node=" unknown ",
            ),
            current_step=make_step(
                node=" unknown ",
                index=1,
            ),
        )
    ) == "invalid_current_node"

    assert error_code(
        lambda: service.advance_investigation_until_boundary(
            object(),
            agent_run=make_run(
                node="mystery_node",
            ),
            current_step=make_step(
                node="mystery_node",
                index=1,
            ),
        )
    ) == "unsupported_current_node"


def test_current_step_contracts_fail_closed() -> None:
    service, _ = make_service()
    run = make_run(
        node=SELECT_TOOL_NODE,
        step_count=2,
    )

    assert error_code(
        lambda: service.advance_investigation_until_boundary(
            object(),
            agent_run=run,
            current_step=None,
        )
    ) == "missing_current_step"

    assert error_code(
        lambda: service.advance_investigation_until_boundary(
            object(),
            agent_run=run,
            current_step=make_step(
                node=SELECT_TOOL_NODE,
                index=1,
            ),
        )
    ) == "stale_current_step"

    assert error_code(
        lambda: service.advance_investigation_until_boundary(
            object(),
            agent_run=run,
            current_step=make_step(
                node=EXECUTE_TOOL_NODE,
                index=2,
            ),
        )
    ) == "current_step_node_mismatch"

    assert error_code(
        lambda: service.advance_investigation_until_boundary(
            object(),
            agent_run=run,
            current_step=make_step(
                node=SELECT_TOOL_NODE,
                index=2,
                status="completed",
            ),
        )
    ) == "current_step_not_running"


def test_invalid_run_contracts_fail_closed() -> None:
    service, _ = make_service()

    invalid_run_id = make_run(
        node=SELECT_TOOL_NODE,
    )
    invalid_run_id.run_id = " "
    assert error_code(
        lambda: service.advance_investigation_until_boundary(
            object(),
            agent_run=invalid_run_id,
            current_step=make_step(
                node=SELECT_TOOL_NODE,
                index=1,
            ),
        )
    ) == "invalid_run_id"

    invalid_state = make_run(
        node=SELECT_TOOL_NODE,
    )
    invalid_state.state_json = None
    assert error_code(
        lambda: service.advance_investigation_until_boundary(
            object(),
            agent_run=invalid_state,
            current_step=make_step(
                node=SELECT_TOOL_NODE,
                index=1,
            ),
        )
    ) == "invalid_agent_state"

    invalid_counter = make_run(
        node=SELECT_TOOL_NODE,
    )
    invalid_counter.tool_call_count = True
    assert error_code(
        lambda: service.advance_investigation_until_boundary(
            object(),
            agent_run=invalid_counter,
            current_step=make_step(
                node=SELECT_TOOL_NODE,
                index=1,
            ),
        )
    ) == "invalid_tool_call_count"

    for field_name in (
        "max_steps",
        "max_tool_calls",
    ):
        invalid_limit = make_run(
            node=SELECT_TOOL_NODE,
            state={field_name: 0},
        )
        assert error_code(
            lambda invalid_limit=invalid_limit: (
                service.advance_investigation_until_boundary(
                    object(),
                    agent_run=invalid_limit,
                    current_step=make_step(
                        node=SELECT_TOOL_NODE,
                        index=1,
                    ),
                )
            )
        ) == f"invalid_{field_name}"


def test_stall_detection_fails_closed() -> None:
    service, _ = make_service()
    run = make_run(
        node=ROUTE_INVESTIGATION_NODE,
    )
    step = make_step(
        node=ROUTE_INVESTIGATION_NODE,
        index=1,
    )

    service.advance_investigation_route.return_value = (
        SimpleNamespace(
            agent_run=run,
            route_investigation_step=step,
            next_step=step,
        )
    )

    assert error_code(
        lambda: service.advance_investigation_until_boundary(
            object(),
            agent_run=run,
            current_step=step,
        )
    ) == "runner_loop_stalled"


def test_source_contract() -> None:
    source = inspect.getsource(
        AgentRunnerService
        .advance_investigation_until_boundary
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

    assert "db.commit" not in calls
    assert "db.rollback" not in calls
    assert "db.refresh" not in calls
    assert "db.flush" not in calls

    assert calls.count(
        "self.advance_investigation_route"
    ) == 1
    assert calls.count(
        "self.advance_select_tool"
    ) == 1
    assert calls.count(
        "self.advance_execute_tool"
    ) == 1
    assert calls.count(
        "self.advance_evaluate_evidence"
    ) == 1
    assert calls.count(
        "self.advance_generate_analysis"
    ) == 1
    assert calls.count(
        "self.advance_persist_analysis"
    ) == 1
    assert calls.count(
        "self.advance_final_review"
    ) == 1
    assert calls.count(
        "self.advance_request_clarification"
    ) == 1
    assert calls.count(
        "self._orchestration_service."
        "complete_step_and_limit_run"
    ) == 2

    assert "while True" in source
    assert "max_transitions" in source
    assert "seen_signatures" in source
    assert "BOUNDED_LOOP_UNIMPLEMENTED_NODES" in source
    assert "GENERATING_ANALYSIS_STATUS" in source
    assert "run_status_node_mismatch" in source
    assert DEFAULT_MAX_TRANSITIONS_PER_CALL == 16

    runner_path = Path(
        inspect.getsourcefile(
            AgentRunnerService
        )
        or ""
    )
    ast.parse(
        runner_path.read_text(
            encoding="utf-8",
        )
    )


def main() -> None:
    tests = (
        test_full_investigation_path_stops_waiting_for_final_review,
        test_clarification_path_stops_waiting,
        test_existing_limit_result_stops_terminal,
        test_max_steps_precheck_terminalizes,
        test_max_tool_calls_precheck_select,
        test_max_tool_calls_precheck_execute,
        test_transition_cap_stops_without_extra_dispatch,
        test_invalid_transition_cap_rejected,
        test_initial_waiting_and_terminal_return_immediately,
        test_final_review_status_pairing_fails_closed,
        test_unknown_status_and_nodes_fail_closed,
        test_current_step_contracts_fail_closed,
        test_invalid_run_contracts_fail_closed,
        test_stall_detection_fails_closed,
        test_source_contract,
    )

    for test in tests:
        test()

    print(
        "Agent bounded Runner loop assertions passed"
    )
    print(f"passed_count={len(tests)}")


if __name__ == "__main__":
    main()
