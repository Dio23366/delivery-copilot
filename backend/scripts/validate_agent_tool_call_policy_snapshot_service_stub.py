from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
from typing import Callable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.agent_tool_call_policy_snapshot_service import (
    AGENT_TOOL_CALL_POLICY_SNAPSHOT_VERSION,
    AgentToolCallPolicySnapshot,
    AgentToolCallPolicySnapshotError,
    AgentToolCallPolicySnapshotService,
)
from app.services.agent_tool_contract_service import (
    agent_tool_contract_service,
)


class FakeScalarResult:
    def __init__(
        self,
        rows: tuple[object, ...],
    ) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return list(self._rows)


class FakeSession:
    def __init__(
        self,
        *,
        agent_run: object | None,
        tool_calls: tuple[object, ...],
    ) -> None:
        self.agent_run = agent_run
        self.tool_calls = tool_calls
        self.scalar_statements: list[object] = []
        self.scalars_statements: list[object] = []

    def scalar(self, statement: object) -> object | None:
        self.scalar_statements.append(statement)
        return self.agent_run

    def scalars(
        self,
        statement: object,
    ) -> FakeScalarResult:
        self.scalars_statements.append(statement)
        return FakeScalarResult(self.tool_calls)


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


def make_call(
    *,
    tool_name: str = "search_knowledge",
    tool_version: str = "grounded_retrieval_v1",
    issue_id: int | str = 17,
    arguments_json: object | None = None,
) -> object:
    return SimpleNamespace(
        tool_name=tool_name,
        tool_version=tool_version,
        arguments_json=(
            arguments_json
            if arguments_json is not None
            else {"issue_id": issue_id}
        ),
    )


def make_run(
    *,
    tool_call_count: object,
) -> object:
    return SimpleNamespace(
        id=41,
        run_id="run-001",
        tool_call_count=tool_call_count,
    )


def load_snapshot(
    *,
    tool_calls: tuple[object, ...] = (),
    tool_call_count: object = 0,
) -> tuple[
    AgentToolCallPolicySnapshot,
    FakeSession,
]:
    db = FakeSession(
        agent_run=make_run(
            tool_call_count=tool_call_count
        ),
        tool_calls=tool_calls,
    )
    snapshot = (
        AgentToolCallPolicySnapshotService().load(
            db,
            run_id="run-001",
        )
    )
    return snapshot, db


def identity(
    tool_name: str,
    issue_id: int | str,
) -> str:
    return (
        agent_tool_contract_service
        .validate_arguments(
            tool_name,
            {"issue_id": issue_id},
        )
        .call_identity
    )


def test_version_is_frozen() -> None:
    assert (
        AGENT_TOOL_CALL_POLICY_SNAPSHOT_VERSION
        == "agent_tool_call_policy_snapshot_v0.1"
    )
    print("PASS: snapshot version is frozen")


def test_empty_snapshot_is_valid() -> None:
    snapshot, db = load_snapshot()

    assert isinstance(
        snapshot,
        AgentToolCallPolicySnapshot,
    )
    assert snapshot.run_id == "run-001"
    assert snapshot.tool_call_count == 0
    assert snapshot.prior_call_identities == ()
    assert len(db.scalar_statements) == 1
    assert len(db.scalars_statements) == 1
    print("PASS: empty run snapshot is valid")


def test_all_rows_generate_stable_identities() -> None:
    calls = (
        make_call(
            tool_name="search_knowledge",
            issue_id="17",
        ),
        make_call(
            tool_name="get_analysis_history",
            tool_version="analysis_history_v1",
            issue_id=17,
        ),
        make_call(
            tool_name="calculate_delivery_risk",
            tool_version="delivery_risk_v1",
            issue_id=17,
        ),
    )

    snapshot, _ = load_snapshot(
        tool_calls=calls,
        tool_call_count=3,
    )

    assert snapshot.prior_call_identities == (
        identity("search_knowledge", 17),
        identity("get_analysis_history", 17),
        identity("calculate_delivery_risk", 17),
    )
    print("PASS: persisted rows reconstruct stable identities")


def test_query_is_run_scoped_and_ordered() -> None:
    _, db = load_snapshot()

    run_statement = str(
        db.scalar_statements[0]
    )
    calls_statement = str(
        db.scalars_statements[0]
    )

    assert "agent_runs.run_id" in run_statement
    assert "agent_tool_calls" in calls_statement
    assert "agent_steps" in calls_statement
    assert "agent_steps.agent_run_id" in calls_statement
    assert "ORDER BY agent_steps.step_index" in (
        calls_statement
    )
    assert "agent_tool_calls.tool_call_index" in (
        calls_statement
    )
    print("PASS: snapshot query is run-scoped and ordered")


def test_count_mismatch_is_rejected() -> None:
    error = expect_raises(
        AgentToolCallPolicySnapshotError,
        lambda: load_snapshot(
            tool_calls=(make_call(),),
            tool_call_count=2,
        ),
    )

    assert error.error_code == (
        "tool_call_count_mismatch"
    )
    print("PASS: persisted count mismatch is rejected")


def test_invalid_persisted_count_is_rejected() -> None:
    for invalid_count in (-1, True, "1"):
        db = FakeSession(
            agent_run=make_run(
                tool_call_count=invalid_count
            ),
            tool_calls=(),
        )
        error = expect_raises(
            AgentToolCallPolicySnapshotError,
            lambda db=db: (
                AgentToolCallPolicySnapshotService()
                .load(db, run_id="run-001")
            ),
        )
        assert error.error_code == (
            "invalid_persisted_tool_call_count"
        )

    print("PASS: invalid persisted counts are rejected")


