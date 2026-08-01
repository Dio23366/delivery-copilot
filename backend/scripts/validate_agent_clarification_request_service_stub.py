from __future__ import annotations

from pathlib import Path
import inspect
import sys
from typing import Callable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.agent_clarification_request_service import (
    AGENT_CLARIFICATION_REQUEST_VERSION,
    CLARIFICATION_INTERRUPT_REASON,
    CLARIFICATION_RESUME_NODE,
    REQUEST_CLARIFICATION_NODE,
    WAITING_FOR_CLARIFICATION_STATUS,
    AgentClarificationRequest,
    AgentClarificationRequestError,
    AgentClarificationRequestService,
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


def tool_result() -> dict[str, object]:
    return {
        "tool_name": "search_knowledge",
        "tool_version": "grounded_retrieval_v1",
        "call_identity": (
            "search_knowledge:"
            f"{'a' * 64}"
        ),
        "arguments": {"issue_id": 17},
        "result_json": {
            "retrieval_status": "no_results"
        },
        "execution_status": "completed",
    }


def base_state() -> dict[str, object]:
    return {
        "issue_id": 17,
        "issue_title": (
            "API authentication fails after token rotation"
        ),
        "issue_description": (
            "Requests return 401 after credentials changed."
        ),
        "issue_type": "API",
        "severity": "high",
        "status": "investigating",
        "project_name": "Enterprise API Rollout",
        "delivery_stage": "Implementation",
        "triage_confirmed": True,
        "selected_tool": None,
        "tool_results": [tool_result()],
        "retrieved_evidence": [],
        "evidence_sufficient": False,
        "evidence_reason": (
            "Approved Tool evidence is insufficient."
        ),
    }


def create(
    state: dict[str, object] | None = None,
) -> AgentClarificationRequest:
    return (
        AgentClarificationRequestService()
        .create_request(
            state
            if state is not None
            else base_state()
        )
    )


def test_version_and_wait_contract_are_frozen() -> None:
    assert AGENT_CLARIFICATION_REQUEST_VERSION == (
        "agent_clarification_request_v0.1"
    )
    assert REQUEST_CLARIFICATION_NODE == (
        "request_clarification"
    )
    assert WAITING_FOR_CLARIFICATION_STATUS == (
        "waiting_for_clarification"
    )
    assert CLARIFICATION_RESUME_NODE == (
        "route_investigation"
    )
    assert CLARIFICATION_INTERRUPT_REASON == (
        "additional_information_required"
    )
    print("PASS: Clarification wait contract is frozen")


def test_authentication_question_is_focused() -> None:
    request = create()

    assert isinstance(
        request,
        AgentClarificationRequest,
    )
    assert "authentication method" in (
        request.clarification_question
    )
    assert "token change" in (
        request.clarification_question
    )
    assert "error code" in (
        request.clarification_question
    )
    print("PASS: authentication question is focused")


def test_deployment_question_is_focused() -> None:
    state = base_state()
    state.update(
        {
            "issue_title": (
                "Deployment failed in production"
            ),
            "issue_description": (
                "Release stopped after configuration update."
            ),
            "issue_type": "Deployment",
        }
    )

    request = create(state)

    assert "environment and version" in (
        request.clarification_question
    )
    assert "deployment or configuration" in (
        request.clarification_question
    )
    assert "error log" in (
        request.clarification_question
    )
    print("PASS: deployment question is focused")


def test_data_question_is_focused() -> None:
    state = base_state()
    state.update(
        {
            "issue_title": "Customer data sync mismatch",
            "issue_description": (
                "Integration produces incomplete records."
            ),
            "issue_type": "Data",
        }
    )

    request = create(state)

    assert "affected record" in (
        request.clarification_question
    )
    assert "source and target systems" in (
        request.clarification_question
    )
    assert "expected versus actual" in (
        request.clarification_question
    )
    print("PASS: data question is focused")


def test_customer_wait_question_is_focused() -> None:
    state = base_state()
    state.update(
        {
            "issue_title": "Customer confirmation pending",
            "issue_description": (
                "Need client-side reproduction details."
            ),
            "issue_type": "Other",
            "status": "waiting_on_customer",
        }
    )

    request = create(state)

    assert "customer's latest action" in (
        request.clarification_question
    )
    assert "exact error observed" in (
        request.clarification_question
    )
    assert "still be reproduced" in (
        request.clarification_question
    )
    print("PASS: customer-wait question is focused")


def test_fallback_question_is_focused() -> None:
    state = base_state()
    state.update(
        {
            "issue_title": "Unexpected workflow failure",
            "issue_description": "Unknown failure.",
            "issue_type": "Other",
            "status": "investigating",
            "evidence_reason": (
                "Current evidence does not explain the issue."
            ),
        }
    )

    request = create(state)

    assert "failure timestamp" in (
        request.clarification_question
    )
    assert "reproduction steps" in (
        request.clarification_question
    )
    assert "original error message" in (
        request.clarification_question
    )
    print("PASS: fallback question remains focused")


def test_state_update_is_controlled() -> None:
    request = create()

    update = request.to_state_update()
    assert set(update) == {
        "clarification_question",
        "clarification_response",
    }
    assert update["clarification_response"] is None
    assert update["clarification_question"] == (
        request.clarification_question
    )

    payload = request.as_dict()
    assert set(payload) == {
        "request_version",
        "node_name",
        "clarification_question",
        "evidence_reason",
        "waiting_status",
        "resume_node",
        "interrupt_reason",
    }
    print("PASS: Clarification state update is controlled")


def test_input_state_is_not_mutated() -> None:
    state = base_state()
    original = {
        key: value
        for key, value in state.items()
    }

    create(state)

    assert state == original
    assert "clarification_question" not in state
    print("PASS: input Agent state is not mutated")


def test_unconfirmed_triage_is_rejected() -> None:
    state = base_state()
    state["triage_confirmed"] = False

    error = expect_raises(
        AgentClarificationRequestError,
        lambda: create(state),
    )

    assert error.error_code == (
        "triage_not_confirmed"
    )
    print("PASS: unconfirmed triage is rejected")


def test_pending_selected_tool_is_rejected() -> None:
    state = base_state()
    state["selected_tool"] = {
        "tool_name": "search_knowledge"
    }

    error = expect_raises(
        AgentClarificationRequestError,
        lambda: create(state),
    )

    assert error.error_code == (
        "tool_execution_incomplete"
    )
    print("PASS: pending selected_tool is rejected")


def test_sufficient_evidence_is_rejected() -> None:
    state = base_state()
    state["evidence_sufficient"] = True

    error = expect_raises(
        AgentClarificationRequestError,
        lambda: create(state),
    )

    assert error.error_code == (
        "clarification_not_required"
    )
    print("PASS: sufficient evidence is rejected")


def test_invalid_evidence_reason_is_rejected() -> None:
    for value in (
        None,
        "",
        "  invalid  ",
        123,
    ):
        state = base_state()
        state["evidence_reason"] = value

        error = expect_raises(
            AgentClarificationRequestError,
            lambda state=state: create(state),
        )
        assert error.error_code == (
            "invalid_evidence_reason"
        )

    print("PASS: invalid evidence reason is rejected")


def test_missing_tool_results_are_rejected() -> None:
    for value in (
        None,
        [],
        "invalid",
    ):
        state = base_state()
        state["tool_results"] = value

        error = expect_raises(
            AgentClarificationRequestError,
            lambda state=state: create(state),
        )
        assert error.error_code == (
            "missing_tool_results"
        )

    print("PASS: missing Tool results are rejected")


def test_incomplete_tool_result_is_rejected() -> None:
    state = base_state()
    state["tool_results"][0][
        "execution_status"
    ] = "failed"

    error = expect_raises(
        AgentClarificationRequestError,
        lambda: create(state),
    )

    assert error.error_code == (
        "invalid_tool_results"
    )
    print("PASS: incomplete Tool result is rejected")


def test_existing_question_is_rejected() -> None:
    state = base_state()
    state["clarification_question"] = (
        "Existing question"
    )

    error = expect_raises(
        AgentClarificationRequestError,
        lambda: create(state),
    )

    assert error.error_code == (
        "clarification_already_requested"
    )
    print("PASS: existing question is rejected")


def test_existing_response_is_rejected() -> None:
    state = base_state()
    state["clarification_response"] = (
        "Existing answer"
    )

    error = expect_raises(
        AgentClarificationRequestError,
        lambda: create(state),
    )

    assert error.error_code == (
        "clarification_already_supplied"
    )
    print("PASS: existing response is rejected")


def test_missing_issue_context_is_rejected() -> None:
    state = base_state()
    for key in (
        "issue_title",
        "issue_description",
        "issue_type",
        "severity",
        "status",
        "project_name",
        "delivery_stage",
    ):
        state[key] = None

    error = expect_raises(
        AgentClarificationRequestError,
        lambda: create(state),
    )

    assert error.error_code == (
        "missing_issue_context"
    )
    print("PASS: missing Issue context is rejected")


def test_output_is_json_safe() -> None:
    request = create()

    assert request.as_dict()[
        "clarification_question"
    ] == request.clarification_question
    assert request.to_state_update()[
        "clarification_response"
    ] is None
    print("PASS: Clarification output is JSON-safe")


def test_source_is_pure_and_deterministic() -> None:
    source = inspect.getsource(
        AgentClarificationRequestService
    )

    forbidden = (
        "sqlalchemy",
        "Session",
        "db.",
        "commit(",
        "rollback(",
        "flush(",
        "refresh(",
        "AgentRunnerService",
        "AgentOrchestrationService",
        "execute_once(",
        "AgentToolCall",
        "openai",
        "llm",
        "random",
        "datetime.now",
    )
    found = [
        token for token in forbidden
        if token in source
    ]

    assert not found, found
    assert "_build_question(" in source
    assert "evidence_reason" in source
    assert "issue_title" in source
    assert "WAITING_FOR_CLARIFICATION_STATUS" in (
        inspect.getsource(
            AgentClarificationRequest
        )
    )

    state = base_state()
    first = create(state)
    second = create(state)
    assert first == second
    print("PASS: Clarification service is pure and deterministic")


def main() -> None:
    tests = (
        test_version_and_wait_contract_are_frozen,
        test_authentication_question_is_focused,
        test_deployment_question_is_focused,
        test_data_question_is_focused,
        test_customer_wait_question_is_focused,
        test_fallback_question_is_focused,
        test_state_update_is_controlled,
        test_input_state_is_not_mutated,
        test_unconfirmed_triage_is_rejected,
        test_pending_selected_tool_is_rejected,
        test_sufficient_evidence_is_rejected,
        test_invalid_evidence_reason_is_rejected,
        test_missing_tool_results_are_rejected,
        test_incomplete_tool_result_is_rejected,
        test_existing_question_is_rejected,
        test_existing_response_is_rejected,
        test_missing_issue_context_is_rejected,
        test_output_is_json_safe,
        test_source_is_pure_and_deterministic,
    )

    for test in tests:
        test()

    print(
        "Agent Clarification Request assertions "
        "passed (19/19)"
    )


if __name__ == "__main__":
    main()
