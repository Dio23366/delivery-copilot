from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import inspect
import sys
from typing import Callable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.agent_evidence_evaluation_service import (
    AGENT_EVIDENCE_EVALUATION_VERSION,
    GENERATE_ANALYSIS_NODE,
    LIMIT_EXCEEDED_NODE,
    REQUEST_CLARIFICATION_NODE,
    SELECT_TOOL_NODE,
    AgentEvidenceEvaluationDecision,
    AgentEvidenceEvaluationError,
)
from app.services.agent_runner_service import (
    AGENT_RUNNER_EVALUATE_EVIDENCE_VERSION,
    EVALUATE_EVIDENCE_NODE,
    AgentRunnerEvaluateEvidenceResult,
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
                    "retrieval_status": "succeeded"
                },
                "execution_status": "completed",
            }
        ],
        "retrieved_evidence": [
            {
                "source_tool": "search_knowledge",
                "source_call_identity": (
                    "search_knowledge:"
                    f"{'a' * 64}"
                ),
                "evidence_type": "knowledge_chunk",
                "payload": {
                    "chunk_id": 21,
                    "chunk_text": (
                        "Verify token rotation and scope."
                    ),
                    "similarity_score": 0.91,
                },
            }
        ],
        "max_tool_calls": 3,
    }


def decision(
    next_node: str,
    *,
    sufficient: bool,
    reason: str,
) -> AgentEvidenceEvaluationDecision:
    return AgentEvidenceEvaluationDecision(
        next_node=next_node,
        evidence_sufficient=sufficient,
        evidence_reason=reason,
        completed_tool_count=1,
        knowledge_evidence_count=(
            1 if sufficient else 0
        ),
        history_evidence_count=0,
        unused_tool_names=(
            "get_analysis_history",
            "calculate_delivery_risk",
        ),
    )


class RecordingEvaluationService:
    def __init__(
        self,
        *,
        evaluation_decision: (
            AgentEvidenceEvaluationDecision | None
        ) = None,
        error: Exception | None = None,
        return_value: object | None = None,
    ) -> None:
        self.evaluation_decision = (
            evaluation_decision
            if evaluation_decision is not None
            else decision(
                GENERATE_ANALYSIS_NODE,
                sufficient=True,
                reason="Grounded evidence is sufficient.",
            )
        )
        self.error = error
        self.return_value = return_value
        self.states: list[dict[str, object]] = []

    def evaluate(
        self,
        state: object,
    ) -> object:
        self.states.append(dict(state))
        if self.error is not None:
            raise self.error
        if self.return_value is not None:
            return self.return_value
        return self.evaluation_decision


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
            node_name=EVALUATE_EVIDENCE_NODE,
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

    def complete_step_and_limit_run(
        self,
        db: object,
        **kwargs: object,
    ) -> tuple[object, object]:
        self.calls.append(
            (
                "complete_step_and_limit_run",
                {"db": db, **dict(kwargs)},
            )
        )
        limited_run = SimpleNamespace(
            run_id=kwargs["run_id"],
            run_status="limit_exceeded",
            current_node="limit_exceeded",
            step_count=kwargs["step_index"],
            state_json=dict(kwargs["state_json"]),
            error_code=kwargs["error_code"],
            error_message=kwargs["error_message"],
        )
        completed_step = SimpleNamespace(
            step_index=kwargs["step_index"],
            node_name=EVALUATE_EVIDENCE_NODE,
            step_status="completed",
            output_state_json=dict(
                kwargs["output_state_json"]
            ),
        )
        return limited_run, completed_step

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
            node_name=EVALUATE_EVIDENCE_NODE,
            step_status="failed",
            error_code=kwargs["error_code"],
        )


def make_run(
    *,
    run_status: str = "running",
    current_node: str = EVALUATE_EVIDENCE_NODE,
    step_count: int = 7,
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
    step_index: int = 7,
    node_name: str = EVALUATE_EVIDENCE_NODE,
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
    evaluation_decision: (
        AgentEvidenceEvaluationDecision | None
    ) = None,
    error: Exception | None = None,
    return_value: object | None = None,
) -> tuple[
    AgentRunnerService,
    RecordingEvaluationService,
    RecordingOrchestrationService,
]:
    evaluation = RecordingEvaluationService(
        evaluation_decision=evaluation_decision,
        error=error,
        return_value=return_value,
    )
    orchestration = RecordingOrchestrationService()
    runner = AgentRunnerService(
        orchestration_service=orchestration,
        evidence_evaluation_service=evaluation,
    )
    return runner, evaluation, orchestration


