from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError


BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.api import agent as agent_api  # noqa: E402
from app.models import AgentRun, Issue  # noqa: E402


def make_query(
    *,
    first_value=None,
) -> Mock:
    query = Mock()
    query.filter.return_value = query
    query.with_for_update.return_value = query
    query.order_by.return_value = query
    query.first.return_value = first_value
    query.all.return_value = []
    return query


def make_run(
    *,
    status: str = "running",
    run_id: str = "run-001",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=101,
        run_id=run_id,
        issue_id=17,
        analysis_log_id=None,
        graph_version="agent_mvp_v0.1",
        current_node="load_issue",
        run_status=status,
        step_count=0,
        tool_call_count=0,
        retry_count=0,
        state_json={"issue_id": 17},
        waiting_since=None,
        resume_node=None,
        error_code=None,
        error_message=None,
        started_at=None,
        completed_at=None,
        created_at=None,
        updated_at=None,
    )


def serialize_run(
    db: Mock,
    run: SimpleNamespace,
) -> dict[str, object]:
    del db

    return {
        "run_id": run.run_id,
        "run_status": run.run_status,
    }


def test_create_uses_server_contract() -> None:
    issue = SimpleNamespace(id=17)
    issue_query = make_query(first_value=issue)
    run_query = make_query(first_value=None)
    db = Mock()

    def query_side_effect(model: object) -> Mock:
        if model is Issue:
            return issue_query
        if model is AgentRun:
            return run_query
        raise AssertionError(
            f"Unexpected query model: {model}"
        )

    db.query.side_effect = query_side_effect

    agent_run = SimpleNamespace(
        run_id="run-001",
        run_status="waiting_for_triage_confirmation",
    )
    runner_service = Mock()
    (
        runner_service
        .start_and_run_to_triage_wait
        .return_value
    ) = SimpleNamespace(agent_run=agent_run)
    serialize_run = Mock(
        return_value={
            "run_id": "run-001",
            "run_status": (
                "waiting_for_triage_confirmation"
            ),
        }
    )

    with (
        patch.object(
            agent_api,
            "agent_runner_service",
            runner_service,
        ),
        patch.object(
            agent_api,
            "_serialize_agent_run",
            serialize_run,
        ),
        patch.object(
            agent_api,
            "uuid4",
            return_value="fixed-run-id",
        ),
    ):
        result = agent_api.create_agent_run(
            payload=agent_api.AgentRunCreatePayload(
                issue_id=17
            ),
            db=db,
        )

    assert result == {
        "run_id": "run-001",
        "run_status": (
            "waiting_for_triage_confirmation"
        ),
    }
    (
        runner_service
        .start_and_run_to_triage_wait
        .assert_called_once_with(
            db,
            run_id="fixed-run-id",
            issue_id=17,
            graph_version=(
                agent_api.AGENT_GRAPH_VERSION
            ),
            initial_state={"issue_id": 17},
        )
    )
    serialize_run.assert_called_once_with(
        db,
        agent_run,
    )
    issue_query.with_for_update.assert_called_once_with()
    db.commit.assert_not_called()


def test_create_returns_existing_active_run() -> None:
    issue = SimpleNamespace(id=17)
    existing_run = SimpleNamespace(
        run_id="run-existing",
        run_status="waiting_for_clarification",
    )
    issue_query = make_query(first_value=issue)
    run_query = make_query(first_value=existing_run)
    db = Mock()

    def query_side_effect(model: object) -> Mock:
        if model is Issue:
            return issue_query
        if model is AgentRun:
            return run_query
        raise AssertionError(
            f"Unexpected query model: {model}"
        )

    db.query.side_effect = query_side_effect
    runner_service = Mock()
    serialize_run = Mock(
        return_value={
            "run_id": "run-existing",
            "run_status": (
                "waiting_for_clarification"
            ),
        }
    )

    with (
        patch.object(
            agent_api,
            "agent_runner_service",
            runner_service,
        ),
        patch.object(
            agent_api,
            "_serialize_agent_run",
            serialize_run,
        ),
    ):
        result = agent_api.create_agent_run(
            payload=agent_api.AgentRunCreatePayload(
                issue_id=17
            ),
            db=db,
        )

    assert result == {
        "run_id": "run-existing",
        "run_status": "waiting_for_clarification",
    }
    (
        runner_service
        .start_and_run_to_triage_wait
        .assert_not_called()
    )
    serialize_run.assert_called_once_with(
        db,
        existing_run,
    )
    issue_query.with_for_update.assert_called_once_with()
    db.rollback.assert_called_once_with()


