from __future__ import annotations

from pathlib import Path
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
    AgentEvidenceEvaluationService,
)
from app.services.agent_tool_registry import (
    CALCULATE_DELIVERY_RISK_TOOL,
    GET_ANALYSIS_HISTORY_TOOL,
    SEARCH_KNOWLEDGE_TOOL,
    approved_agent_tool_registry,
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


def identity(
    tool_name: str,
    marker: str,
) -> str:
    return f"{tool_name}:{marker * 64}"


def tool_result(
    tool_name: str,
    marker: str,
    result_json: dict[str, object],
) -> dict[str, object]:
    definition = approved_agent_tool_registry.get(
        tool_name
    )
    return {
        "tool_name": tool_name,
        "tool_version": definition.tool_version,
        "call_identity": identity(
            tool_name,
            marker,
        ),
        "arguments": {"issue_id": 17},
        "result_json": result_json,
        "execution_status": "completed",
    }


def evidence(
    *,
    tool_name: str,
    marker: str,
    evidence_type: str,
    payload: dict[str, object],
) -> dict[str, object]:
    return {
        "source_tool": tool_name,
        "source_call_identity": identity(
            tool_name,
            marker,
        ),
        "evidence_type": evidence_type,
        "payload": payload,
    }


def base_state() -> dict[str, object]:
    return {
        "issue_id": 17,
        "triage_confirmed": True,
        "selected_tool": None,
        "tool_results": [
            tool_result(
                SEARCH_KNOWLEDGE_TOOL,
                "a",
                {
                    "retrieval_status": (
                        "no_results"
                    )
                },
            )
        ],
        "retrieved_evidence": [],
        "max_tool_calls": 3,
    }


def all_tool_results() -> list[dict[str, object]]:
    return [
        tool_result(
            SEARCH_KNOWLEDGE_TOOL,
            "a",
            {"retrieval_status": "no_results"},
        ),
        tool_result(
            GET_ANALYSIS_HISTORY_TOOL,
            "b",
            {"analysis_count": 0, "analyses": []},
        ),
        tool_result(
            CALCULATE_DELIVERY_RISK_TOOL,
            "c",
            {"risk_level": "medium"},
        ),
    ]


def test_version_and_nodes_are_frozen() -> None:
    assert AGENT_EVIDENCE_EVALUATION_VERSION == (
        "agent_evidence_evaluation_v0.1"
    )
    assert GENERATE_ANALYSIS_NODE == (
        "generate_analysis"
    )
    assert SELECT_TOOL_NODE == "select_tool"
    assert REQUEST_CLARIFICATION_NODE == (
        "request_clarification"
    )
    assert LIMIT_EXCEEDED_NODE == (
        "limit_exceeded"
    )
    print("PASS: Evidence Evaluation contract is frozen")


def test_usable_knowledge_generates_analysis() -> None:
    state = base_state()
    state["tool_results"][0] = tool_result(
        SEARCH_KNOWLEDGE_TOOL,
        "a",
        {"retrieval_status": "succeeded"},
    )
    state["retrieved_evidence"] = [
        evidence(
            tool_name=SEARCH_KNOWLEDGE_TOOL,
            marker="a",
            evidence_type="knowledge_chunk",
            payload={
                "chunk_id": 21,
                "chunk_text": (
                    "Verify token rotation and scope."
                ),
                "similarity_score": 0.91,
            },
        )
    ]

    decision = (
        AgentEvidenceEvaluationService()
        .evaluate(state)
    )

    assert decision.next_node == (
        GENERATE_ANALYSIS_NODE
    )
    assert decision.evidence_sufficient is True
    assert decision.knowledge_evidence_count == 1
    print("PASS: usable knowledge generates analysis")


def test_accepted_history_generates_analysis() -> None:
    state = base_state()
    state["tool_results"] = [
        tool_result(
            GET_ANALYSIS_HISTORY_TOOL,
            "b",
            {"analysis_count": 1},
        )
    ]
    state["retrieved_evidence"] = [
        evidence(
            tool_name=GET_ANALYSIS_HISTORY_TOOL,
            marker="b",
            evidence_type="analysis_history",
            payload={
                "analysis_id": 68,
                "feedback_status": "accepted",
                "issue_summary": (
                    "A prior token rotation failed."
                ),
                "possible_root_cause": "",
                "recommended_actions": [],
            },
        )
    ]

    decision = (
        AgentEvidenceEvaluationService()
        .evaluate(state)
    )

    assert decision.next_node == (
        GENERATE_ANALYSIS_NODE
    )
    assert decision.history_evidence_count == 1
    print("PASS: accepted history generates analysis")


def test_rejected_history_selects_another_tool() -> None:
    state = base_state()
    state["tool_results"] = [
        tool_result(
            GET_ANALYSIS_HISTORY_TOOL,
            "b",
            {"analysis_count": 1},
        )
    ]
    state["retrieved_evidence"] = [
        evidence(
            tool_name=GET_ANALYSIS_HISTORY_TOOL,
            marker="b",
            evidence_type="analysis_history",
            payload={
                "analysis_id": 67,
                "feedback_status": "rejected",
                "issue_summary": "Rejected draft.",
                "possible_root_cause": "",
                "recommended_actions": [],
            },
        )
    ]

    decision = (
        AgentEvidenceEvaluationService()
        .evaluate(state)
    )

    assert decision.next_node == SELECT_TOOL_NODE
    assert decision.evidence_sufficient is False
    print("PASS: rejected history selects another Tool")


def test_risk_only_selects_another_tool() -> None:
    state = base_state()
    state["tool_results"] = [
        tool_result(
            CALCULATE_DELIVERY_RISK_TOOL,
            "c",
            {"risk_level": "high"},
        )
    ]

    decision = (
        AgentEvidenceEvaluationService()
        .evaluate(state)
    )

    assert decision.next_node == SELECT_TOOL_NODE
    assert SEARCH_KNOWLEDGE_TOOL in (
        decision.unused_tool_names
    )
    print("PASS: risk-only result selects another Tool")


def test_exhausted_tools_request_clarification() -> None:
    state = base_state()
    state["tool_results"] = all_tool_results()
    state["max_tool_calls"] = 3

    decision = (
        AgentEvidenceEvaluationService()
        .evaluate(state)
    )

    assert decision.next_node == (
        REQUEST_CLARIFICATION_NODE
    )
    assert decision.unused_tool_names == ()
    print("PASS: exhausted Tools request clarification")


def test_usable_clarification_generates_analysis() -> None:
    state = base_state()
    state["tool_results"] = all_tool_results()
    state["clarification_response"] = (
        "The token rotated immediately before the failure."
    )

    decision = (
        AgentEvidenceEvaluationService()
        .evaluate(state)
    )

    assert decision.next_node == (
        GENERATE_ANALYSIS_NODE
    )
    assert decision.evidence_sufficient is True
    print("PASS: usable clarification generates analysis")


def test_weak_clarification_hits_limit() -> None:
    state = base_state()
    state["tool_results"] = all_tool_results()
    state["clarification_response"] = "Unknown"

    decision = (
        AgentEvidenceEvaluationService()
        .evaluate(state)
    )

    assert decision.next_node == LIMIT_EXCEEDED_NODE
    assert decision.evidence_sufficient is False
    print("PASS: weak clarification hits limit")


def test_state_update_is_controlled() -> None:
    state = base_state()

    decision = (
        AgentEvidenceEvaluationService()
        .evaluate(state)
    )

    assert isinstance(
        decision,
        AgentEvidenceEvaluationDecision,
    )
    assert decision.to_state_update() == {
        "evidence_sufficient": False,
        "evidence_reason": (
            decision.evidence_reason
        ),
    }
    assert set(decision.as_dict()) == {
        "evaluation_version",
        "next_node",
        "evidence_sufficient",
        "evidence_reason",
        "completed_tool_count",
        "knowledge_evidence_count",
        "history_evidence_count",
        "unused_tool_names",
    }
    print("PASS: Evaluation state update is controlled")


def test_input_state_is_not_mutated() -> None:
    state = base_state()
    original = {
        key: value
        for key, value in state.items()
    }

    AgentEvidenceEvaluationService().evaluate(
        state
    )

    assert state == original
    assert "evidence_sufficient" not in state
    print("PASS: input Agent state is not mutated")


def test_pending_selected_tool_is_rejected() -> None:
    state = base_state()
    state["selected_tool"] = {
        "tool_name": SEARCH_KNOWLEDGE_TOOL
    }

    error = expect_raises(
        AgentEvidenceEvaluationError,
        lambda: AgentEvidenceEvaluationService()
        .evaluate(state),
    )

    assert error.error_code == (
        "tool_execution_incomplete"
    )
    print("PASS: pending selected_tool is rejected")


def test_invalid_tool_budget_is_rejected() -> None:
    for value in (None, 0, -1, True, "3"):
        state = base_state()
        state["max_tool_calls"] = value

        error = expect_raises(
            AgentEvidenceEvaluationError,
            lambda state=state: (
                AgentEvidenceEvaluationService()
                .evaluate(state)
            ),
        )
        assert error.error_code == (
            "invalid_max_tool_calls"
        )

    print("PASS: invalid Tool budget is rejected")


def test_duplicate_tool_results_are_rejected() -> None:
    state = base_state()
    duplicate = tool_result(
        SEARCH_KNOWLEDGE_TOOL,
        "b",
        {"retrieval_status": "no_results"},
    )
    state["tool_results"].append(duplicate)

    error = expect_raises(
        AgentEvidenceEvaluationError,
        lambda: AgentEvidenceEvaluationService()
        .evaluate(state),
    )

    assert error.error_code == (
        "duplicate_completed_tool"
    )
    print("PASS: duplicate completed Tool is rejected")


def test_orphan_evidence_is_rejected() -> None:
    state = base_state()
    state["retrieved_evidence"] = [
        evidence(
            tool_name=SEARCH_KNOWLEDGE_TOOL,
            marker="z",
            evidence_type="knowledge_chunk",
            payload={
                "chunk_text": "Orphan evidence."
            },
        )
    ]

    error = expect_raises(
        AgentEvidenceEvaluationError,
        lambda: AgentEvidenceEvaluationService()
        .evaluate(state),
    )

    assert error.error_code == (
        "orphan_retrieved_evidence"
    )
    print("PASS: orphan evidence is rejected")


def test_evidence_type_mismatch_is_rejected() -> None:
    state = base_state()
    state["tool_results"] = [
        tool_result(
            CALCULATE_DELIVERY_RISK_TOOL,
            "c",
            {"risk_level": "high"},
        )
    ]
    state["retrieved_evidence"] = [
        evidence(
            tool_name=CALCULATE_DELIVERY_RISK_TOOL,
            marker="c",
            evidence_type="knowledge_chunk",
            payload={
                "chunk_text": "Invalid evidence."
            },
        )
    ]

    error = expect_raises(
        AgentEvidenceEvaluationError,
        lambda: AgentEvidenceEvaluationService()
        .evaluate(state),
    )

    assert error.error_code == (
        "evidence_type_mismatch"
    )
    print("PASS: evidence type mismatch is rejected")


def test_invalid_clarification_is_rejected() -> None:
    state = base_state()
    state["tool_results"] = all_tool_results()
    state["clarification_response"] = "  invalid  "

    error = expect_raises(
        AgentEvidenceEvaluationError,
        lambda: AgentEvidenceEvaluationService()
        .evaluate(state),
    )

    assert error.error_code == (
        "invalid_clarification_response"
    )
    print("PASS: invalid clarification is rejected")


def test_source_is_pure_and_signal_dependent() -> None:
    source = inspect.getsource(
        AgentEvidenceEvaluationService
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
        "complete_step_and_advance_run(",
    )
    found = [
        token for token in forbidden
        if token in source
    ]
    assert not found, found
    assert "_knowledge_is_usable(" in source
    assert "_history_is_usable(" in source
    assert "clarification_response" in source
    assert "unused_names" in source

    observed = set()

    knowledge_state = base_state()
    knowledge_state["tool_results"][0] = tool_result(
        SEARCH_KNOWLEDGE_TOOL,
        "a",
        {"retrieval_status": "succeeded"},
    )
    knowledge_state["retrieved_evidence"] = [
        evidence(
            tool_name=SEARCH_KNOWLEDGE_TOOL,
            marker="a",
            evidence_type="knowledge_chunk",
            payload={
                "chunk_text": "Grounded runbook.",
                "similarity_score": 0.9,
            },
        )
    ]
    observed.add(
        AgentEvidenceEvaluationService()
        .evaluate(knowledge_state)
        .next_node
    )

    observed.add(
        AgentEvidenceEvaluationService()
        .evaluate(base_state())
        .next_node
    )

    exhausted = base_state()
    exhausted["tool_results"] = all_tool_results()
    observed.add(
        AgentEvidenceEvaluationService()
        .evaluate(exhausted)
        .next_node
    )

    exhausted["clarification_response"] = "Unknown"
    observed.add(
        AgentEvidenceEvaluationService()
        .evaluate(exhausted)
        .next_node
    )

    assert observed == {
        GENERATE_ANALYSIS_NODE,
        SELECT_TOOL_NODE,
        REQUEST_CLARIFICATION_NODE,
        LIMIT_EXCEEDED_NODE,
    }
    print("PASS: Evaluation is pure and signal-dependent")


def main() -> None:
    tests = (
        test_version_and_nodes_are_frozen,
        test_usable_knowledge_generates_analysis,
        test_accepted_history_generates_analysis,
        test_rejected_history_selects_another_tool,
        test_risk_only_selects_another_tool,
        test_exhausted_tools_request_clarification,
        test_usable_clarification_generates_analysis,
        test_weak_clarification_hits_limit,
        test_state_update_is_controlled,
        test_input_state_is_not_mutated,
        test_pending_selected_tool_is_rejected,
        test_invalid_tool_budget_is_rejected,
        test_duplicate_tool_results_are_rejected,
        test_orphan_evidence_is_rejected,
        test_evidence_type_mismatch_is_rejected,
        test_invalid_clarification_is_rejected,
        test_source_is_pure_and_signal_dependent,
    )

    for test in tests:
        test()

    print(
        "Agent Evidence Evaluation assertions "
        "passed (17/17)"
    )


if __name__ == "__main__":
    main()