def test_missing_run_is_rejected() -> None:
    db = FakeSession(
        agent_run=None,
        tool_calls=(),
    )

    error = expect_raises(
        LookupError,
        lambda: (
            AgentToolCallPolicySnapshotService()
            .load(db, run_id="run-404")
        ),
    )

    assert "Agent run not found" in str(error)
    assert db.scalars_statements == []
    print("PASS: missing Run is rejected before Tool query")


def test_invalid_run_id_queries_nothing() -> None:
    invalid_values = (
        "",
        " run-001",
        "run-001 ",
        17,
    )

    for value in invalid_values:
        db = FakeSession(
            agent_run=make_run(tool_call_count=0),
            tool_calls=(),
        )
        expect_raises(
            (
                TypeError
                if not isinstance(value, str)
                else ValueError
            ),
            lambda value=value, db=db: (
                AgentToolCallPolicySnapshotService()
                .load(db, run_id=value)
            ),
        )
        assert db.scalar_statements == []
        assert db.scalars_statements == []

    print("PASS: invalid run_id queries nothing")


def test_non_mapping_arguments_are_rejected() -> None:
    error = expect_raises(
        AgentToolCallPolicySnapshotError,
        lambda: load_snapshot(
            tool_calls=(
                make_call(arguments_json=[]),
            ),
            tool_call_count=1,
        ),
    )

    assert error.error_code == (
        "invalid_persisted_tool_arguments"
    )
    print("PASS: non-object persisted arguments are rejected")


def test_unapproved_persisted_tool_is_rejected() -> None:
    error = expect_raises(
        AgentToolCallPolicySnapshotError,
        lambda: load_snapshot(
            tool_calls=(
                make_call(
                    tool_name="unapproved_tool",
                    tool_version="v1",
                ),
            ),
            tool_call_count=1,
        ),
    )

    assert error.error_code == (
        "invalid_persisted_tool_call"
    )
    print("PASS: unapproved persisted Tool is rejected")


def test_invalid_persisted_arguments_are_rejected() -> None:
    error = expect_raises(
        AgentToolCallPolicySnapshotError,
        lambda: load_snapshot(
            tool_calls=(
                make_call(issue_id=0),
            ),
            tool_call_count=1,
        ),
    )

    assert error.error_code == (
        "invalid_persisted_tool_call"
    )
    print("PASS: invalid persisted arguments are rejected")


def test_version_mismatch_is_rejected() -> None:
    error = expect_raises(
        AgentToolCallPolicySnapshotError,
        lambda: load_snapshot(
            tool_calls=(
                make_call(
                    tool_version="wrong_version",
                ),
            ),
            tool_call_count=1,
        ),
    )

    assert error.error_code == (
        "persisted_tool_version_mismatch"
    )
    print("PASS: persisted Tool version mismatch is rejected")


def test_all_lifecycle_rows_are_counted() -> None:
    calls = tuple(
        make_call(issue_id=value)
        for value in (17, 18, 19, 20)
    )
    snapshot, _ = load_snapshot(
        tool_calls=calls,
        tool_call_count=4,
    )

    assert len(
        snapshot.prior_call_identities
    ) == 4
    print("PASS: snapshot counts every persisted ToolCall row")


def test_snapshot_serialization_is_json_safe() -> None:
    snapshot, _ = load_snapshot(
        tool_calls=(make_call(),),
        tool_call_count=1,
    )

    payload = snapshot.as_dict()

    assert payload["run_id"] == "run-001"
    assert payload["tool_call_count"] == 1
    assert isinstance(
        payload["prior_call_identities"],
        list,
    )
    print("PASS: snapshot serialization is JSON-safe")


def test_source_is_read_only_and_fail_closed() -> None:
    source_path = (
        BACKEND_ROOT
        / "app"
        / "services"
        / "agent_tool_call_policy_snapshot_service.py"
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
        "retry",
    )
    found = [
        token for token in forbidden
        if token in source
    ]
    assert not found, found
    assert "select(AgentRun)" in source
    assert "select(AgentToolCall)" in source
    assert "AgentStep.step_index" in source
    assert "validate_arguments(" in source
    assert "tool_call_count_mismatch" in source
    assert "persisted_tool_version_mismatch" in source
    print("PASS: snapshot source is read-only and fail-closed")


def main() -> None:
    tests = (
        test_version_is_frozen,
        test_empty_snapshot_is_valid,
        test_all_rows_generate_stable_identities,
        test_query_is_run_scoped_and_ordered,
        test_count_mismatch_is_rejected,
        test_invalid_persisted_count_is_rejected,
        test_missing_run_is_rejected,
        test_invalid_run_id_queries_nothing,
        test_non_mapping_arguments_are_rejected,
        test_unapproved_persisted_tool_is_rejected,
        test_invalid_persisted_arguments_are_rejected,
        test_version_mismatch_is_rejected,
        test_all_lifecycle_rows_are_counted,
        test_snapshot_serialization_is_json_safe,
        test_source_is_read_only_and_fail_closed,
    )

    for test in tests:
        test()

    print(
        "Agent ToolCall Policy Snapshot assertions "
        "passed (15/15)"
    )


if __name__ == "__main__":
    main()
