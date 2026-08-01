from __future__ import annotations

from pathlib import Path
from types import MappingProxyType, SimpleNamespace
import inspect
import sys
from typing import Callable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.agent_runner_service import (
    AGENT_RUNNER_SELECT_TOOL_VERSION,
    EXECUTE_TOOL_NODE,
    SELECT_TOOL_NODE,
    AgentRunnerSelectToolResult,
    AgentRunnerService,
)
from app.services.agent_tool_selection_service import (
    AGENT_TOOL_SELECTION_VERSION,
    AgentToolSelectionDecision,
    AgentToolSelectionError,
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
        "graph_version": "agent_mvp_v0.1",
        "triage_confirmed": True,
        "triage_result": {
            "issue_type": "API",
            "subtype": "authentication",
            "severity": "high",
            "confidence": 0.95,
            "reason": "Authentication evidence is present.",
        },
        "issue_context": {
            "issue_id": 17,
            "issue_title": "Customer API failure",
            "issue_description": "Token rejected with 401",
            "issue_type": "API",
            "severity": "high",
            "status": "investigating",
            "owner": "Engineering",
            "project_name": "Runner Project",
            "project_status": "active",
            "delivery_stage": "Implementation",
            "risk_level": "medium",
            "health": "at_risk",
            "customer_name": "Runner Customer",
            "customer_industry": "Technology",
            "customer_contact": "runner@example.com",
        },
        "tool_results": [],
        "max_steps": 16,
        "max_tool_calls": 3,
    }


def make_decision() -> AgentToolSelectionDecision:
    return AgentToolSelectionDecision(
        tool_name="search_knowledge",
        tool_version="grounded_retrieval_v1",
        arguments=MappingProxyType({"issue_id": 17}),
        call_identity="search_knowledge:" + ("a" * 64),
        confidence=0.92,
        reason=(
            "Grounded knowledge is the highest-ranked "
            "evidence source."
        ),
    )


class RecordingSelectionService:
    def __init__(
        self,
        *,
        decision: AgentToolSelectionDecision | None = None,
        error: Exception | None = None,
    ) -> None:
        self.decision = (
            decision
            if decision is not None
            else make_decision()
        )
        self.error = error
        self.states: list[dict[str, object]] = []

    def select(
        self,
        state: object,
    ) -> AgentToolSelectionDecision:
        self.states.append(dict(state))
        if self.error is not None:
            raise self.error
        return self.decision


class RecordingOrchestrationService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

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
            node_name=SELECT_TOOL_NODE,
            step_status="completed",
            output_state_json=dict(
                kwargs["output_state_json"]
            ),
        )
        next_step = SimpleNamespace(
            step_index=int(kwargs["step_index"]) + 1,
            node_name=kwargs["next_node"],
            step_status="running",
            input_state_json=dict(kwargs["state_json"]),
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
            node_name=SELECT_TOOL_NODE,
            step_status="failed",
            error_code=kwargs["error_code"],
        )


def make_run(
    *,
    run_status: str = "running",
    current_node: str = SELECT_TOOL_NODE,
    step_count: int = 5,
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
    step_index: int = 5,
    node_name: str = SELECT_TOOL_NODE,
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
    decision: AgentToolSelectionDecision | None = None,
    error: Exception | None = None,
) -> tuple[
    AgentRunnerService,
    RecordingSelectionService,
    RecordingOrchestrationService,
]:
    selection = RecordingSelectionService(
        decision=decision,
        error=error,
    )
    orchestration = RecordingOrchestrationService()
    runner = AgentRunnerService(
        orchestration_service=orchestration,
        tool_selection_service=selection,
    )
    return runner, selection, orchestration


def call(
    runner: AgentRunnerService,
    *,
    db: object | None = None,
    agent_run: object | None = None,
    select_step: object | None = None,
) -> AgentRunnerSelectToolResult:
    return runner.advance_select_tool(
        db if db is not None else object(),
        agent_run=(
            agent_run
            if agent_run is not None
            else make_run()
        ),
        select_tool_step=(
            select_step
            if select_step is not None
            else make_step()
        ),
    )


