from __future__ import annotations

import ast
from copy import deepcopy
import inspect
import textwrap
from types import MappingProxyType, SimpleNamespace
from typing import Callable
from unittest.mock import Mock

from app.ai.prompt_builder import ISSUE_SUMMARIZER_PROMPT_VERSION
from app.ai.schemas import IssueAnalysisContext, ProviderAnalysisResult
from app.services.agent_analysis_generation_service import (
    AGENT_ANALYSIS_GENERATION_VERSION,
    AgentAnalysisGenerationError,
    AgentAnalysisGenerationOutcome,
)
from app.services.agent_runner_service import (
    AGENT_RUNNER_GENERATE_ANALYSIS_VERSION,
    GENERATE_ANALYSIS_NODE,
    PERSIST_ANALYSIS_NODE,
    AgentRunnerGenerateAnalysisResult,
    AgentRunnerService,
)


def state() -> dict[str, object]:
    return {
        "issue_id": 17,
        "issue_context": {"issue_id": 17},
        "selected_tool": None,
        "tool_results": [],
        "retrieved_evidence": [],
        "evidence_sufficient": True,
        "evidence_reason": "Accepted history is sufficient.",
    }


def run(
    *,
    state_json: object | None = None,
    run_id: object = "run-generate-001",
    run_status: object = "running",
    current_node: object = GENERATE_ANALYSIS_NODE,
    step_count: object = 5,
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
    )


def step(
    *,
    input_state_json: object | None = None,
    step_index: object = 5,
    node_name: object = GENERATE_ANALYSIS_NODE,
    step_status: object = "running",
) -> SimpleNamespace:
    return SimpleNamespace(
        step_index=step_index,
        node_name=node_name,
        step_status=step_status,
        input_state_json=(
            state()
            if input_state_json is None
            else input_state_json
        ),
    )


def outcome() -> AgentAnalysisGenerationOutcome:
    analysis_result = ProviderAnalysisResult(
        issue_summary="Authentication fails after rollout.",
        possible_root_cause="Token configuration may be inconsistent.",
        recommended_actions=[
            "Validate token endpoint configuration.",
        ],
        customer_update_draft="The issue is under investigation.",
        risk_level="high",
        project_impact="Testing may be delayed.",
        provider="llm",
        model_name="gpt-test",
        prompt_version=ISSUE_SUMMARIZER_PROMPT_VERSION,
    )
    analysis_context = IssueAnalysisContext(
        issue={"id": 17},
        project=None,
        customer=None,
    )
    generated = {
        "generation_version": AGENT_ANALYSIS_GENERATION_VERSION,
        "analysis_type": "issue_summarizer",
        "provider": "llm",
        "model_name": "gpt-test",
        "prompt_version": ISSUE_SUMMARIZER_PROMPT_VERSION,
        "provider_fallback_reason": None,
        "issue_summary": analysis_result.issue_summary,
        "possible_root_cause": analysis_result.possible_root_cause,
        "recommended_actions": list(
            analysis_result.recommended_actions
        ),
        "customer_update_draft": (
            analysis_result.customer_update_draft
        ),
        "risk_level": analysis_result.risk_level,
        "project_impact": analysis_result.project_impact,
        "retrieval_status": "not_attempted",
        "retrieval_query": None,
        "knowledge_citations": [],
        "retrieval_error_code": None,
        "supplemental_evidence_count": 1,
    }
    return AgentAnalysisGenerationOutcome(
        analysis_result=analysis_result,
        analysis_context=analysis_context,
        knowledge_citations=(),
        supplemental_evidence=(),
        provider_fallback_reason=None,
        state_update=MappingProxyType(
            {"generated_analysis": generated}
        ),
    )


class RecordingOrchestrationService:
    def __init__(self) -> None:
        self.advance_calls: list[dict[str, object]] = []
        self.fail_calls: list[dict[str, object]] = []

    def complete_step_and_advance_run(
        self,
        db: object,
        **kwargs: object,
    ) -> tuple[SimpleNamespace, SimpleNamespace, SimpleNamespace]:
        self.advance_calls.append({"db": db, **dict(kwargs)})
        next_state = dict(kwargs["state_json"])
        current_index = int(kwargs["step_index"])
        advanced_run = run(
            state_json=next_state,
            current_node=str(kwargs["next_node"]),
            step_count=current_index + 1,
        )
        completed_step = step(
            input_state_json=state(),
            step_index=current_index,
            step_status="completed",
        )
        next_step = SimpleNamespace(
            step_index=current_index + 1,
            node_name=str(kwargs["next_node"]),
            step_status="running",
            input_state_json=next_state,
        )
        return advanced_run, completed_step, next_step

    def fail_step(
        self,
        db: object,
        **kwargs: object,
    ) -> SimpleNamespace:
        self.fail_calls.append({"db": db, **dict(kwargs)})
        return step(
            step_index=int(kwargs["step_index"]),
            step_status="failed",
        )