def call(
    runner: AgentRunnerService,
    *,
    db: object | None = None,
    agent_run: object | None = None,
    evaluate_step: object | None = None,
) -> AgentRunnerEvaluateEvidenceResult:
    return runner.advance_evaluate_evidence(
        db if db is not None else object(),
        agent_run=(
            agent_run
            if agent_run is not None
            else make_run()
        ),
        evaluate_evidence_step=(
            evaluate_step
            if evaluate_step is not None
            else make_step()
        ),
    )


def test_version_and_routes_are_frozen() -> None:
    assert AGENT_RUNNER_EVALUATE_EVIDENCE_VERSION == (
        "agent_runner_evaluate_evidence_v0.1"
    )
    assert EVALUATE_EVIDENCE_NODE == (
        "evaluate_evidence"
    )
    assert {
        GENERATE_ANALYSIS_NODE,
        SELECT_TOOL_NODE,
        REQUEST_CLARIFICATION_NODE,
    } == {
        "generate_analysis",
        "select_tool",
        "request_clarification",
    }
    assert LIMIT_EXCEEDED_NODE == "limit_exceeded"
    print("PASS: Runner evaluate_evidence contract is frozen")


def test_generate_analysis_route_advances() -> None:
    runner, evaluation, orchestration = (
        build_runner()
    )
    db = object()

    result = call(runner, db=db)

    assert isinstance(
        result,
        AgentRunnerEvaluateEvidenceResult,
    )
    assert result.agent_run.current_node == (
        GENERATE_ANALYSIS_NODE
    )
    assert result.next_step.node_name == (
        GENERATE_ANALYSIS_NODE
    )
    assert len(evaluation.states) == 1
    assert len(orchestration.calls) == 1
    assert orchestration.calls[0][1]["db"] is db
    print("PASS: generate_analysis route advances")


def test_select_tool_route_advances() -> None:
    runner, _, orchestration = build_runner(
        evaluation_decision=decision(
            SELECT_TOOL_NODE,
            sufficient=False,
            reason="Another approved Tool remains.",
        )
    )

    result = call(runner)

    assert result.agent_run.current_node == (
        SELECT_TOOL_NODE
    )
    assert result.next_step.node_name == (
        SELECT_TOOL_NODE
    )
    assert orchestration.calls[0][1][
        "next_node"
    ] == SELECT_TOOL_NODE
    print("PASS: select_tool route advances")


def test_request_clarification_route_advances() -> None:
    runner, _, orchestration = build_runner(
        evaluation_decision=decision(
            REQUEST_CLARIFICATION_NODE,
            sufficient=False,
            reason="Focused clarification is required.",
        )
    )

    result = call(runner)

    assert result.agent_run.current_node == (
        REQUEST_CLARIFICATION_NODE
    )
    assert result.next_step.node_name == (
        REQUEST_CLARIFICATION_NODE
    )
    assert orchestration.calls[0][1][
        "next_node"
    ] == REQUEST_CLARIFICATION_NODE
    print("PASS: request_clarification route advances")


def test_controlled_state_update_is_persisted() -> None:
    evaluation_decision = decision(
        GENERATE_ANALYSIS_NODE,
        sufficient=True,
        reason="Grounded evidence is sufficient.",
    )
    runner, _, orchestration = build_runner(
        evaluation_decision=evaluation_decision
    )
    state = base_state()
    state["preserved_value"] = "keep-me"

    result = call(
        runner,
        agent_run=make_run(state_json=state),
        evaluate_step=make_step(
            input_state_json=state
        ),
    )

    assert result.state_json["preserved_value"] == (
        "keep-me"
    )
    assert result.state_json[
        "evidence_sufficient"
    ] is True
    assert result.state_json["evidence_reason"] == (
        "Grounded evidence is sufficient."
    )

    payload = orchestration.calls[0][1]
    assert payload["state_json"] == result.state_json
    assert payload["output_state_json"] == (
        evaluation_decision.as_dict()
    )
    print("PASS: controlled Evaluation state is persisted")


