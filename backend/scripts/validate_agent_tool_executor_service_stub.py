from __future__ import annotations

from dataclasses import dataclass
import operator
from pathlib import Path
import sys
from typing import Callable

from pydantic import BaseModel


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.schemas.agent_tools import (
    AgentAnalysisHistoryOutput,
    AgentSearchKnowledgeOutput,
)
from app.services.agent_tool_contract_service import (
    agent_tool_contract_service,
)
from app.services.agent_tool_executor_service import (
    AGENT_TOOL_EXECUTOR_VERSION,
    AgentToolExecutionOutcome,
    AgentToolExecutorError,
    AgentToolExecutorService,
)
from app.services.agent_tool_registry import (
    approved_agent_tool_registry,
)


@dataclass
class FakeToolCall:
    tool_call_index: int
    call_status: str
    arguments_json: dict[str, object] | None = None
    result_json: dict[str, object] | None = None
    error_code: str | None = None
    error_message: str | None = None


class RecordingOrchestration:
    def __init__(
        self,
        *,
        fail_on: str | None = None,
    ) -> None:
        self.fail_on = fail_on
        self.events: list[
            tuple[str, dict[str, object]]
        ] = []

    def _record(
        self,
        name: str,
        payload: dict[str, object],
    ) -> None:
        self.events.append((name, payload))
        if self.fail_on == name:
            raise RuntimeError(
                f"{name} persistence failure"
            )

    def create_tool_call(
        self,
        db: object,
        **kwargs: object,
    ) -> FakeToolCall:
        payload = dict(kwargs)
        payload["db"] = db
        self._record("create", payload)
        return FakeToolCall(
            tool_call_index=1,
            call_status="created",
            arguments_json=dict(
                kwargs["arguments_json"]
            ),
        )

    def start_tool_call(
        self,
        db: object,
        **kwargs: object,
    ) -> FakeToolCall:
        payload = dict(kwargs)
        payload["db"] = db
        self._record("start", payload)
        return FakeToolCall(
            tool_call_index=int(
                kwargs["tool_call_index"]
            ),
            call_status="running",
        )

    def complete_tool_call(
        self,
        db: object,
        **kwargs: object,
    ) -> FakeToolCall:
        payload = dict(kwargs)
        payload["db"] = db
        self._record("complete", payload)
        return FakeToolCall(
            tool_call_index=int(
                kwargs["tool_call_index"]
            ),
            call_status="completed",
            result_json=dict(kwargs["result_json"]),
        )

    def fail_tool_call(
        self,
        db: object,
        **kwargs: object,
    ) -> FakeToolCall:
        payload = dict(kwargs)
        payload["db"] = db
        self._record("fail", payload)
        return FakeToolCall(
            tool_call_index=int(
                kwargs["tool_call_index"]
            ),
            call_status="failed",
            error_code=str(kwargs["error_code"]),
            error_message=str(
                kwargs["error_message"]
            ),
        )

    def timeout_tool_call(
        self,
        db: object,
        **kwargs: object,
    ) -> FakeToolCall:
        payload = dict(kwargs)
        payload["db"] = db
        self._record("timeout", payload)
        return FakeToolCall(
            tool_call_index=int(
                kwargs["tool_call_index"]
            ),
            call_status="timed_out",
            error_code=str(kwargs["error_code"]),
            error_message=str(
                kwargs["error_message"]
            ),
        )


