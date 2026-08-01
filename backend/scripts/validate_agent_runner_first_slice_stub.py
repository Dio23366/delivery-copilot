from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ai.issue_summarizer import IssueContext
from app.services.agent_runner_service import (
    AWAIT_TRIAGE_CONFIRMATION_NODE,
    DEFAULT_AGENT_GRAPH_VERSION,
    LOAD_ISSUE_NODE,
    TRIAGE_ISSUE_NODE,
    WAITING_FOR_TRIAGE_CONFIRMATION_STATUS,
    AgentRunnerService,
)
from app.services.agent_triage_service import (
    AgentTriageExhaustedError,
    AgentTriageOutcome,
)
from app.schemas.agent import AgentTriageResult


RUNNER_PATH = Path(
    "app/services/agent_runner_service.py"
)


@dataclass
class FakeRun:
    run_id: str
    current_node: str
    run_status: str = "running"


@dataclass
class FakeStep:
    step_index: int
    node_name: str
    step_status: str = "running"


class FakeOrchestrationService:
    def __init__(self) -> None:
        self.calls: list[
            tuple[str, dict[str, Any]]
        ] = []

    def start_run(
        self,
        db: object,
        **kwargs: Any,
    ) -> FakeRun:
        del db
        self.calls.append(
            ("start_run", dict(kwargs))
        )
        return FakeRun(
            run_id=kwargs["run_id"],
            current_node=kwargs["initial_node"],
        )

    def start_step(
        self,
        db: object,
        **kwargs: Any,
    ) -> FakeStep:
        del db
        self.calls.append(
            ("start_step", dict(kwargs))
        )
        return FakeStep(
            step_index=1,
            node_name=kwargs["node_name"],
        )

    def complete_step_and_advance_run(
        self,
        db: object,
        **kwargs: Any,
    ) -> tuple[FakeRun, FakeStep, FakeStep]:
        del db
        self.calls.append(
            (
                "complete_step_and_advance_run",
                dict(kwargs),
            )
        )

        step_index = kwargs["step_index"]
        next_node = kwargs["next_node"]

        return (
            FakeRun(
                run_id=kwargs["run_id"],
                current_node=next_node,
            ),
            FakeStep(
                step_index=step_index,
                node_name=(
                    LOAD_ISSUE_NODE
                    if step_index == 1
                    else TRIAGE_ISSUE_NODE
                ),
                step_status="completed",
            ),
            FakeStep(
                step_index=step_index + 1,
                node_name=next_node,
            ),
        )

    def interrupt_step_and_wait_run(
        self,
        db: object,
        **kwargs: Any,
    ) -> tuple[FakeRun, FakeStep]:
        del db
        self.calls.append(
            (
                "interrupt_step_and_wait_run",
                dict(kwargs),
            )
        )

        return (
            FakeRun(
                run_id=kwargs["run_id"],
                current_node=(
                    AWAIT_TRIAGE_CONFIRMATION_NODE
                ),
                run_status=kwargs["waiting_status"],
            ),
            FakeStep(
                step_index=kwargs["step_index"],
                node_name=(
                    AWAIT_TRIAGE_CONFIRMATION_NODE
                ),
                step_status="interrupted",
            ),
        )

    def fail_step(
        self,
        db: object,
        **kwargs: Any,
    ) -> FakeStep:
        del db
        self.calls.append(
            ("fail_step", dict(kwargs))
        )
        return FakeStep(
            step_index=kwargs["step_index"],
            node_name="failed",
            step_status="failed",
        )


class FakeIssueContextService:
    def __init__(
        self,
        *,
        error: Exception | None = None,
    ) -> None:
        self.error = error
        self.loaded_issue_ids: list[int] = []

    def load_issue_context(
        self,
        db: object,
        *,
        issue_id: int,
    ) -> IssueContext:
        del db
        self.loaded_issue_ids.append(issue_id)

        if self.error is not None:
            raise self.error

        return IssueContext(
            issue_id=issue_id,
            issue_title=(
                "Customer API authentication failure"
            ),
            issue_description=(
                "API token rejected with 401"
            ),
            issue_type="API",
            severity="critical",
            status="open",
            owner="Runner Owner",
            project_name="Runner Project",
            project_status="active",
            delivery_stage="Implementation",
            risk_level="high",
            health="critical",
            customer_name="Runner Customer",
            customer_industry="Technology",
            customer_contact="runner@example.com",
        )

    def serialize_issue_context(
        self,
        context: IssueContext,
    ) -> dict[str, object]:
        return {
            "issue_id": context.issue_id,
            "issue_title": context.issue_title,
            "issue_description": (
                context.issue_description
            ),
            "issue_type": context.issue_type,
            "severity": context.severity,
            "status": context.status,
            "owner": context.owner,
            "project_name": context.project_name,
            "project_status": (
                context.project_status
            ),
            "delivery_stage": (
                context.delivery_stage
            ),
            "risk_level": context.risk_level,
            "health": context.health,
            "customer_name": context.customer_name,
            "customer_industry": (
                context.customer_industry
            ),
            "customer_contact": (
                context.customer_contact
            ),
        }


