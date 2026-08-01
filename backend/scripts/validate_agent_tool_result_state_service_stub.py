from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import inspect
import sys
from typing import Callable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.agent_guarded_tool_execution_service import (
    AgentGuardedToolExecutionOutcome,
)
from app.services.agent_tool_registry import (
    CALCULATE_DELIVERY_RISK_TOOL,
    GET_ANALYSIS_HISTORY_TOOL,
    SEARCH_KNOWLEDGE_TOOL,
    approved_agent_tool_registry,
)
from app.services.agent_tool_result_state_service import (
    AGENT_TOOL_RESULT_STATE_VERSION,
    AgentToolResultStateError,
    AgentToolResultStateOutcome,
    AgentToolResultStateService,
)
from app.services.agent_tool_selection_service import (
    AGENT_TOOL_SELECTION_VERSION,
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


def selected_tool(
    tool_name: str,
    *,
    call_identity: str | None = None,
) -> dict[str, object]:
    definition = approved_agent_tool_registry.get(
        tool_name
    )
    identity = (
        call_identity
        if call_identity is not None
        else f"{tool_name}:" + ("a" * 64)
    )
    return {
        "selection_version": (
            AGENT_TOOL_SELECTION_VERSION
        ),
        "tool_name": tool_name,
        "tool_version": definition.tool_version,
        "arguments": {"issue_id": 17},
        "call_identity": identity,
        "confidence": 0.91,
        "reason": "Controlled test selection.",
    }


def base_state(
    tool_name: str = SEARCH_KNOWLEDGE_TOOL,
) -> dict[str, object]:
    return {
        "issue_id": 17,
        "selected_tool": selected_tool(
            tool_name
        ),
        "tool_results": [],
        "retrieved_evidence": [],
    }


def guarded_outcome(
    tool_name: str,
    result_json: dict[str, object],
    *,
    call_identity: str | None = None,
    decision_arguments: (
        dict[str, object] | None
    ) = None,
) -> AgentGuardedToolExecutionOutcome:
    selected = selected_tool(
        tool_name,
        call_identity=call_identity,
    )
    decision = SimpleNamespace(
        tool_name=selected["tool_name"],
        tool_version=selected["tool_version"],
        call_identity=selected["call_identity"],
        normalized_arguments=(
            decision_arguments
            if decision_arguments is not None
            else dict(selected["arguments"])
        ),
    )
    execution = SimpleNamespace(
        tool_name=selected["tool_name"],
        tool_version=selected["tool_version"],
        call_identity=selected["call_identity"],
        result_json=result_json,
    )
    return AgentGuardedToolExecutionOutcome(
        decision=decision,
        execution=execution,
    )


def knowledge_result() -> dict[str, object]:
    return {
        "retrieval_status": "succeeded",
        "retrieval_query": "API authentication 401",
        "knowledge_evidence": [
            {
                "citation_id": "K1",
                "rank": 1,
                "chunk_id": 21,
                "document_id": 3,
                "document_title": (
                    "API Authentication Guide"
                ),
                "scope_type": "global",
                "doc_type": "runbook",
                "source_kind": "manual",
                "source_name": "Integration Runbook",
                "source_uri": None,
                "chunk_index": 0,
                "chunk_text": (
                    "Verify token rotation and scope."
                ),
                "similarity_score": 0.91,
            }
        ],
        "knowledge_citations": [
            {
                "citation_id": "K1",
                "document_id": 3,
                "document_title": (
                    "API Authentication Guide"
                ),
                "chunk_id": 21,
                "chunk_index": 0,
                "source_kind": "manual",
                "source_name": "Integration Runbook",
                "source_uri": None,
            }
        ],
        "retrieval_error_code": None,
    }


def history_result() -> dict[str, object]:
    return {
        "issue_id": 17,
        "analysis_count": 1,
        "analyses": [
            {
                "analysis_id": 68,
                "issue_id": 17,
                "analysis_type": "issue_summary",
                "provider": "llm",
                "model_name": "gpt-5.5",
                "prompt_version": (
                    "issue_summarizer_v4_grounded"
                ),
                "issue_summary": "Prior API failure.",
                "possible_root_cause": (
                    "Rotated token was not applied."
                ),
                "recommended_actions": [
                    "Refresh the integration token."
                ],
                "customer_update_draft": (
                    "Engineering is validating the token."
                ),
                "risk_level": "medium",
                "project_impact": (
                    "API synchronization is delayed."
                ),
                "feedback_status": "accepted",
                "feedback_note": None,
                "edited_output": None,
                "retrieval_status": "succeeded",
                "retrieval_query": (
                    "API authentication failure"
                ),
                "knowledge_citations": [],
                "retrieval_error_code": None,
                "knowledge_grounded": False,
                "created_at": (
                    "2026-07-17T10:00:00"
                ),
                "updated_at": (
                    "2026-07-17T10:05:00"
                ),
            }
        ],
    }


def risk_result() -> dict[str, object]:
    return {
        "project_id": 2,
        "overdue_requirements": 1,
        "blocked_issues": 2,
        "critical_issues": 1,
        "delivery_completion_rate": 0.4,
        "risk_level": "high",
    }


def test_version_is_frozen() -> None:
    assert AGENT_TOOL_RESULT_STATE_VERSION == (
        "agent_tool_result_state_v0.1"
    )
    print("PASS: Tool result-state version is frozen")


def test_knowledge_result_maps_evidence() -> None:
    state = base_state()
    outcome = (
        AgentToolResultStateService().apply(
            state,
            guarded_outcome(
                SEARCH_KNOWLEDGE_TOOL,
                knowledge_result(),
            ),
        )
    )

    assert isinstance(
        outcome,
        AgentToolResultStateOutcome,
    )
    update = outcome.to_state_update()
    assert len(update["tool_results"]) == 1
    assert len(update["retrieved_evidence"]) == 1
    evidence = update["retrieved_evidence"][0]
    assert evidence["source_tool"] == (
        SEARCH_KNOWLEDGE_TOOL
    )
    assert evidence["evidence_type"] == (
        "knowledge_chunk"
    )
    print("PASS: search knowledge maps evidence")


def test_history_result_maps_evidence() -> None:
    state = base_state(
        GET_ANALYSIS_HISTORY_TOOL
    )
    outcome = (
        AgentToolResultStateService().apply(
            state,
            guarded_outcome(
                GET_ANALYSIS_HISTORY_TOOL,
                history_result(),
            ),
        )
    )

    evidence = outcome.to_state_update()[
        "retrieved_evidence"
    ]
    assert len(evidence) == 1
    assert evidence[0]["evidence_type"] == (
        "analysis_history"
    )
    assert evidence[0]["payload"][
        "analysis_id"
    ] == 68
    print("PASS: analysis history maps evidence")


def test_risk_result_stays_in_tool_results() -> None:
    state = base_state(
        CALCULATE_DELIVERY_RISK_TOOL
    )
    outcome = (
        AgentToolResultStateService().apply(
            state,
            guarded_outcome(
                CALCULATE_DELIVERY_RISK_TOOL,
                risk_result(),
            ),
        )
    )
    update = outcome.to_state_update()

    assert update["retrieved_evidence"] == []
    assert update["tool_results"][0][
        "result_json"
    ]["risk_level"] == "high"
    print("PASS: delivery risk remains Tool result data")


def test_selected_tool_is_cleared() -> None:
    outcome = (
        AgentToolResultStateService().apply(
            base_state(),
            guarded_outcome(
                SEARCH_KNOWLEDGE_TOOL,
                knowledge_result(),
            ),
        )
    )

    assert outcome.to_state_update()[
        "selected_tool"
    ] is None
    print("PASS: completed selected_tool is cleared")


def test_prior_state_is_appended() -> None:
    state = base_state(
        GET_ANALYSIS_HISTORY_TOOL
    )
    prior_identity = (
        f"{SEARCH_KNOWLEDGE_TOOL}:"
        f"{'b' * 64}"
    )
    prior_result = {
        "tool_name": SEARCH_KNOWLEDGE_TOOL,
        "tool_version": (
            approved_agent_tool_registry
            .get(SEARCH_KNOWLEDGE_TOOL)
            .tool_version
        ),
        "call_identity": prior_identity,
        "arguments": {"issue_id": 17},
        "result_json": {
            "retrieval_status": "no_results"
        },
        "execution_status": "completed",
    }
    prior_evidence = {
        "source_tool": SEARCH_KNOWLEDGE_TOOL,
        "source_call_identity": prior_identity,
        "evidence_type": "knowledge_chunk",
        "payload": {"chunk_id": 10},
    }
    state["tool_results"] = [prior_result]
    state["retrieved_evidence"] = [
        prior_evidence
    ]

    outcome = (
        AgentToolResultStateService().apply(
            state,
            guarded_outcome(
                GET_ANALYSIS_HISTORY_TOOL,
                history_result(),
            ),
        )
    )
    update = outcome.to_state_update()

    assert len(update["tool_results"]) == 2
    assert len(update["retrieved_evidence"]) == 2
    assert update["tool_results"][0] == prior_result
    assert update["retrieved_evidence"][0] == (
        prior_evidence
    )
    print("PASS: prior controlled state is appended")


def test_input_state_is_not_mutated() -> None:
    state = base_state()
    original_selected = dict(
        state["selected_tool"]
    )

    AgentToolResultStateService().apply(
        state,
        guarded_outcome(
            SEARCH_KNOWLEDGE_TOOL,
            knowledge_result(),
        ),
    )

    assert state["selected_tool"] == (
        original_selected
    )
    assert state["tool_results"] == []
    assert state["retrieved_evidence"] == []
    print("PASS: input state is not mutated")


def test_duplicate_call_identity_is_rejected() -> None:
    state = base_state()
    identity = state["selected_tool"][
        "call_identity"
    ]
    state["tool_results"] = [
        {
            "tool_name": SEARCH_KNOWLEDGE_TOOL,
            "tool_version": (
                state["selected_tool"][
                    "tool_version"
                ]
            ),
            "call_identity": identity,
            "arguments": {"issue_id": 17},
            "result_json": {
                "retrieval_status": "no_results"
            },
            "execution_status": "completed",
        }
    ]

    error = expect_raises(
        AgentToolResultStateError,
        lambda: AgentToolResultStateService()
        .apply(
            state,
            guarded_outcome(
                SEARCH_KNOWLEDGE_TOOL,
                knowledge_result(),
            ),
        ),
    )

    assert error.error_code == (
        "duplicate_tool_result"
    )
    print("PASS: duplicate call identity is rejected")


def test_missing_selected_tool_is_rejected() -> None:
    state = base_state()
    state["selected_tool"] = None

    error = expect_raises(
        AgentToolResultStateError,
        lambda: AgentToolResultStateService()
        .apply(
            state,
            guarded_outcome(
                SEARCH_KNOWLEDGE_TOOL,
                knowledge_result(),
            ),
        ),
    )

    assert error.error_code == (
        "missing_selected_tool"
    )
    print("PASS: missing selected_tool is rejected")


def test_invalid_selected_tool_shape_is_rejected() -> None:
    state = base_state()
    del state["selected_tool"]["reason"]

    error = expect_raises(
        AgentToolResultStateError,
        lambda: AgentToolResultStateService()
        .apply(
            state,
            guarded_outcome(
                SEARCH_KNOWLEDGE_TOOL,
                knowledge_result(),
            ),
        ),
    )

    assert error.error_code == (
        "invalid_selected_tool"
    )
    print("PASS: invalid selected_tool shape is rejected")


def test_tool_name_mismatch_is_rejected() -> None:
    state = base_state()
    outcome = guarded_outcome(
        GET_ANALYSIS_HISTORY_TOOL,
        history_result(),
    )

    error = expect_raises(
        AgentToolResultStateError,
        lambda: AgentToolResultStateService()
        .apply(state, outcome),
    )

    assert error.error_code == (
        "selected_tool_name_mismatch"
    )
    print("PASS: Tool name mismatch is rejected")


def test_tool_version_mismatch_is_rejected() -> None:
    state = base_state()
    outcome = guarded_outcome(
        SEARCH_KNOWLEDGE_TOOL,
        knowledge_result(),
    )
    outcome.execution.tool_version = "wrong-version"

    error = expect_raises(
        AgentToolResultStateError,
        lambda: AgentToolResultStateService()
        .apply(state, outcome),
    )

    assert error.error_code == (
        "execution_tool_version_mismatch"
    )
    print("PASS: Tool version mismatch is rejected")


def test_call_identity_mismatch_is_rejected() -> None:
    state = base_state()
    outcome = guarded_outcome(
        SEARCH_KNOWLEDGE_TOOL,
        knowledge_result(),
        call_identity=(
            f"{SEARCH_KNOWLEDGE_TOOL}:"
            f"{'c' * 64}"
        ),
    )

    error = expect_raises(
        AgentToolResultStateError,
        lambda: AgentToolResultStateService()
        .apply(state, outcome),
    )

    assert error.error_code == (
        "selected_call_identity_mismatch"
    )
    print("PASS: call identity mismatch is rejected")


def test_policy_arguments_mismatch_is_rejected() -> None:
    state = base_state()
    outcome = guarded_outcome(
        SEARCH_KNOWLEDGE_TOOL,
        knowledge_result(),
        decision_arguments={"issue_id": 18},
    )

    error = expect_raises(
        AgentToolResultStateError,
        lambda: AgentToolResultStateService()
        .apply(state, outcome),
    )

    assert error.error_code == (
        "policy_execution_mismatch"
    )
    print("PASS: policy argument mismatch is rejected")


def test_malformed_evidence_results_are_rejected() -> None:
    malformed_cases = (
        {
            **knowledge_result(),
            "retrieval_status": "unknown",
        },
        {
            **knowledge_result(),
            "retrieval_status": "no_results",
        },
        {
            "issue_id": 17,
            "analysis_count": 2,
            "analyses": history_result()[
                "analyses"
            ],
        },
    )

    tool_names = (
        SEARCH_KNOWLEDGE_TOOL,
        SEARCH_KNOWLEDGE_TOOL,
        GET_ANALYSIS_HISTORY_TOOL,
    )

    for tool_name, result in zip(
        tool_names,
        malformed_cases,
        strict=True,
    ):
        state = base_state(tool_name)
        expect_raises(
            AgentToolResultStateError,
            lambda state=state,
            tool_name=tool_name,
            result=result: (
                AgentToolResultStateService()
                .apply(
                    state,
                    guarded_outcome(
                        tool_name,
                        result,
                    ),
                )
            ),
        )

    print("PASS: malformed evidence results are rejected")


def test_source_is_pure_and_controlled() -> None:
    source = inspect.getsource(
        AgentToolResultStateService
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
        "execute_once(",
        "AgentToolCall",
        "create_tool_call(",
    )
    found = [
        token for token in forbidden
        if token in source
    ]
    assert not found, found
    assert "selected_tool" in source
    assert "tool_results" in source
    assert "retrieved_evidence" in source
    assert "knowledge_chunk" in source
    assert "analysis_history" in source
    assert "duplicate_tool_result" in source

    print("PASS: result-state mapping is pure and controlled")


def main() -> None:
    tests = (
        test_version_is_frozen,
        test_knowledge_result_maps_evidence,
        test_history_result_maps_evidence,
        test_risk_result_stays_in_tool_results,
        test_selected_tool_is_cleared,
        test_prior_state_is_appended,
        test_input_state_is_not_mutated,
        test_duplicate_call_identity_is_rejected,
        test_missing_selected_tool_is_rejected,
        test_invalid_selected_tool_shape_is_rejected,
        test_tool_name_mismatch_is_rejected,
        test_tool_version_mismatch_is_rejected,
        test_call_identity_mismatch_is_rejected,
        test_policy_arguments_mismatch_is_rejected,
        test_malformed_evidence_results_are_rejected,
        test_source_is_pure_and_controlled,
    )

    for test in tests:
        test()

    print(
        "Agent Tool Result State assertions "
        "passed (16/16)"
    )


if __name__ == "__main__":
    main()