def test_version_and_nodes_are_frozen() -> None:
    assert AGENT_RUNNER_SELECT_TOOL_VERSION == (
        "agent_runner_select_tool_v0.1"
    )
    assert SELECT_TOOL_NODE == "select_tool"
    assert EXECUTE_TOOL_NODE == "execute_tool"
    print("PASS: Runner select_tool contract is frozen")


def test_happy_path_advances_atomically() -> None:
    runner, selection, orchestration = build_runner()
    db = object()

    result = call(runner, db=db)

    assert isinstance(result, AgentRunnerSelectToolResult)
    assert result.agent_run.current_node == EXECUTE_TOOL_NODE
    assert result.execute_tool_step.node_name == EXECUTE_TOOL_NODE
    assert len(selection.states) == 1
    assert len(orchestration.calls) == 1
    assert orchestration.calls[0][1]["db"] is db
    print("PASS: select_tool advances atomically")


def test_persisted_state_feeds_selection_exactly() -> None:
    runner, selection, _ = build_runner()
    state = base_state()
    state["preserved_value"] = "keep-me"

    call(
        runner,
        agent_run=make_run(state_json=state),
        select_step=make_step(input_state_json=state),
    )

    assert selection.states == [state]
    print("PASS: persisted state feeds Tool Selection exactly")


def test_selected_tool_state_is_controlled() -> None:
    runner, _, orchestration = build_runner()

    result = call(runner)

    selected = result.state_json["selected_tool"]
    assert selected == make_decision().as_dict()

    method, payload = orchestration.calls[0]
    assert method == "complete_step_and_advance_run"
    assert payload["next_node"] == EXECUTE_TOOL_NODE
    assert payload["state_json"]["selected_tool"] == selected
    assert payload["output_state_json"] == {
        "selected_tool": selected
    }
    print("PASS: selected_tool state update is controlled")


def test_original_state_is_not_mutated() -> None:
    runner, _, _ = build_runner()
    state = base_state()
    original = dict(state)

    result = call(
        runner,
        agent_run=make_run(state_json=state),
        select_step=make_step(input_state_json=state),
    )

    assert state == original
    assert "selected_tool" not in state
    assert "selected_tool" in result.state_json
    print("PASS: Runner builds a new persisted state")


def test_result_preserves_advanced_objects() -> None:
    runner, _, _ = build_runner()

    result = call(runner)

    assert result.select_tool_step.step_status == "completed"
    assert result.execute_tool_step.step_status == "running"
    assert result.selection_decision.tool_name == "search_knowledge"
    print("PASS: select_tool result preserves advanced objects")


def test_invalid_run_status_is_rejected() -> None:
    runner, selection, orchestration = build_runner()

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            agent_run=make_run(run_status="created"),
        ),
    )

    assert "status" in str(error)
    assert selection.states == []
    assert orchestration.calls == []
    print("PASS: invalid Run status is rejected")


def test_invalid_current_node_is_rejected() -> None:
    runner, selection, orchestration = build_runner()

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            agent_run=make_run(
                current_node="route_investigation"
            ),
        ),
    )

    assert "current node" in str(error)
    assert selection.states == []
    assert orchestration.calls == []
    print("PASS: invalid Run current node is rejected")


def test_invalid_select_step_is_rejected() -> None:
    invalid_steps = (
        make_step(node_name="execute_tool"),
        make_step(step_status="interrupted"),
    )

    for invalid_step in invalid_steps:
        runner, selection, orchestration = build_runner()

        expect_raises(
            ValueError,
            lambda invalid_step=invalid_step: call(
                runner,
                select_step=invalid_step,
            ),
        )
        assert selection.states == []
        assert orchestration.calls == []

    print("PASS: invalid select_tool Step is rejected")


def test_step_index_mismatch_is_rejected() -> None:
    runner, selection, orchestration = build_runner()

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            agent_run=make_run(step_count=6),
            select_step=make_step(step_index=5),
        ),
    )

    assert "latest Step" in str(error)
    assert selection.states == []
    assert orchestration.calls == []
    print("PASS: non-latest select_tool Step is rejected")