def test_create_missing_issue_returns_404() -> None:
    db = Mock()
    db.query.return_value = make_query(
        first_value=None
    )

    try:
        agent_api.create_agent_run(
            payload=agent_api.AgentRunCreatePayload(
                issue_id=999
            ),
            db=db,
        )
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "Issue 不存在"
    else:
        raise AssertionError(
            "Missing Issue should return 404"
        )

    db.rollback.assert_called_once_with()


def test_get_returns_run_detail() -> None:
    db = Mock()
    db.query.return_value = make_query(
        first_value=make_run()
    )

    with patch.object(
        agent_api,
        "_serialize_agent_run",
        serialize_run,
    ):
        result = agent_api.get_agent_run(
            run_id="run-001",
            db=db,
        )

    assert result == {
        "run_id": "run-001",
        "run_status": "running",
    }


def test_get_missing_run_returns_404() -> None:
    db = Mock()
    db.query.return_value = make_query(
        first_value=None
    )

    try:
        agent_api.get_agent_run(
            run_id="missing-run",
            db=db,
        )
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "Agent Run 不存在"
    else:
        raise AssertionError(
            "Missing Agent Run should return 404"
        )


def test_resume_with_triage_result() -> None:
    db = Mock()
    service = Mock()
    runner_service = Mock()

    resumed_run = make_run()
    route_investigation_step = SimpleNamespace(
        id=301,
        node_name="route_investigation",
    )
    advanced_run = make_run()
    advanced_run.current_node = "generate_analysis"
    advanced_run.step_count = 5

    service.resume_waiting_investigation_run.return_value = (
        resumed_run,
        route_investigation_step,
    )
    (
        runner_service
        .advance_investigation_until_boundary
        .return_value
    ) = SimpleNamespace(
        agent_run=advanced_run,
        current_step=SimpleNamespace(
            id=305,
            node_name="generate_analysis",
        ),
        transition_count=4,
        stop_reason="unimplemented_boundary",
        visited_nodes=(
            "route_investigation",
            "select_tool",
            "execute_tool",
            "evaluate_evidence",
        ),
    )
    serialize_run = Mock(
        return_value={
            "run_id": "run-001",
            "run_status": "running",
        }
    )

    with (
        patch.object(
            agent_api,
            "agent_orchestration_service",
            service,
        ),
        patch.object(
            agent_api,
            "agent_runner_service",
            runner_service,
        ),
        patch.object(
            agent_api,
            "_serialize_agent_run",
            serialize_run,
        ),
    ):
        result = agent_api.resume_agent_run(
            run_id="run-001",
            payload=agent_api.AgentRunResumePayload(
                triage_result={
                    "confirmed": True,
                }
            ),
            db=db,
        )

    assert result == {
        "run_id": "run-001",
        "run_status": "running",
    }

    (
        service
        .resume_waiting_investigation_run
        .assert_called_once_with(
            db,
            run_id="run-001",
            triage_result={"confirmed": True},
            clarification_response=None,
        )
    )
    (
        runner_service
        .advance_investigation_until_boundary
        .assert_called_once_with(
            db,
            agent_run=resumed_run,
            current_step=route_investigation_step,
        )
    )
    (
        runner_service
        .advance_investigation_route
        .assert_not_called()
    )
    serialize_run.assert_called_once_with(
        db,
        advanced_run,
    )
    db.commit.assert_not_called()


def test_resume_requires_exactly_one_input() -> None:
    db = Mock()

    payloads = (
        agent_api.AgentRunResumePayload(),
        agent_api.AgentRunResumePayload(
            triage_result={"confirmed": True},
            clarification_response="More context",
        ),
        agent_api.AgentRunResumePayload(
            clarification_response="   ",
        ),
    )

    for payload in payloads:
        try:
            agent_api.resume_agent_run(
                run_id="run-001",
                payload=payload,
                db=db,
            )
        except HTTPException as exc:
            assert exc.status_code == 422
        else:
            raise AssertionError(
                "Invalid Resume payload should fail"
            )