class StubGenerationService:
    def __init__(self, result: object) -> None:
        self.result = result
        self.states: list[dict[str, object]] = []

    def generate(self, agent_state: object) -> object:
        assert isinstance(agent_state, dict)
        self.states.append(deepcopy(agent_state))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def service(
    result: object | None = None,
) -> tuple[
    AgentRunnerService,
    RecordingOrchestrationService,
    StubGenerationService,
]:
    runner = object.__new__(AgentRunnerService)
    orchestration = RecordingOrchestrationService()
    generation = StubGenerationService(
        outcome() if result is None else result
    )
    runner._orchestration_service = orchestration
    runner._analysis_generation_service = generation
    return runner, orchestration, generation


def expect_value_error(
    callback: Callable[[], object],
    fragment: str,
) -> None:
    try:
        callback()
    except ValueError as exc:
        assert fragment in str(exc)
        return
    raise AssertionError("Expected ValueError")


def test_constants_and_result_contract() -> None:
    assert AGENT_RUNNER_GENERATE_ANALYSIS_VERSION == (
        "agent_runner_generate_analysis_v0.1"
    )
    assert PERSIST_ANALYSIS_NODE == "persist_analysis"
    assert GENERATE_ANALYSIS_NODE == "generate_analysis"
    assert AgentRunnerGenerateAnalysisResult.__dataclass_params__.frozen


def test_happy_path_advances_to_persist_analysis() -> None:
    runner, orchestration, generation = service()
    db = object()
    initial_state = state()
    initial_run = run(state_json=deepcopy(initial_state))
    initial_step = step(input_state_json=deepcopy(initial_state))

    result = runner.advance_generate_analysis(
        db,
        agent_run=initial_run,
        generate_analysis_step=initial_step,
    )

    assert isinstance(result, AgentRunnerGenerateAnalysisResult)
    assert result.agent_run.current_node == PERSIST_ANALYSIS_NODE
    assert result.persist_analysis_step.node_name == PERSIST_ANALYSIS_NODE
    assert result.generate_analysis_step.step_status == "completed"
    assert result.generation_outcome is generation.result
    assert "generated_analysis" in result.state_json
    assert len(generation.states) == 1
    assert generation.states[0] == initial_state
    assert len(orchestration.advance_calls) == 1
    assert not orchestration.fail_calls


def test_transition_payload_is_exact() -> None:
    runner, orchestration, _ = service()
    db = object()
    initial_state = state()
    generated_outcome = outcome()
    runner._analysis_generation_service = StubGenerationService(
        generated_outcome
    )

    result = runner.advance_generate_analysis(
        db,
        agent_run=run(state_json=deepcopy(initial_state)),
        generate_analysis_step=step(
            input_state_json=deepcopy(initial_state)
        ),
    )

    call = orchestration.advance_calls[0]
    assert call["db"] is db
    assert call["run_id"] == "run-generate-001"
    assert call["step_index"] == 5
    assert call["next_node"] == PERSIST_ANALYSIS_NODE
    assert call["state_json"] == result.state_json
    assert call["output_state_json"] == (
        generated_outcome.as_dict()
    )


def test_input_state_is_not_mutated() -> None:
    runner, _, _ = service()
    initial_state = state()
    original = deepcopy(initial_state)
    initial_run = run(state_json=initial_state)
    initial_step = step(input_state_json=deepcopy(initial_state))

    runner.advance_generate_analysis(
        object(),
        agent_run=initial_run,
        generate_analysis_step=initial_step,
    )

    assert initial_state == original
    assert initial_run.state_json == original
    assert initial_step.input_state_json == original


def test_invalid_run_contracts_fail_closed() -> None:
    runner, _, _ = service()
    cases = (
        (run(run_id=" "), "normalized run_id"),
        (run(run_status="waiting"), "cannot generate analysis"),
        (run(current_node="persist_analysis"), "unexpected current node"),
        (run(step_count=True), "positive integer step_count"),
        (run(state_json=[]), "state_json must be a mapping"),
    )
    for invalid_run, fragment in cases:
        expect_value_error(
            lambda invalid_run=invalid_run: (
                runner.advance_generate_analysis(
                    object(),
                    agent_run=invalid_run,
                    generate_analysis_step=step(),
                )
            ),
            fragment,
        )


