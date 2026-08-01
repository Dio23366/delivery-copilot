from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import inspect
import sys
from typing import Callable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.agent_investigation_routing_service import (
    AgentInvestigationRoutingOutcome,
    NEXT_NODE_EVALUATE_EVIDENCE,
    NEXT_NODE_FAILED,
    NEXT_NODE_LIMIT_EXCEEDED,
    NEXT_NODE_SELECT_TOOL,
)
from app.services.agent_runner_service import (
    AGENT_RUNNER_INVESTIGATION_ROUTE_VERSION,
    EVALUATE_EVIDENCE_NODE,
    ROUTE_INVESTIGATION_NODE,
    SELECT_TOOL_NODE,
    AgentRunnerInvestigationRouteBlockedError,
    AgentRunnerInvestigationRouteResult,
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


class RecordingRoutingService:
    def __init__(
        self,
        *,
        outcome: AgentInvestigationRoutingOutcome,
    ) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, object]] = []

    def route(
        self,
        state: object,
        *,
        step_count: int,
        tool_call_count: int,
    ) -> AgentInvestigationRoutingOutcome:
        self.calls.append(
            {
                "state": dict(state),
                "step_count": step_count,
                "tool_call_count": tool_call_count,
            }
        )
        return self.outcome


class RecordingOrchestrationService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def complete_step_and_advance_run(
        self,
        db: object,
        **kwargs: object,
    ) -> tuple[object, object, object]:
        self.calls.append(
            {
                "operation": "advance",
                "db": db,
                **dict(kwargs),
            }
        )
        advanced_run = SimpleNamespace(
            run_id=kwargs["run_id"],
            run_status="running",
            current_node=kwargs["next_node"],
            state_json=dict(kwargs["state_json"]),
        )
        completed_step = SimpleNamespace(
            step_index=kwargs["step_index"],
            node_name=ROUTE_INVESTIGATION_NODE,
            step_status="completed",
        )
        next_step = SimpleNamespace(
            step_index=int(kwargs["step_index"]) + 1,
            node_name=kwargs["next_node"],
            step_status="running",
        )
        return advanced_run, completed_step, next_step

    def complete_step_and_limit_run(
        self,
        db: object,
        **kwargs: object,
    ) -> tuple[object, object]:
        self.calls.append(
            {
                "operation": "limit",
                "db": db,
                **dict(kwargs),
            }
        )
        limited_run = SimpleNamespace(
            run_id=kwargs["run_id"],
            run_status="limit_exceeded",
            current_node="limit_exceeded",
            state_json=dict(kwargs["state_json"]),
            error_code=kwargs["error_code"],
            error_message=kwargs["error_message"],
        )
        completed_step = SimpleNamespace(
            step_index=kwargs["step_index"],
            node_name=ROUTE_INVESTIGATION_NODE,
            step_status="completed",
            output_state_json=dict(
                kwargs["output_state_json"]
            ),
        )
        return limited_run, completed_step


def make_outcome(
    *,
    next_node: str = NEXT_NODE_SELECT_TOOL,
    reason: str = "Controlled route selected.",
    error_code: str | None = None,
    max_steps: int = 16,
    max_tool_calls: int = 3,
) -> AgentInvestigationRoutingOutcome:
    return AgentInvestigationRoutingOutcome(
        next_node=next_node,
        reason=reason,
        max_steps=max_steps,
        max_tool_calls=max_tool_calls,
        error_code=error_code,
    )


def make_run(
    *,
    run_status: str = "running",
    current_node: str = ROUTE_INVESTIGATION_NODE,
    step_count: int = 4,
    tool_call_count: int = 0,
    state_json: dict[str, object] | None = None,
) -> object:
    effective_state = (
        dict(state_json)
        if state_json is not None
        else {
            "triage_result": {
                "issue_type": "API",
                "issue_subtype": "authentication",
            },
            "triage_confirmed": True,
        }
    )
    return SimpleNamespace(
        run_id="run-001",
        run_status=run_status,
        current_node=current_node,
        step_count=step_count,
        tool_call_count=tool_call_count,
        state_json=effective_state,
    )


def make_step(
    *,
    step_index: int = 4,
    node_name: str = ROUTE_INVESTIGATION_NODE,
    step_status: str = "running",
    input_state_json: dict[str, object] | None = None,
) -> object:
    effective_state = (
        dict(input_state_json)
        if input_state_json is not None
        else {
            "triage_result": {
                "issue_type": "API",
                "issue_subtype": "authentication",
            },
            "triage_confirmed": True,
        }
    )
    return SimpleNamespace(
        step_index=step_index,
        node_name=node_name,
        step_status=step_status,
        input_state_json=effective_state,
    )


def build_runner(
    *,
    outcome: AgentInvestigationRoutingOutcome | None = None,
) -> tuple[
    AgentRunnerService,
    RecordingRoutingService,
    RecordingOrchestrationService,
]:
    routing = RecordingRoutingService(
        outcome=(
            outcome
            if outcome is not None
            else make_outcome()
        )
    )
    orchestration = RecordingOrchestrationService()
    runner = AgentRunnerService(
        orchestration_service=orchestration,
        investigation_routing_service=routing,
    )
    return runner, routing, orchestration