def test_original_state_is_not_mutated() -> None:
    runner, _, _ = build_runner()
    state = base_state()

    result = call(
        runner,
        agent_run=make_run(state_json=state),
        evaluate_step=make_step(
            input_state_json=state
        ),
    )

    assert "evidence_sufficient" not in state
    assert "evidence_reason" not in state
    assert result.state_json[
        "evidence_sufficient"
    ] is True
    print("PASS: original Agent state is not mutated")


def test_result_preserves_advanced_objects() -> None:
    runner, _, _ = build_runner()

    result = call(runner)

    assert result.evaluate_evidence_step.step_status == (
        "completed"
    )
    assert result.next_step.step_status == "running"
    assert result.evaluation_decision.next_node == (
        GENERATE_ANALYSIS_NODE
    )
    print("PASS: Evaluation result preserves objects")


def test_invalid_run_status_is_rejected() -> None:
    runner, evaluation, orchestration = (
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
    assert evaluation.states == []
    assert orchestration.calls == []
    print("PASS: invalid Run status is rejected")


def test_invalid_current_node_is_rejected() -> None:
    runner, evaluation, orchestration = (
        build_runner()
    )

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            agent_run=make_run(
                current_node="execute_tool"
            ),
        ),
    )

    assert "current node" in str(error)
    assert evaluation.states == []
    assert orchestration.calls == []
    print("PASS: invalid current node is rejected")


def test_invalid_evaluate_step_is_rejected() -> None:
    invalid_steps = (
        make_step(node_name="execute_tool"),
        make_step(step_status="completed"),
    )

    for invalid_step in invalid_steps:
        runner, evaluation, orchestration = (
            build_runner()
        )

        expect_raises(
            ValueError,
            lambda invalid_step=invalid_step: call(
                runner,
                evaluate_step=invalid_step,
            ),
        )
        assert evaluation.states == []
        assert orchestration.calls == []

    print("PASS: invalid evaluate_evidence Step is rejected")


def test_step_index_mismatch_is_rejected() -> None:
    runner, evaluation, orchestration = (
        build_runner()
    )

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            agent_run=make_run(step_count=8),
            evaluate_step=make_step(step_index=7),
        ),
    )

    assert "latest Step" in str(error)
    assert evaluation.states == []
    assert orchestration.calls == []
    print("PASS: non-latest Evaluation Step is rejected")


def test_state_snapshot_mismatch_is_rejected() -> None:
    runner, evaluation, orchestration = (
        build_runner()
    )
    step_state = base_state()
    step_state["issue_id"] = 18

    error = expect_raises(
        ValueError,
        lambda: call(
            runner,
            evaluate_step=make_step(
                input_state_json=step_state
            ),
        ),
    )

    assert "state snapshot" in str(error)
    assert evaluation.states == []
    assert orchestration.calls == []
    print("PASS: mismatched Evaluation state is rejected")


def test_controlled_evaluation_error_fails_step() -> None:
    evaluation_error = AgentEvidenceEvaluationError(
        error_code="missing_tool_results",
        message="Completed Tool results are required.",
    )
    runner, _, orchestration = build_runner(
        error=evaluation_error
    )

    error = expect_raises(
        AgentEvidenceEvaluationError,
        lambda: call(runner),
    )

    assert error is evaluation_error
    assert [name for name, _ in orchestration.calls] == [
        "fail_step"
    ]
    payload = orchestration.calls[0][1]
    assert payload["error_code"] == (
        "missing_tool_results"
    )
    assert payload["output_state_json"] == {
        "evaluation_version": (
            AGENT_EVIDENCE_EVALUATION_VERSION
        ),
        "error_code": "missing_tool_results",
    }
    print("PASS: controlled Evaluation error fails the Step")


def test_unexpected_evaluation_error_is_sanitized() -> None:
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
        "evaluate_evidence_failed"
    )
    assert payload["error_message"] == (
        "RuntimeError occurred while evaluating "
        "Agent evidence"
    )
    assert "secret" not in payload["error_message"]
    print("PASS: unexpected Evaluation error is sanitized")