def test_invalid_step_contracts_fail_closed() -> None:
    runner, _, _ = service()
    cases = (
        (step(step_index=4), "latest Step"),
        (step(node_name="evaluate_evidence"), "unexpected generation node"),
        (step(step_status="completed"), "must be running"),
        (step(input_state_json=[]), "input state must be a mapping"),
        (step(input_state_json={"different": True}), "does not match"),
    )
    for invalid_step, fragment in cases:
        expect_value_error(
            lambda invalid_step=invalid_step: (
                runner.advance_generate_analysis(
                    object(),
                    agent_run=run(),
                    generate_analysis_step=invalid_step,
                )
            ),
            fragment,
        )


def test_existing_generated_analysis_is_rejected() -> None:
    runner, _, generation = service()
    initial_state = state()
    initial_state["generated_analysis"] = {"existing": True}

    expect_value_error(
        lambda: runner.advance_generate_analysis(
            object(),
            agent_run=run(state_json=initial_state),
            generate_analysis_step=step(
                input_state_json=deepcopy(initial_state)
            ),
        ),
        "already contains generated_analysis",
    )
    assert not generation.states


def test_structured_generation_error_fails_step() -> None:
    error = AgentAnalysisGenerationError(
        error_code="missing_generation_evidence",
        message="Generation evidence is missing.",
    )
    runner, orchestration, _ = service(error)

    try:
        runner.advance_generate_analysis(
            object(),
            agent_run=run(),
            generate_analysis_step=step(),
        )
    except AgentAnalysisGenerationError as exc:
        assert exc is error
    else:
        raise AssertionError("Expected structured generation error")

    assert not orchestration.advance_calls
    assert len(orchestration.fail_calls) == 1
    call = orchestration.fail_calls[0]
    assert call["error_code"] == "missing_generation_evidence"
    assert call["error_message"] == "Generation evidence is missing."
    assert call["output_state_json"] == {
        "generation_version": AGENT_ANALYSIS_GENERATION_VERSION,
        "runner_generation_version": (
            AGENT_RUNNER_GENERATE_ANALYSIS_VERSION
        ),
        "error_code": "missing_generation_evidence",
    }


def test_unexpected_error_is_sanitized_and_fails_step() -> None:
    runner, orchestration, _ = service(
        RuntimeError("secret provider detail")
    )

    try:
        runner.advance_generate_analysis(
            object(),
            agent_run=run(),
            generate_analysis_step=step(),
        )
    except RuntimeError as exc:
        assert str(exc) == "secret provider detail"
    else:
        raise AssertionError("Expected RuntimeError")

    call = orchestration.fail_calls[0]
    assert call["error_code"] == "generate_analysis_failed"
    assert call["error_message"] == (
        "RuntimeError occurred while generating Agent analysis"
    )
    assert "secret provider detail" not in call["error_message"]


def test_invalid_outcome_type_fails_step() -> None:
    runner, orchestration, _ = service(object())

    try:
        runner.advance_generate_analysis(
            object(),
            agent_run=run(),
            generate_analysis_step=step(),
        )
    except TypeError as exc:
        assert "invalid outcome type" in str(exc)
    else:
        raise AssertionError("Expected TypeError")

    assert orchestration.fail_calls[0]["error_code"] == (
        "generate_analysis_failed"
    )


def test_source_contract_is_transaction_neutral() -> None:
    source = inspect.getsource(
        AgentRunnerService.advance_generate_analysis
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
            calls.append(".".join(reversed(parts)))

    for forbidden in (
        "db.add",
        "db.commit",
        "db.rollback",
        "db.refresh",
        "db.flush",
        "db.delete",
    ):
        assert forbidden not in calls

    assert calls.count(
        "self._analysis_generation_service.generate"
    ) == 1
    assert calls.count(
        "self._orchestration_service.complete_step_and_advance_run"
    ) == 1
    assert calls.count("self._fail_step") == 2
    assert "next_node=PERSIST_ANALYSIS_NODE" in source
    assert "generated_analysis" in source


def main() -> None:
    tests = (
        test_constants_and_result_contract,
        test_happy_path_advances_to_persist_analysis,
        test_transition_payload_is_exact,
        test_input_state_is_not_mutated,
        test_invalid_run_contracts_fail_closed,
        test_invalid_step_contracts_fail_closed,
        test_existing_generated_analysis_is_rejected,
        test_structured_generation_error_fails_step,
        test_unexpected_error_is_sanitized_and_fails_step,
        test_invalid_outcome_type_fails_step,
        test_source_contract_is_transaction_neutral,
    )

    for test in tests:
        test()
        print(f"passed={test.__name__}")

    print(
        "Agent Runner generate_analysis assertions "
        f"passed: {len(tests)}/{len(tests)}"
    )
    print(f"passed_count={len(tests)}")


if __name__ == "__main__":
    main()