class RecordingDispatch:
    def __init__(
        self,
        *,
        result: BaseModel | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[
            tuple[object, object]
        ] = []

    def execute(
        self,
        validated_arguments: object,
        db: object,
    ) -> BaseModel:
        self.calls.append(
            (validated_arguments, db)
        )
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


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


def search_output() -> AgentSearchKnowledgeOutput:
    return AgentSearchKnowledgeOutput(
        retrieval_status="no_results",
        retrieval_query="controlled query",
        knowledge_evidence=(),
        knowledge_citations=(),
        retrieval_error_code=None,
    )


def build_executor(
    orchestration: RecordingOrchestration,
    dispatch: RecordingDispatch,
) -> AgentToolExecutorService:
    return AgentToolExecutorService(
        contract_service=agent_tool_contract_service,
        dispatch_service=dispatch,
        orchestration_service=orchestration,
        registry=approved_agent_tool_registry,
    )


def execute_search(
    executor: AgentToolExecutorService,
    db: object,
    *,
    arguments: dict[str, object] | None = None,
) -> AgentToolExecutionOutcome:
    return executor.execute_once(
        db,
        run_id="run-001",
        step_index=4,
        tool_name="search_knowledge",
        arguments=(
            arguments
            if arguments is not None
            else {"issue_id": 17}
        ),
    )


def test_version_is_frozen() -> None:
    assert AGENT_TOOL_EXECUTOR_VERSION == (
        "agent_tool_executor_v0.1"
    )
    print("PASS: Executor version is frozen")


def test_success_lifecycle_order() -> None:
    orchestration = RecordingOrchestration()
    dispatch = RecordingDispatch(
        result=search_output()
    )
    db = object()

    outcome = execute_search(
        build_executor(orchestration, dispatch),
        db,
    )

    assert [
        name for name, _ in orchestration.events
    ] == ["create", "start", "complete"]
    assert outcome.tool_call.call_status == "completed"
    print("PASS: success lifecycle order is deterministic")


def test_normalized_arguments_and_metadata() -> None:
    orchestration = RecordingOrchestration()
    dispatch = RecordingDispatch(
        result=search_output()
    )

    outcome = execute_search(
        build_executor(orchestration, dispatch),
        object(),
        arguments={"issue_id": "17"},
    )

    create_payload = orchestration.events[0][1]
    assert create_payload["arguments_json"] == {
        "issue_id": 17
    }
    assert create_payload["tool_name"] == (
        "search_knowledge"
    )
    assert create_payload["tool_version"] == (
        "grounded_retrieval_v1"
    )
    assert create_payload["timeout_seconds"] == 30
    assert create_payload["read_only"] is True
    assert (
        create_payload["requires_approval"]
        is False
    )
    assert outcome.call_identity.startswith(
        "search_knowledge:"
    )
    print("PASS: normalized arguments and Registry metadata persist")


def test_validated_result_is_persisted() -> None:
    orchestration = RecordingOrchestration()
    outcome = execute_search(
        build_executor(
            orchestration,
            RecordingDispatch(result=search_output()),
        ),
        object(),
    )

    complete_payload = orchestration.events[-1][1]
    assert complete_payload["result_json"] == {
        "retrieval_status": "no_results",
        "retrieval_query": "controlled query",
        "knowledge_evidence": [],
        "knowledge_citations": [],
        "retrieval_error_code": None,
    }
    assert dict(outcome.result_json) == (
        complete_payload["result_json"]
    )
    expect_raises(
        TypeError,
        lambda: operator.setitem(
            outcome.result_json,
            "unexpected",
            True,
        ),
    )
    print("PASS: validated result is persisted immutably")


def test_timeout_signal_is_persisted() -> None:
    orchestration = RecordingOrchestration()
    executor = build_executor(
        orchestration,
        RecordingDispatch(
            error=TimeoutError("provider timeout")
        ),
    )

    error = expect_raises(
        AgentToolExecutorError,
        lambda: execute_search(executor, object()),
    )

    assert error.error_code == "TOOL_TIMEOUT"
    assert error.tool_call.call_status == "timed_out"
    assert [
        name for name, _ in orchestration.events
    ] == ["create", "start", "timeout"]
    assert "provider timeout" not in str(error)
    print("PASS: timeout signal is persisted safely")


def test_dispatch_failure_is_persisted() -> None:
    orchestration = RecordingOrchestration()
    executor = build_executor(
        orchestration,
        RecordingDispatch(
            error=LookupError("Issue not found: 17")
        ),
    )

    error = expect_raises(
        AgentToolExecutorError,
        lambda: execute_search(executor, object()),
    )

    assert error.error_code == "tool_business_error"
    assert str(error) == "Issue not found: 17"
    assert error.tool_call.call_status == "failed"
    assert [
        name for name, _ in orchestration.events
    ] == ["create", "start", "fail"]
    print("PASS: business failure is persisted")


def test_invalid_result_is_persisted_as_failure() -> None:
    orchestration = RecordingOrchestration()
    wrong_output = AgentAnalysisHistoryOutput(
        issue_id=17,
        analysis_count=0,
        analyses=(),
    )
    executor = build_executor(
        orchestration,
        RecordingDispatch(result=wrong_output),
    )

    error = expect_raises(
        AgentToolExecutorError,
        lambda: execute_search(executor, object()),
    )

    assert error.error_code == "invalid_tool_result"
    assert error.tool_call.call_status == "failed"
    assert orchestration.events[-1][0] == "fail"
    print("PASS: invalid Tool result is persisted as failure")


def test_invalid_arguments_create_no_audit_row() -> None:
    orchestration = RecordingOrchestration()
    executor = build_executor(
        orchestration,
        RecordingDispatch(result=search_output()),
    )

    expect_raises(
        Exception,
        lambda: execute_search(
            executor,
            object(),
            arguments={"issue_id": 0},
        ),
    )

    assert orchestration.events == []
    print("PASS: invalid arguments fail before audit creation")


def test_unapproved_tool_create_no_audit_row() -> None:
    orchestration = RecordingOrchestration()
    executor = build_executor(
        orchestration,
        RecordingDispatch(result=search_output()),
    )

    expect_raises(
        Exception,
        lambda: executor.execute_once(
            object(),
            run_id="run-001",
            step_index=4,
            tool_name="unapproved_tool",
            arguments={"issue_id": 17},
        ),
    )

    assert orchestration.events == []
    print("PASS: unapproved Tool fails before audit creation")


def test_create_failure_stops_execution() -> None:
    orchestration = RecordingOrchestration(
        fail_on="create"
    )
    dispatch = RecordingDispatch(
        result=search_output()
    )

    expect_raises(
        RuntimeError,
        lambda: execute_search(
            build_executor(orchestration, dispatch),
            object(),
        ),
    )

    assert [name for name, _ in orchestration.events] == [
        "create"
    ]
    assert dispatch.calls == []
    print("PASS: create failure stops execution")


def test_start_failure_stops_dispatch() -> None:
    orchestration = RecordingOrchestration(
        fail_on="start"
    )
    dispatch = RecordingDispatch(
        result=search_output()
    )

    expect_raises(
        RuntimeError,
        lambda: execute_search(
            build_executor(orchestration, dispatch),
            object(),
        ),
    )

    assert [
        name for name, _ in orchestration.events
    ] == ["create", "start"]
    assert dispatch.calls == []
    print("PASS: start failure stops dispatch")


def test_unknown_error_is_redacted() -> None:
    orchestration = RecordingOrchestration()
    secret = "https://secret.example?api_key=abc"
    executor = build_executor(
        orchestration,
        RecordingDispatch(
            error=RuntimeError(secret)
        ),
    )

    error = expect_raises(
        AgentToolExecutorError,
        lambda: execute_search(executor, object()),
    )

    assert error.error_code == "tool_execution_failed"
    assert secret not in str(error)
    fail_payload = orchestration.events[-1][1]
    assert secret not in str(
        fail_payload["error_message"]
    )
    print("PASS: unknown failure details are redacted")


def test_call_identity_is_stable() -> None:
    outcomes = []
    for _ in range(2):
        outcomes.append(
            execute_search(
                build_executor(
                    RecordingOrchestration(),
                    RecordingDispatch(
                        result=search_output()
                    ),
                ),
                object(),
                arguments={"issue_id": 17},
            )
        )

    assert (
        outcomes[0].call_identity
        == outcomes[1].call_identity
    )
    print("PASS: call identity is stable")


def test_executor_owns_no_transactions_or_state() -> None:
    source_path = (
        BACKEND_ROOT
        / "app"
        / "services"
        / "agent_tool_executor_service.py"
    )
    source = source_path.read_text(encoding="utf-8")

    forbidden = (
        "db.add(",
        "db.delete(",
        "db.commit(",
        "db.rollback(",
        "db.flush(",
        "db.refresh(",
        ".with_for_update(",
        "AgentRunnerService",
        "state_json",
        "selected_tool",
        "tool_results",
        "ThreadPoolExecutor",
        "time.sleep(",
        "asyncio.sleep(",
        "eval(",
        "exec(",
        "importlib",
    )
    found = [
        token for token in forbidden
        if token in source
    ]
    assert not found, found
    assert "execute_once(" in source
    assert "create_tool_call(" in source
    assert "start_tool_call(" in source
    assert "complete_tool_call(" in source
    assert "fail_tool_call(" in source
    assert "timeout_tool_call(" in source
    print("PASS: Executor is transaction-free and state-free")


def test_no_retry_or_hard_timeout_claim() -> None:
    source_path = (
        BACKEND_ROOT
        / "app"
        / "services"
        / "agent_tool_executor_service.py"
    )
    source = source_path.read_text(encoding="utf-8")

    assert "retry" not in source.lower()
    assert "ThreadPoolExecutor" not in source
    assert "signal.alarm" not in source
    assert "timeout_seconds=" in source
    print("PASS: first slice makes no retry or hard-timeout claim")


def main() -> None:
    tests = (
        test_version_is_frozen,
        test_success_lifecycle_order,
        test_normalized_arguments_and_metadata,
        test_validated_result_is_persisted,
        test_timeout_signal_is_persisted,
        test_dispatch_failure_is_persisted,
        test_invalid_result_is_persisted_as_failure,
        test_invalid_arguments_create_no_audit_row,
        test_unapproved_tool_create_no_audit_row,
        test_create_failure_stops_execution,
        test_start_failure_stops_dispatch,
        test_unknown_error_is_redacted,
        test_call_identity_is_stable,
        test_executor_owns_no_transactions_or_state,
        test_no_retry_or_hard_timeout_claim,
    )

    for test in tests:
        test()

    print(
        "Agent Tool Executor Service assertions "
        "passed (15/15)"
    )


if __name__ == "__main__":
    main()