class FakeTriageService:
    def __init__(
        self,
        *,
        error: Exception | None = None,
    ) -> None:
        self.error = error
        self.contexts: list[IssueContext] = []

    def triage(
        self,
        context: IssueContext,
    ) -> AgentTriageOutcome:
        self.contexts.append(context)

        if self.error is not None:
            raise self.error

        return AgentTriageOutcome(
            result=AgentTriageResult(
                issue_type="API",
                subtype="authentication",
                severity="critical",
                confidence=0.95,
                reason=(
                    "Issue Type 'API' was preserved; "
                    "subtype 'authentication' was "
                    "selected from a specific controlled "
                    "signal; severity 'critical' was "
                    "preserved."
                ),
            ),
            attempt=1,
            max_retries=2,
        )


def make_runner(
    *,
    context_error: Exception | None = None,
    triage_error: Exception | None = None,
) -> tuple[
    AgentRunnerService,
    FakeOrchestrationService,
    FakeIssueContextService,
    FakeTriageService,
]:
    orchestration = FakeOrchestrationService()
    context_service = FakeIssueContextService(
        error=context_error
    )
    triage_service = FakeTriageService(
        error=triage_error
    )

    runner = AgentRunnerService(
        orchestration_service=orchestration,
        issue_context_service=context_service,
        triage_service=triage_service,
    )

    return (
        runner,
        orchestration,
        context_service,
        triage_service,
    )


def test_happy_path_exact_call_sequence() -> None:
    (
        runner,
        orchestration,
        context_service,
        triage_service,
    ) = make_runner()

    result = runner.start_and_run_to_triage_wait(
        object(),
        run_id="run-first-slice",
        issue_id=17,
    )

    call_names = [
        name
        for name, _ in orchestration.calls
    ]

    assert call_names == [
        "start_run",
        "start_step",
        "complete_step_and_advance_run",
        "complete_step_and_advance_run",
        "interrupt_step_and_wait_run",
    ]
    assert context_service.loaded_issue_ids == [17]
    assert len(triage_service.contexts) == 1
    assert result.agent_run.run_status == (
        WAITING_FOR_TRIAGE_CONFIRMATION_STATUS
    )
    assert (
        result.await_triage_confirmation_step
        .step_status
        == "interrupted"
    )


def test_happy_path_state_contract() -> None:
    runner, orchestration, _, _ = make_runner()

    initial_state = {
        "request_id": "request-123",
    }

    result = runner.start_and_run_to_triage_wait(
        object(),
        run_id="run-state",
        issue_id=17,
        initial_state=initial_state,
    )

    assert initial_state == {
        "request_id": "request-123",
    }
    assert result.state_json["request_id"] == (
        "request-123"
    )
    assert result.state_json["issue_id"] == 17
    assert result.state_json["graph_version"] == (
        DEFAULT_AGENT_GRAPH_VERSION
    )
    assert len(
        result.state_json["issue_context"]
    ) == 15
    assert result.state_json["triage_attempt"] == 1
    assert result.state_json["max_retries"] == 2
    assert (
        result.state_json[
            "triage_suggestion"
        ]["subtype"]
        == "authentication"
    )

    final_call = orchestration.calls[-1]
    assert final_call[1]["waiting_status"] == (
        WAITING_FOR_TRIAGE_CONFIRMATION_STATUS
    )
    assert final_call[1]["step_index"] == 3


def test_graph_override_is_preserved() -> None:
    runner, orchestration, _, _ = make_runner()

    runner.start_and_run_to_triage_wait(
        object(),
        run_id="run-graph",
        issue_id=17,
        graph_version="agent_mvp_test",
    )

    start_run_call = orchestration.calls[0][1]
    assert start_run_call["graph_version"] == (
        "agent_mvp_test"
    )
    assert start_run_call["initial_node"] == (
        LOAD_ISSUE_NODE
    )


def test_load_issue_failure_marks_first_step_failed() -> None:
    (
        runner,
        orchestration,
        _,
        triage_service,
    ) = make_runner(
        context_error=LookupError(
            "Issue not found: 999"
        )
    )

    try:
        runner.start_and_run_to_triage_wait(
            object(),
            run_id="run-missing",
            issue_id=999,
        )
    except LookupError:
        pass
    else:
        raise AssertionError(
            "Expected LookupError"
        )

    assert not triage_service.contexts

    fail_calls = [
        payload
        for name, payload in orchestration.calls
        if name == "fail_step"
    ]

    assert len(fail_calls) == 1
    assert fail_calls[0]["step_index"] == 1
    assert fail_calls[0]["error_code"] == (
        "issue_not_found"
    )