def call(
    runner: AgentRunnerService,
    *,
    db: object | None = None,
    agent_run: object | None = None,
    route_step: object | None = None,
) -> AgentRunnerInvestigationRouteResult:
    effective_db = db if db is not None else object()
    effective_run = (
        agent_run
        if agent_run is not None
        else make_run()
    )
    effective_step = (
        route_step
        if route_step is not None
        else make_step()
    )
    return runner.advance_investigation_route(
        effective_db,
        agent_run=effective_run,
        route_investigation_step=effective_step,
    )


def test_version_and_nodes_are_frozen() -> None:
    assert AGENT_RUNNER_INVESTIGATION_ROUTE_VERSION == (
        "agent_runner_investigation_route_v0.1"
    )
    assert ROUTE_INVESTIGATION_NODE == "route_investigation"
    assert SELECT_TOOL_NODE == NEXT_NODE_SELECT_TOOL
    assert EVALUATE_EVIDENCE_NODE == (
        NEXT_NODE_EVALUATE_EVIDENCE
    )
    print("PASS: Runner investigation route contract is frozen")


def test_select_tool_route_advances_atomically() -> None:
    runner, routing, orchestration = build_runner()
    db = object()

    result = call(runner, db=db)

    assert isinstance(
        result,
        AgentRunnerInvestigationRouteResult,
    )
    assert result.routing_outcome.next_node == (
        SELECT_TOOL_NODE
    )
    assert result.next_step.node_name == SELECT_TOOL_NODE
    assert len(routing.calls) == 1
    assert len(orchestration.calls) == 1
    assert orchestration.calls[0]["db"] is db
    print("PASS: select_tool route advances through Orchestration")


def test_evaluate_evidence_route_is_supported() -> None:
    runner, _, orchestration = build_runner(
        outcome=make_outcome(
            next_node=NEXT_NODE_EVALUATE_EVIDENCE,
        )
    )

    result = call(runner)

    assert result.next_step.node_name == (
        EVALUATE_EVIDENCE_NODE
    )
    assert orchestration.calls[0]["next_node"] == (
        EVALUATE_EVIDENCE_NODE
    )
    print("PASS: evaluate_evidence route is supported")


def test_persisted_counts_feed_routing() -> None:
    runner, routing, _ = build_runner()
    run = make_run(
        step_count=7,
        tool_call_count=2,
    )
    step = make_step(step_index=7)

    call(
        runner,
        agent_run=run,
        route_step=step,
    )

    payload = routing.calls[0]
    assert payload["step_count"] == 7
    assert payload["tool_call_count"] == 2
    print("PASS: persisted counts feed routing exactly")


def test_route_limits_update_state() -> None:
    runner, _, orchestration = build_runner(
        outcome=make_outcome(
            max_steps=20,
            max_tool_calls=4,
        )
    )

    result = call(runner)

    assert result.state_json["max_steps"] == 20
    assert result.state_json["max_tool_calls"] == 4
    assert orchestration.calls[0]["state_json"][
        "max_steps"
    ] == 20
    assert orchestration.calls[0]["state_json"][
        "max_tool_calls"
    ] == 4
    print("PASS: resolved limits update persisted state")


def test_route_output_is_controlled() -> None:
    runner, _, orchestration = build_runner()

    call(runner)

    output = orchestration.calls[0][
        "output_state_json"
    ]
    assert output == {
        "routing_version": (
            "agent_investigation_routing_v0.1"
        ),
        "next_node": SELECT_TOOL_NODE,
        "reason": "Controlled route selected.",
        "error_code": None,
        "max_steps": 16,
        "max_tool_calls": 3,
    }
    print("PASS: route Step output is controlled")


def test_result_preserves_advanced_objects() -> None:
    runner, _, _ = build_runner()

    result = call(runner)

    assert result.agent_run.current_node == (
        SELECT_TOOL_NODE
    )
    assert result.route_investigation_step.step_status == (
        "completed"
    )
    assert result.next_step.step_status == "running"
    print("PASS: route result preserves advanced objects")


def test_invalid_run_status_is_rejected() -> None:
    runner, routing, orchestration = build_runner()

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            agent_run=make_run(run_status="created"),
        ),
    )

    assert "status" in str(error)
    assert routing.calls == []
    assert orchestration.calls == []
    print("PASS: invalid Run status is rejected")


def test_invalid_current_node_is_rejected() -> None:
    runner, routing, orchestration = build_runner()

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
    assert routing.calls == []
    assert orchestration.calls == []
    print("PASS: invalid Run current node is rejected")


def test_invalid_route_step_is_rejected() -> None:
    invalid_steps = (
        make_step(node_name="select_tool"),
        make_step(step_status="interrupted"),
    )

    for invalid_step in invalid_steps:
        runner, routing, orchestration = build_runner()
        expect_raises(
            ValueError,
            lambda invalid_step=invalid_step: call(
                runner,
                route_step=invalid_step,
            ),
        )
        assert routing.calls == []
        assert orchestration.calls == []

    print("PASS: invalid route Step node or status is rejected")