def test_cancel_active_uses_active_path() -> None:
    active_run = make_run(status="running")
    cancelled_run = make_run(
        status="cancelled"
    )

    db = Mock()
    db.query.return_value = make_query(
        first_value=active_run
    )

    service = Mock()
    service.cancel_active_run.return_value = (
        cancelled_run,
        None,
        None,
    )

    with (
        patch.object(
            agent_api,
            "agent_orchestration_service",
            service,
        ),
        patch.object(
            agent_api,
            "_serialize_agent_run",
            serialize_run,
        ),
    ):
        result = agent_api.cancel_agent_run(
            run_id="run-001",
            db=db,
        )

    assert result["run_status"] == "cancelled"

    service.cancel_active_run.assert_called_once_with(
        db,
        run_id="run-001",
    )
    service.cancel_waiting_run.assert_not_called()


def test_cancel_waiting_uses_waiting_path() -> None:
    waiting_run = make_run(
        status="waiting_for_clarification"
    )
    cancelled_run = make_run(
        status="cancelled"
    )

    db = Mock()
    db.query.return_value = make_query(
        first_value=waiting_run
    )

    service = Mock()
    service.cancel_waiting_run.return_value = (
        cancelled_run
    )

    with (
        patch.object(
            agent_api,
            "agent_orchestration_service",
            service,
        ),
        patch.object(
            agent_api,
            "_serialize_agent_run",
            serialize_run,
        ),
    ):
        result = agent_api.cancel_agent_run(
            run_id="run-001",
            db=db,
        )

    assert result["run_status"] == "cancelled"

    service.cancel_waiting_run.assert_called_once_with(
        db,
        run_id="run-001",
    )
    service.cancel_active_run.assert_not_called()


def test_terminal_and_service_errors() -> None:
    terminal_db = Mock()
    terminal_db.query.return_value = make_query(
        first_value=make_run(
            status="completed"
        )
    )

    try:
        agent_api.cancel_agent_run(
            run_id="run-001",
            db=terminal_db,
        )
    except HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError(
            "Terminal Run cancellation should fail"
        )

    resume_db = Mock()
    resume_service = Mock()

    (
        resume_service
        .resume_waiting_investigation_run
        .side_effect
    ) = LookupError("Agent Run not found")

    with patch.object(
        agent_api,
        "agent_orchestration_service",
        resume_service,
    ):
        try:
            agent_api.resume_agent_run(
                run_id="missing-run",
                payload=(
                    agent_api.AgentRunResumePayload(
                        clarification_response=(
                            "Additional context"
                        )
                    )
                ),
                db=resume_db,
            )
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError(
                "LookupError should map to 404"
            )

    issue_query = make_query(
        first_value=SimpleNamespace(id=17)
    )
    run_query = make_query(first_value=None)

    create_db = Mock()

    def query_side_effect(model):
        if model is Issue:
            return issue_query

        if model is AgentRun:
            return run_query

        raise AssertionError(
            f"Unexpected queried model: {model}"
        )

    create_db.query.side_effect = query_side_effect

    create_runner_service = Mock()
    (
        create_runner_service
        .start_and_run_to_triage_wait
        .side_effect
    ) = SQLAlchemyError(
        "database failure"
    )

    with patch.object(
        agent_api,
        "agent_runner_service",
        create_runner_service,
    ):
        try:
            agent_api.create_agent_run(
                payload=(
                    agent_api.AgentRunCreatePayload(
                        issue_id=17
                    )
                ),
                db=create_db,
            )
        except HTTPException as exc:
            assert exc.status_code == 500
        else:
            raise AssertionError(
                "SQLAlchemyError should map to 500"
            )

    create_db.rollback.assert_called_once_with()


def main() -> None:
    test_create_uses_server_contract()
    test_create_returns_existing_active_run()
    test_create_missing_issue_returns_404()
    test_get_returns_run_detail()
    test_get_missing_run_returns_404()
    test_resume_with_triage_result()
    test_resume_requires_exactly_one_input()
    test_cancel_active_uses_active_path()
    test_cancel_waiting_uses_waiting_path()
    test_terminal_and_service_errors()

    print(
        "Agent HTTP API stub assertions passed"
    )


if __name__ == "__main__":
    main()
