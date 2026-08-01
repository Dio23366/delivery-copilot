from __future__ import annotations

from pathlib import Path
from types import MappingProxyType, SimpleNamespace
import sys
from typing import Callable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.agent_guarded_tool_execution_service import (
    AGENT_GUARDED_TOOL_EXECUTION_VERSION,
    AgentGuardedToolExecutionOutcome,
    AgentGuardedToolExecutionService,
    AgentToolExecutionRejectedError,
)
from app.services.agent_tool_call_policy_snapshot_service import (
    AgentToolCallPolicySnapshot,
)
from app.services.agent_tool_contract_service import (
    agent_tool_contract_service,
)
from app.services.agent_tool_execution_policy_service import (
    AgentToolExecutionPolicyDecision,
)
from app.services.agent_tool_executor_service import (
    AgentToolExecutionOutcome,
    AgentToolExecutorError,
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


class RecordingSnapshotService:
    def __init__(
        self,
        *,
        snapshot: AgentToolCallPolicySnapshot,
        error: Exception | None = None,
        events: list[str] | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.error = error
        self.events = events if events is not None else []
        self.calls: list[
            tuple[object, str]
        ] = []

    def load(
        self,
        db: object,
        *,
        run_id: str,
    ) -> AgentToolCallPolicySnapshot:
        self.events.append("snapshot")
        self.calls.append((db, run_id))
        if self.error is not None:
            raise self.error
        return self.snapshot


class RecordingPolicyService:
    def __init__(
        self,
        *,
        decision: AgentToolExecutionPolicyDecision,
        error: Exception | None = None,
        events: list[str] | None = None,
    ) -> None:
        self.decision = decision
        self.error = error
        self.events = events if events is not None else []
        self.calls: list[dict[str, object]] = []

    def evaluate(
        self,
        **kwargs: object,
    ) -> AgentToolExecutionPolicyDecision:
        self.events.append("policy")
        self.calls.append(dict(kwargs))
        if self.error is not None:
            raise self.error
        return self.decision


class RecordingExecutorService:
    def __init__(
        self,
        *,
        outcome: AgentToolExecutionOutcome,
        error: Exception | None = None,
        events: list[str] | None = None,
    ) -> None:
        self.outcome = outcome
        self.error = error
        self.events = events if events is not None else []
        self.calls: list[
            tuple[object, dict[str, object]]
        ] = []

    def execute_once(
        self,
        db: object,
        **kwargs: object,
    ) -> AgentToolExecutionOutcome:
        self.events.append("executor")
        self.calls.append((db, dict(kwargs)))
        if self.error is not None:
            raise self.error
        return self.outcome


def approved_identity() -> str:
    return (
        agent_tool_contract_service
        .validate_arguments(
            "search_knowledge",
            {"issue_id": 17},
        )
        .call_identity
    )


def snapshot(
    *,
    count: int = 0,
    identities: tuple[str, ...] = (),
) -> AgentToolCallPolicySnapshot:
    return AgentToolCallPolicySnapshot(
        run_id="run-001",
        tool_call_count=count,
        prior_call_identities=identities,
    )


def decision(
    *,
    allowed: bool = True,
    error_code: str | None = None,
    reason: str = (
        "The approved Tool call may execute."
    ),
) -> AgentToolExecutionPolicyDecision:
    return AgentToolExecutionPolicyDecision(
        allowed=allowed,
        tool_name="search_knowledge",
        tool_version="grounded_retrieval_v1",
        call_identity=approved_identity(),
        normalized_arguments=MappingProxyType(
            {"issue_id": 17}
        ),
        tool_call_count=0,
        max_tool_calls=3,
        error_code=error_code,
        reason=reason,
    )


def execution(
    *,
    tool_name: str = "search_knowledge",
    tool_version: str = "grounded_retrieval_v1",
    call_identity: str | None = None,
) -> AgentToolExecutionOutcome:
    return AgentToolExecutionOutcome(
        tool_call=SimpleNamespace(
            call_status="completed",
            tool_call_index=1,
        ),
        tool_name=tool_name,
        tool_version=tool_version,
        call_identity=(
            call_identity
            if call_identity is not None
            else approved_identity()
        ),
        result_json=MappingProxyType(
            {
                "retrieval_status": "no_results",
                "retrieval_query": "controlled query",
                "knowledge_evidence": [],
                "knowledge_citations": [],
                "retrieval_error_code": None,
            }
        ),
    )


def build_service(
    *,
    snapshot_value: AgentToolCallPolicySnapshot | None = None,
    decision_value: AgentToolExecutionPolicyDecision | None = None,
    execution_value: AgentToolExecutionOutcome | None = None,
    snapshot_error: Exception | None = None,
    policy_error: Exception | None = None,
    executor_error: Exception | None = None,
) -> tuple[
    AgentGuardedToolExecutionService,
    RecordingSnapshotService,
    RecordingPolicyService,
    RecordingExecutorService,
    list[str],
]:
    events: list[str] = []
    snapshot_service = RecordingSnapshotService(
        snapshot=(
            snapshot_value
            if snapshot_value is not None
            else snapshot()
        ),
        error=snapshot_error,
        events=events,
    )
    policy_service = RecordingPolicyService(
        decision=(
            decision_value
            if decision_value is not None
            else decision()
        ),
        error=policy_error,
        events=events,
    )
    executor_service = RecordingExecutorService(
        outcome=(
            execution_value
            if execution_value is not None
            else execution()
        ),
        error=executor_error,
        events=events,
    )

    return (
        AgentGuardedToolExecutionService(
            snapshot_service=snapshot_service,
            policy_service=policy_service,
            executor_service=executor_service,
        ),
        snapshot_service,
        policy_service,
        executor_service,
        events,
    )


def call(
    service: AgentGuardedToolExecutionService,
    db: object,
) -> AgentGuardedToolExecutionOutcome:
    return service.execute_once(
        db,
        run_id="run-001",
        step_index=4,
        tool_name="search_knowledge",
        arguments={"issue_id": "17"},
        max_tool_calls=3,
    )


def test_version_is_frozen() -> None:
    assert AGENT_GUARDED_TOOL_EXECUTION_VERSION == (
        "agent_guarded_tool_execution_v0.1"
    )
    print("PASS: guarded execution version is frozen")


def test_success_order_is_deterministic() -> None:
    service, _, _, _, events = build_service()

    outcome = call(service, object())

    assert events == [
        "snapshot",
        "policy",
        "executor",
    ]
    assert isinstance(
        outcome,
        AgentGuardedToolExecutionOutcome,
    )
    print("PASS: success order is deterministic")


def test_snapshot_inputs_feed_policy() -> None:
    prior = ("search_knowledge:prior",)
    service, _, policy_service, _, _ = (
        build_service(
            snapshot_value=snapshot(
                count=1,
                identities=prior,
            )
        )
    )

    call(service, object())

    payload = policy_service.calls[0]
    assert payload["tool_call_count"] == 1
    assert payload["max_tool_calls"] == 3
    assert payload["prior_call_identities"] == prior
    assert payload["tool_name"] == "search_knowledge"
    assert payload["arguments"] == {"issue_id": "17"}
    print("PASS: persisted snapshot feeds policy exactly")


def test_normalized_decision_feeds_executor() -> None:
    service, _, _, executor_service, _ = (
        build_service()
    )
    db = object()

    call(service, db)

    called_db, payload = executor_service.calls[0]
    assert called_db is db
    assert payload == {
        "run_id": "run-001",
        "step_index": 4,
        "tool_name": "search_knowledge",
        "arguments": {"issue_id": 17},
    }
    print("PASS: normalized decision feeds Executor")


def test_success_outcome_is_json_safe() -> None:
    service, _, _, _, _ = build_service()

    payload = call(service, object()).as_dict()

    assert payload["decision"]["allowed"] is True
    assert payload["execution"]["tool_name"] == (
        "search_knowledge"
    )
    assert payload["execution"]["result_json"][
        "retrieval_status"
    ] == "no_results"
    print("PASS: guarded outcome is JSON-safe")


def test_max_call_rejection_stops_executor() -> None:
    rejected = decision(
        allowed=False,
        error_code="max_tool_calls_reached",
        reason=(
            "The Agent Tool call limit has "
            "already been reached."
        ),
    )
    service, _, _, executor_service, events = (
        build_service(decision_value=rejected)
    )

    error = expect_raises(
        AgentToolExecutionRejectedError,
        lambda: call(service, object()),
    )

    assert error.error_code == (
        "max_tool_calls_reached"
    )
    assert error.decision is rejected
    assert events == ["snapshot", "policy"]
    assert executor_service.calls == []
    print("PASS: max-call rejection creates no execution")


def test_duplicate_rejection_stops_executor() -> None:
    rejected = decision(
        allowed=False,
        error_code="duplicate_tool_call",
        reason=(
            "An identical approved Tool call "
            "already exists in this run."
        ),
    )
    service, _, _, executor_service, events = (
        build_service(decision_value=rejected)
    )

    error = expect_raises(
        AgentToolExecutionRejectedError,
        lambda: call(service, object()),
    )

    assert error.error_code == "duplicate_tool_call"
    assert events == ["snapshot", "policy"]
    assert executor_service.calls == []
    print("PASS: duplicate rejection creates no execution")


def test_snapshot_failure_stops_pipeline() -> None:
    service, _, policy_service, executor_service, events = (
        build_service(
            snapshot_error=LookupError(
                "Agent run not found: run-001"
            )
        )
    )

    expect_raises(
        LookupError,
        lambda: call(service, object()),
    )

    assert events == ["snapshot"]
    assert policy_service.calls == []
    assert executor_service.calls == []
    print("PASS: snapshot failure stops pipeline")


def test_policy_failure_stops_executor() -> None:
    service, _, _, executor_service, events = (
        build_service(
            policy_error=ValueError(
                "policy snapshot mismatch"
            )
        )
    )

    expect_raises(
        ValueError,
        lambda: call(service, object()),
    )

    assert events == ["snapshot", "policy"]
    assert executor_service.calls == []
    print("PASS: policy failure stops Executor")


def test_executor_failure_is_preserved() -> None:
    executor_error = AgentToolExecutorError(
        error_code="tool_business_error",
        message="Issue not found: 17",
        call_identity=approved_identity(),
        tool_call=SimpleNamespace(
            call_status="failed"
        ),
    )
    service, _, _, _, events = build_service(
        executor_error=executor_error
    )

    error = expect_raises(
        AgentToolExecutorError,
        lambda: call(service, object()),
    )

    assert error is executor_error
    assert events == [
        "snapshot",
        "policy",
        "executor",
    ]
    print("PASS: Executor failure is preserved")


def test_identity_mismatch_fails_closed() -> None:
    service, _, _, _, _ = build_service(
        execution_value=execution(
            call_identity="search_knowledge:wrong"
        )
    )

    error = expect_raises(
        RuntimeError,
        lambda: call(service, object()),
    )

    assert "call identity" in str(error)
    print("PASS: execution identity mismatch fails closed")


def test_tool_name_mismatch_fails_closed() -> None:
    service, _, _, _, _ = build_service(
        execution_value=execution(
            tool_name="get_analysis_history"
        )
    )

    error = expect_raises(
        RuntimeError,
        lambda: call(service, object()),
    )

    assert "Tool name" in str(error)
    print("PASS: execution Tool name mismatch fails closed")


def test_tool_version_mismatch_fails_closed() -> None:
    service, _, _, _, _ = build_service(
        execution_value=execution(
            tool_version="wrong_version"
        )
    )

    error = expect_raises(
        RuntimeError,
        lambda: call(service, object()),
    )

    assert "Tool version" in str(error)
    print("PASS: execution Tool version mismatch fails closed")


def test_rejected_error_requires_rejection() -> None:
    expect_raises(
        ValueError,
        lambda: AgentToolExecutionRejectedError(
            decision=decision(allowed=True)
        ),
    )
    print("PASS: rejection error rejects allowed decisions")


def test_source_is_transaction_and_state_free() -> None:
    source_path = (
        BACKEND_ROOT
        / "app"
        / "services"
        / "agent_guarded_tool_execution_service.py"
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
        "retry",
        "ThreadPoolExecutor",
        "time.sleep(",
        "asyncio.sleep(",
    )
    found = [
        token for token in forbidden
        if token in source
    ]
    assert not found, found
    assert ".load(" in source
    assert ".evaluate(" in source
    assert "execute_once(" in source
    assert "AgentToolExecutionRejectedError" in source
    print("PASS: coordinator is transaction-free and state-free")


def main() -> None:
    tests = (
        test_version_is_frozen,
        test_success_order_is_deterministic,
        test_snapshot_inputs_feed_policy,
        test_normalized_decision_feeds_executor,
        test_success_outcome_is_json_safe,
        test_max_call_rejection_stops_executor,
        test_duplicate_rejection_stops_executor,
        test_snapshot_failure_stops_pipeline,
        test_policy_failure_stops_executor,
        test_executor_failure_is_preserved,
        test_identity_mismatch_fails_closed,
        test_tool_name_mismatch_fails_closed,
        test_tool_version_mismatch_fails_closed,
        test_rejected_error_requires_rejection,
        test_source_is_transaction_and_state_free,
    )

    for test in tests:
        test()

    print(
        "Agent Guarded Tool Execution assertions "
        "passed (15/15)"
    )


if __name__ == "__main__":
    main()