def test_step_index_mismatch_is_rejected() -> None:
    runner, routing, orchestration = build_runner()

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            agent_run=make_run(step_count=5),
            route_step=make_step(step_index=4),
        ),
    )

    assert "latest Step" in str(error)
    assert routing.calls == []
    assert orchestration.calls == []
    print("PASS: non-latest route Step is rejected")


def test_state_snapshot_mismatch_is_rejected() -> None:
    runner, routing, orchestration = build_runner()

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            route_step=make_step(
                input_state_json={
                    "triage_result": {
                        "issue_type": "Data",
                    },
                    "triage_confirmed": True,
                }
            ),
        ),
    )

    assert "state snapshot" in str(error)
    assert routing.calls == []
    assert orchestration.calls == []
    print("PASS: mismatched Step state snapshot is rejected")


def test_failed_route_is_blocked_before_advancement() -> None:
    blocked = make_outcome(
        next_node=NEXT_NODE_FAILED,
        reason="Confirmed triage is missing.",
        error_code="missing_triage_result",
    )
    runner, _, orchestration = build_runner(
        outcome=blocked
    )

    error = expect_raises(
        AgentRunnerInvestigationRouteBlockedError,
        lambda: call(runner),
    )

    assert error.error_code == "missing_triage_result"
    assert error.routing_outcome is blocked
    assert orchestration.calls == []
    print("PASS: failed route is blocked before advancement")


def test_limit_route_terminalizes_atomically() -> None:
    limited = make_outcome(
        next_node=NEXT_NODE_LIMIT_EXCEEDED,
        reason="The max_steps limit was reached.",
        error_code="max_steps_reached",
        max_steps=4,
        max_tool_calls=3,
    )
    runner, routing, orchestration = build_runner(
        outcome=limited
    )
    db = object()

    result = call(runner, db=db)

    assert isinstance(
        result,
        AgentRunnerInvestigationRouteResult,
    )
    assert result.agent_run.run_status == (
        "limit_exceeded"
    )
    assert result.agent_run.current_node == (
        "limit_exceeded"
    )
    assert result.route_investigation_step.step_status == (
        "completed"
    )
    assert result.next_step is None
    assert result.routing_outcome is limited
    assert len(routing.calls) == 1
    assert len(orchestration.calls) == 1

    payload = orchestration.calls[0]
    assert payload["operation"] == "limit"
    assert payload["db"] is db
    assert payload["run_id"] == "run-001"
    assert payload["step_index"] == 4
    assert payload["error_code"] == "max_steps_reached"
    assert payload["error_message"] == (
        "The max_steps limit was reached."
    )
    assert payload["state_json"]["max_steps"] == 4
    assert payload["state_json"]["max_tool_calls"] == 3
    assert payload["output_state_json"] == {
        "routing_version": (
            "agent_investigation_routing_v0.1"
        ),
        "next_node": NEXT_NODE_LIMIT_EXCEEDED,
        "reason": "The max_steps limit was reached.",
        "error_code": "max_steps_reached",
        "max_steps": 4,
        "max_tool_calls": 3,
    }
    print("PASS: limit route terminalizes through Orchestration")


def test_source_preserves_transaction_boundary() -> None:
    source = inspect.getsource(
        AgentRunnerService.advance_investigation_route
    )

    forbidden = (
        "db.commit(",
        "db.rollback(",
        "db.flush(",
        "db.refresh(",
        "agent_persistence_service",
        "AgentGuardedToolExecutionService",
        "execute_once(",
        "selected_tool",
        "tool_results",
        "retrieved_evidence",
    )
    found = [
        token for token in forbidden
        if token in source
    ]
    assert not found, found
    assert "complete_step_and_advance_run(" in source
    assert "complete_step_and_limit_run(" in source
    assert "NEXT_NODE_LIMIT_EXCEEDED" in source
    assert ".route(" in source
    print("PASS: Runner route preserves transaction boundary")


def main() -> None:
    tests = (
        test_version_and_nodes_are_frozen,
        test_select_tool_route_advances_atomically,
        test_evaluate_evidence_route_is_supported,
        test_persisted_counts_feed_routing,
        test_route_limits_update_state,
        test_route_output_is_controlled,
        test_result_preserves_advanced_objects,
        test_invalid_run_status_is_rejected,
        test_invalid_current_node_is_rejected,
        test_invalid_route_step_is_rejected,
        test_step_index_mismatch_is_rejected,
        test_state_snapshot_mismatch_is_rejected,
        test_failed_route_is_blocked_before_advancement,
        test_limit_route_terminalizes_atomically,
        test_source_preserves_transaction_boundary,
    )

    for test in tests:
        test()

    print(
        "Agent Runner investigation route assertions "
        "passed (15/15)"
    )


if __name__ == "__main__":
    main()