def test_triage_exhaustion_marks_second_step_failed() -> None:
    triage_error = AgentTriageExhaustedError(
        code="triage_unclassifiable",
        attempts=3,
        max_retries=2,
        detail="No controlled signal",
    )

    runner, orchestration, _, _ = make_runner(
        triage_error=triage_error
    )

    try:
        runner.start_and_run_to_triage_wait(
            object(),
            run_id="run-unclassifiable",
            issue_id=17,
        )
    except AgentTriageExhaustedError:
        pass
    else:
        raise AssertionError(
            "Expected triage exhaustion"
        )

    fail_calls = [
        payload
        for name, payload in orchestration.calls
        if name == "fail_step"
    ]

    assert len(fail_calls) == 1
    assert fail_calls[0]["step_index"] == 2
    assert fail_calls[0]["error_code"] == (
        "triage_unclassifiable"
    )
    assert fail_calls[0]["output_state_json"] == {
        "triage_attempt": 3,
        "max_retries": 2,
    }


def test_wait_uses_frozen_node_and_status() -> None:
    runner, orchestration, _, _ = make_runner()

    runner.start_and_run_to_triage_wait(
        object(),
        run_id="run-wait",
        issue_id=17,
    )

    advance_calls = [
        payload
        for name, payload in orchestration.calls
        if name
        == "complete_step_and_advance_run"
    ]

    assert [
        payload["next_node"]
        for payload in advance_calls
    ] == [
        TRIAGE_ISSUE_NODE,
        AWAIT_TRIAGE_CONFIRMATION_NODE,
    ]

    wait_payload = orchestration.calls[-1][1]
    assert wait_payload["waiting_status"] == (
        WAITING_FOR_TRIAGE_CONFIRMATION_STATUS
    )


def test_invalid_step_index_is_rejected() -> None:
    class InvalidStepOrchestration(
        FakeOrchestrationService
    ):
        def start_step(
            self,
            db: object,
            **kwargs: Any,
        ) -> FakeStep:
            del db
            self.calls.append(
                ("start_step", dict(kwargs))
            )
            return FakeStep(
                step_index=0,
                node_name=kwargs["node_name"],
            )

    orchestration = InvalidStepOrchestration()
    runner = AgentRunnerService(
        orchestration_service=orchestration,
        issue_context_service=(
            FakeIssueContextService()
        ),
        triage_service=FakeTriageService(),
    )

    try:
        runner.start_and_run_to_triage_wait(
            object(),
            run_id="run-invalid-step",
            issue_id=17,
        )
    except ValueError as exc:
        assert "positive integer" in str(exc)
    else:
        raise AssertionError(
            "Expected invalid step rejection"
        )


def test_runner_source_reuses_orchestration_only() -> None:
    source = RUNNER_PATH.read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    direct_db_calls: set[str] = set()
    persistence_calls: set[str] = set()
    orchestration_calls: set[str] = set()

    def dotted_name(node: ast.AST) -> str | None:
        parts: list[str] = []
        current = node

        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value

        if isinstance(current, ast.Name):
            parts.append(current.id)
            return ".".join(reversed(parts))

        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(
                alias.name
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module)
        elif isinstance(node, ast.Call):
            call_name = dotted_name(node.func)

            if call_name is None:
                continue

            if call_name.startswith("db."):
                direct_db_calls.add(call_name)

            if call_name.startswith(
                "self._persistence_service."
            ):
                persistence_calls.add(call_name)

            orchestration_prefix = (
                "self._orchestration_service."
            )
            if call_name.startswith(
                orchestration_prefix
            ):
                orchestration_calls.add(
                    call_name[
                        len(orchestration_prefix):
                    ]
                )

    assert not any(
        module.endswith(
            "agent_persistence_service"
        )
        for module in imported_modules
    )
    assert not direct_db_calls
    assert not persistence_calls

    assert {
        "start_run",
        "start_step",
        "complete_step_and_advance_run",
        "complete_step_and_limit_run",
        "interrupt_step_and_wait_run",
        "fail_step",
    }.issubset(orchestration_calls)


TESTS: tuple[Callable[[], None], ...] = (
    test_happy_path_exact_call_sequence,
    test_happy_path_state_contract,
    test_graph_override_is_preserved,
    test_load_issue_failure_marks_first_step_failed,
    test_triage_exhaustion_marks_second_step_failed,
    test_wait_uses_frozen_node_and_status,
    test_invalid_step_index_is_rejected,
    test_runner_source_reuses_orchestration_only,
)


def main() -> None:
    for test in TESTS:
        test()
        print(f"passed={test.__name__}")

    print(f"validator_test_count={len(TESTS)}")
    print(
        "first_slice="
        "start_run->load_issue->triage_issue->"
        "await_triage_confirmation->"
        "waiting_for_triage_confirmation"
    )
    print("expected_step_count=3")
    print("direct_db_mutation_call_count=0")
    print("api_integration=not_started")
    print(
        "agent_runner_first_slice_stub_validation="
        "passed"
    )


if __name__ == "__main__":
    main()
