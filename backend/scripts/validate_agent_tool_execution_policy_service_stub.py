from __future__ import annotations

import operator
from pathlib import Path
import sys
from typing import Callable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.agent_tool_contract_service import (
    AgentToolContractError,
    agent_tool_contract_service,
)
from app.services.agent_tool_execution_policy_service import (
    AGENT_TOOL_EXECUTION_POLICY_VERSION,
    AgentToolExecutionPolicyDecision,
    AgentToolExecutionPolicyService,
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


def candidate_identity(
    *,
    issue_id: int = 17,
) -> str:
    return (
        agent_tool_contract_service
        .validate_arguments(
            "search_knowledge",
            {"issue_id": issue_id},
        )
        .call_identity
    )


def evaluate(
    *,
    issue_id: int | str = 17,
    tool_call_count: int = 0,
    max_tool_calls: int = 3,
    prior_call_identities: tuple[str, ...] = (),
) -> AgentToolExecutionPolicyDecision:
    return AgentToolExecutionPolicyService().evaluate(
        tool_name="search_knowledge",
        arguments={"issue_id": issue_id},
        tool_call_count=tool_call_count,
        max_tool_calls=max_tool_calls,
        prior_call_identities=(
            prior_call_identities
        ),
    )


def test_version_is_frozen() -> None:
    assert AGENT_TOOL_EXECUTION_POLICY_VERSION == (
        "agent_tool_execution_policy_v0.1"
    )
    print("PASS: policy version is frozen")


def test_fresh_candidate_is_allowed() -> None:
    decision = evaluate()

    assert decision.allowed is True
    assert decision.error_code is None
    assert decision.reason == (
        "The approved Tool call may execute."
    )
    print("PASS: fresh approved Tool call is allowed")


def test_arguments_are_normalized() -> None:
    decision = evaluate(issue_id="17")

    assert dict(decision.normalized_arguments) == {
        "issue_id": 17
    }
    assert decision.tool_name == "search_knowledge"
    assert decision.tool_version == (
        "grounded_retrieval_v1"
    )
    print("PASS: candidate arguments are normalized")


def test_normalized_arguments_are_immutable() -> None:
    decision = evaluate()

    expect_raises(
        TypeError,
        lambda: operator.setitem(
            decision.normalized_arguments,
            "issue_id",
            99,
        ),
    )
    print("PASS: normalized arguments are immutable")


def test_identity_is_stable() -> None:
    first = evaluate()
    second = evaluate(issue_id="17")

    assert first.call_identity == (
        second.call_identity
    )
    assert first.call_identity.startswith(
        "search_knowledge:"
    )
    print("PASS: candidate identity is stable")


def test_limit_is_rejected() -> None:
    decision = evaluate(
        tool_call_count=3,
        max_tool_calls=3,
        prior_call_identities=(
            candidate_identity(issue_id=1),
            candidate_identity(issue_id=2),
            candidate_identity(issue_id=3),
        ),
    )

    assert decision.allowed is False
    assert decision.error_code == (
        "max_tool_calls_reached"
    )
    print("PASS: reached Tool call limit is rejected")


def test_over_limit_is_rejected() -> None:
    decision = evaluate(
        tool_call_count=4,
        max_tool_calls=3,
        prior_call_identities=(
            candidate_identity(issue_id=1),
            candidate_identity(issue_id=2),
            candidate_identity(issue_id=3),
            candidate_identity(issue_id=4),
        ),
    )

    assert decision.allowed is False
    assert decision.error_code == (
        "max_tool_calls_reached"
    )
    print("PASS: over-limit state remains rejected")


def test_duplicate_identity_is_rejected() -> None:
    identity = candidate_identity()
    decision = evaluate(
        tool_call_count=1,
        max_tool_calls=3,
        prior_call_identities=(identity,),
    )

    assert decision.allowed is False
    assert decision.error_code == (
        "duplicate_tool_call"
    )
    assert decision.call_identity == identity
    print("PASS: identical prior Tool call is rejected")


def test_distinct_identity_is_allowed() -> None:
    decision = evaluate(
        issue_id=17,
        tool_call_count=1,
        max_tool_calls=3,
        prior_call_identities=(
            candidate_identity(issue_id=18),
        ),
    )

    assert decision.allowed is True
    print("PASS: distinct Tool call identity is allowed")


def test_invalid_counts_are_rejected() -> None:
    invalid_cases = (
        (-1, 3),
        (True, 3),
        (0, 0),
        (0, -1),
        (0, True),
    )

    for tool_call_count, max_tool_calls in invalid_cases:
        expect_raises(
            ValueError,
            lambda tool_call_count=tool_call_count,
            max_tool_calls=max_tool_calls: (
                AgentToolExecutionPolicyService()
                .evaluate(
                    tool_name="search_knowledge",
                    arguments={"issue_id": 17},
                    tool_call_count=tool_call_count,
                    max_tool_calls=max_tool_calls,
                    prior_call_identities=(),
                )
            ),
        )

    print("PASS: invalid Tool call counts are rejected")


def test_snapshot_count_mismatch_is_rejected() -> None:
    error = expect_raises(
        ValueError,
        lambda: evaluate(
            tool_call_count=1,
            max_tool_calls=3,
            prior_call_identities=(),
        ),
    )

    assert "must match" in str(error)
    print("PASS: incomplete identity snapshot is rejected")


def test_malformed_identity_snapshot_is_rejected() -> None:
    invalid_snapshots = (
        "search_knowledge:digest",
        ("",),
        (" identity",),
        (17,),
    )

    for snapshot in invalid_snapshots:
        expect_raises(
            (TypeError if isinstance(snapshot, str) else ValueError),
            lambda snapshot=snapshot: (
                AgentToolExecutionPolicyService()
                .evaluate(
                    tool_name="search_knowledge",
                    arguments={"issue_id": 17},
                    tool_call_count=1,
                    max_tool_calls=3,
                    prior_call_identities=snapshot,
                )
            ),
        )

    print("PASS: malformed identity snapshots are rejected")


def test_unapproved_tool_is_rejected_by_contract() -> None:
    error = expect_raises(
        AgentToolContractError,
        lambda: AgentToolExecutionPolicyService()
        .evaluate(
            tool_name="unapproved_tool",
            arguments={"issue_id": 17},
            tool_call_count=0,
            max_tool_calls=3,
            prior_call_identities=(),
        ),
    )

    assert error.error_code == "unapproved_tool"
    print("PASS: unapproved Tool is rejected by Contract")


def test_invalid_arguments_are_rejected_by_contract() -> None:
    error = expect_raises(
        AgentToolContractError,
        lambda: AgentToolExecutionPolicyService()
        .evaluate(
            tool_name="search_knowledge",
            arguments={"issue_id": 0},
            tool_call_count=0,
            max_tool_calls=3,
            prior_call_identities=(),
        ),
    )

    assert error.error_code == (
        "invalid_tool_arguments"
    )
    print("PASS: invalid arguments are rejected by Contract")


def test_source_is_pure_and_retry_free() -> None:
    source_path = (
        BACKEND_ROOT
        / "app"
        / "services"
        / "agent_tool_execution_policy_service.py"
    )
    source = source_path.read_text(encoding="utf-8")

    forbidden = (
        "sqlalchemy",
        "Session",
        "db.",
        "AgentRun",
        "AgentStep",
        "AgentToolCall",
        "AgentRunnerService",
        "state_json",
        "commit(",
        "rollback(",
        "flush(",
        "refresh(",
        "retry",
        "time.sleep(",
        "asyncio.sleep(",
    )
    found = [
        token for token in forbidden
        if token in source
    ]
    assert not found, found
    assert "validate_arguments(" in source
    assert "max_tool_calls_reached" in source
    assert "duplicate_tool_call" in source
    print("PASS: policy source is pure and retry-free")


def main() -> None:
    tests = (
        test_version_is_frozen,
        test_fresh_candidate_is_allowed,
        test_arguments_are_normalized,
        test_normalized_arguments_are_immutable,
        test_identity_is_stable,
        test_limit_is_rejected,
        test_over_limit_is_rejected,
        test_duplicate_identity_is_rejected,
        test_distinct_identity_is_allowed,
        test_invalid_counts_are_rejected,
        test_snapshot_count_mismatch_is_rejected,
        test_malformed_identity_snapshot_is_rejected,
        test_unapproved_tool_is_rejected_by_contract,
        test_invalid_arguments_are_rejected_by_contract,
        test_source_is_pure_and_retry_free,
    )

    for test in tests:
        test()

    print(
        "Agent Tool Execution Policy assertions "
        "passed (15/15)"
    )


if __name__ == "__main__":
    main()