def test_limit_route_terminalizes_through_orchestration() -> None:
    limit_decision = decision(
        LIMIT_EXCEEDED_NODE,
        sufficient=False,
        reason="Tool budget is exhausted.",
    )
    runner, evaluation, orchestration = build_runner(
        evaluation_decision=limit_decision
    )
    db = object()

    result = call(runner, db=db)

    assert isinstance(
        result,
        AgentRunnerEvaluateEvidenceResult,
    )
    assert result.agent_run.run_status == (
        "limit_exceeded"
    )
    assert result.agent_run.current_node == (
        LIMIT_EXCEEDED_NODE
    )
    assert result.evaluate_evidence_step.step_status == (
        "completed"
    )
    assert result.next_step is None
    assert result.evaluation_decision is limit_decision
    assert len(evaluation.states) == 1
    assert [name for name, _ in orchestration.calls] == [
        "complete_step_and_limit_run"
    ]

    payload = orchestration.calls[0][1]
    assert payload["db"] is db
    assert payload["run_id"] == "run-001"
    assert payload["step_index"] == 7
    assert payload["error_code"] == (
        "max_tool_calls_reached"
    )
    assert payload["error_message"] == (
        "Tool budget is exhausted."
    )
    assert payload["state_json"][
        "evidence_sufficient"
    ] is False
    assert payload["state_json"]["evidence_reason"] == (
        "Tool budget is exhausted."
    )
    assert payload["output_state_json"] == (
        limit_decision.as_dict()
    )
    print("PASS: limit_exceeded terminalizes through Orchestration")


def test_unsupported_route_is_rejected_before_orchestration() -> None:
    runner, evaluation, orchestration = build_runner(
        evaluation_decision=decision(
            "unsupported_node",
            sufficient=False,
            reason="Unsupported route.",
        )
    )

    error = expect_raises(
        ValueError,
        lambda: call(runner),
    )

    assert "unsupported next node" in str(error)
    assert len(evaluation.states) == 1
    assert orchestration.calls == []
    print("PASS: unsupported route is rejected before orchestration")


def test_invalid_decision_type_fails_step() -> None:
    runner, _, orchestration = build_runner(
        return_value={"next_node": "select_tool"}
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
    ] == "evaluate_evidence_failed"
    print("PASS: invalid Evaluation decision type fails the Step")


def test_source_preserves_route_boundaries() -> None:
    source = inspect.getsource(
        AgentRunnerService.advance_evaluate_evidence
    )

    forbidden = (
        "db.commit(",
        "db.rollback(",
        "db.flush(",
        "db.refresh(",
        "agent_persistence_service",
        "interrupt_step_and_wait_run(",
        "mark_step_interrupted_and_run_waiting(",
        "resume_waiting_investigation_run(",
        "finalize_waiting_review_run(",
        "complete_run(",
        "fail_run(",
    )
    found = [
        token for token in forbidden
        if token in source
    ]

    assert not found, found
    assert ".evaluate(" in source
    assert "complete_step_and_advance_run(" in source
    assert "complete_step_and_limit_run(" in source
    assert "_fail_step(" in source
    assert "LIMIT_EXCEEDED_NODE" in source
    assert "max_tool_calls_reached" in source
    print("PASS: Runner Evaluation preserves boundaries")


def main() -> None:
    tests = (
        test_version_and_routes_are_frozen,
        test_generate_analysis_route_advances,
        test_select_tool_route_advances,
        test_request_clarification_route_advances,
        test_controlled_state_update_is_persisted,
        test_original_state_is_not_mutated,
        test_result_preserves_advanced_objects,
        test_invalid_run_status_is_rejected,
        test_invalid_current_node_is_rejected,
        test_invalid_evaluate_step_is_rejected,
        test_step_index_mismatch_is_rejected,
        test_state_snapshot_mismatch_is_rejected,
        test_controlled_evaluation_error_fails_step,
        test_unexpected_evaluation_error_is_sanitized,
        test_limit_route_terminalizes_through_orchestration,
        test_unsupported_route_is_rejected_before_orchestration,
        test_invalid_decision_type_fails_step,
        test_source_preserves_route_boundaries,
    )

    for test in tests:
        test()

    print(
        "Agent Runner evaluate_evidence assertions "
        "passed (18/18)"
    )


if __name__ == "__main__":
    main()