def test_state_snapshot_mismatch_is_rejected() -> None:
    runner, selection, orchestration = build_runner()
    step_state = base_state()
    step_state["issue_id"] = 18

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            select_step=make_step(
                input_state_json=step_state
            ),
        ),
    )

    assert "state snapshot" in str(error)
    assert selection.states == []
    assert orchestration.calls == []
    print("PASS: mismatched Step state snapshot is rejected")


def test_pending_selected_tool_is_rejected() -> None:
    runner, selection, orchestration = build_runner()
    state = base_state()
    state["selected_tool"] = make_decision().as_dict()

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            agent_run=make_run(state_json=state),
            select_step=make_step(input_state_json=state),
        ),
    )

    assert "already contains selected_tool" in str(error)
    assert selection.states == []
    assert orchestration.calls == []
    print("PASS: pending selected_tool is rejected")


def test_controlled_selection_error_fails_step() -> None:
    selection_error = AgentToolSelectionError(
        error_code="triage_not_confirmed",
        message="Tool selection requires confirmed triage.",
    )
    runner, _, orchestration = build_runner(
        error=selection_error
    )

    error = expect_raises(
        AgentToolSelectionError,
        lambda: call(runner),
    )

    assert error is selection_error
    assert [name for name, _ in orchestration.calls] == [
        "fail_step"
    ]
    payload = orchestration.calls[0][1]
    assert payload["error_code"] == "triage_not_confirmed"
    assert payload["output_state_json"] == {
        "selection_version": AGENT_TOOL_SELECTION_VERSION,
        "error_code": "triage_not_confirmed",
    }
    print("PASS: controlled selection error fails the Step")


def test_unexpected_selection_error_fails_step() -> None:
    runner, _, orchestration = build_runner(
        error=RuntimeError("simulated selection failure")
    )

    expect_raises(
        RuntimeError,
        lambda: call(runner),
    )

    assert [name for name, _ in orchestration.calls] == [
        "fail_step"
    ]
    payload = orchestration.calls[0][1]
    assert payload["error_code"] == "select_tool_failed"
    assert payload["error_message"] == (
        "RuntimeError occurred while selecting "
        "an Agent Tool"
    )
    print("PASS: unexpected selection error fails the Step")


def test_source_preserves_boundaries() -> None:
    source = inspect.getsource(
        AgentRunnerService.advance_select_tool
    )

    forbidden = (
        "db.commit(",
        "db.rollback(",
        "db.flush(",
        "db.refresh(",
        "agent_persistence_service",
        "AgentGuardedToolExecutionService",
        "execute_once(",
        "AgentToolCall",
        "create_tool_call(",
        "start_tool_call(",
        "complete_tool_call(",
    )
    found = [
        token for token in forbidden
        if token in source
    ]

    assert not found, found
    assert ".select(" in source
    assert "complete_step_and_advance_run(" in source
    assert "_fail_step(" in source
    print("PASS: Runner select_tool preserves boundaries")


def main() -> None:
    tests = (
        test_version_and_nodes_are_frozen,
        test_happy_path_advances_atomically,
        test_persisted_state_feeds_selection_exactly,
        test_selected_tool_state_is_controlled,
        test_original_state_is_not_mutated,
        test_result_preserves_advanced_objects,
        test_invalid_run_status_is_rejected,
        test_invalid_current_node_is_rejected,
        test_invalid_select_step_is_rejected,
        test_step_index_mismatch_is_rejected,
        test_state_snapshot_mismatch_is_rejected,
        test_pending_selected_tool_is_rejected,
        test_controlled_selection_error_fails_step,
        test_unexpected_selection_error_fails_step,
        test_source_preserves_boundaries,
    )

    for test in tests:
        test()

    print(
        "Agent Runner select_tool assertions "
        "passed (15/15)"
    )


if __name__ == "__main__":
    main()
