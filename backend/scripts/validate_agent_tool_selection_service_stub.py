from __future__ import annotations

from pathlib import Path
import inspect
import sys
from typing import Callable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.agent_tool_registry import (
    CALCULATE_DELIVERY_RISK_TOOL,
    GET_ANALYSIS_HISTORY_TOOL,
    SEARCH_KNOWLEDGE_TOOL,
)
from app.services.agent_tool_selection_service import (
    AGENT_TOOL_SELECTION_VERSION,
    AgentToolSelectionDecision,
    AgentToolSelectionError,
    AgentToolSelectionService,
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


def base_state() -> dict[str, object]:
    return {
        "issue_id": 17,
        "triage_confirmed": True,
        "triage_result": {
            "issue_type": "API",
            "subtype": "authentication",
            "severity": "medium",
            "confidence": 0.95,
            "reason": (
                "Authentication evidence is present."
            ),
        },
        "issue_context": {
            "risk_level": "low",
            "health": "healthy",
            "status": "investigating",
            "delivery_stage": "Implementation",
        },
        "tool_results": [],
    }


def test_version_is_frozen() -> None:
    assert AGENT_TOOL_SELECTION_VERSION == (
        "agent_tool_selection_v0.1"
    )
    print("PASS: selection version is frozen")


def test_normal_triage_selects_knowledge() -> None:
    decision = AgentToolSelectionService().select(
        base_state()
    )

    assert decision.tool_name == SEARCH_KNOWLEDGE_TOOL
    assert decision.tool_version == (
        "grounded_retrieval_v1"
    )
    print("PASS: normal technical triage selects knowledge")


def test_critical_deployment_selects_risk() -> None:
    state = base_state()
    state["triage_result"] = {
        "issue_type": "Deployment",
        "subtype": "rollback",
        "severity": "critical",
        "confidence": 0.95,
        "reason": "A critical deployment rollback is active.",
    }

    decision = AgentToolSelectionService().select(
        state
    )

    assert decision.tool_name == (
        CALCULATE_DELIVERY_RISK_TOOL
    )
    print("PASS: critical deployment selects risk")


def test_high_project_risk_selects_risk() -> None:
    state = base_state()
    state["issue_context"] = {
        "risk_level": "high",
        "health": "at_risk",
    }

    decision = AgentToolSelectionService().select(
        state
    )

    assert decision.tool_name == (
        CALCULATE_DELIVERY_RISK_TOOL
    )
    print("PASS: high project risk selects risk")


def test_low_confidence_selects_history() -> None:
    state = base_state()
    state["triage_result"] = {
        "issue_type": "Data",
        "subtype": "mapping",
        "severity": "medium",
        "confidence": 0.60,
        "reason": "The available classification is generic.",
    }

    decision = AgentToolSelectionService().select(
        state
    )

    assert decision.tool_name == (
        GET_ANALYSIS_HISTORY_TOOL
    )
    print("PASS: low-confidence triage selects history")


def test_clarification_can_prioritize_history() -> None:
    state = base_state()
    state["triage_result"] = {
        "issue_type": "API",
        "subtype": "authentication",
        "severity": "medium",
        "confidence": 0.80,
        "reason": "Human detail refined the triage.",
    }
    state["clarification_response"] = (
        "The token rotated before the failure."
    )

    decision = AgentToolSelectionService().select(
        state
    )

    assert decision.tool_name == (
        GET_ANALYSIS_HISTORY_TOOL
    )
    print("PASS: clarification can prioritize history")


def test_prior_knowledge_result_is_excluded() -> None:
    state = base_state()
    state["tool_results"] = [
        {"tool_name": SEARCH_KNOWLEDGE_TOOL}
    ]

    decision = AgentToolSelectionService().select(
        state
    )

    assert decision.tool_name == (
        GET_ANALYSIS_HISTORY_TOOL
    )
    assert "excluded" in decision.reason
    print("PASS: prior knowledge result is excluded")


def test_prior_risk_result_is_excluded() -> None:
    state = base_state()
    state["triage_result"] = {
        "issue_type": "Deployment",
        "subtype": "rollback",
        "severity": "critical",
        "confidence": 0.95,
        "reason": "A critical deployment rollback is active.",
    }
    state["tool_results"] = [
        {
            "tool_name": (
                CALCULATE_DELIVERY_RISK_TOOL
            )
        }
    ]

    decision = AgentToolSelectionService().select(
        state
    )

    assert decision.tool_name == SEARCH_KNOWLEDGE_TOOL
    print("PASS: prior risk result is excluded")


def test_contract_normalizes_arguments() -> None:
    state = base_state()
    state["issue_id"] = 17

    decision = AgentToolSelectionService().select(
        state
    )

    assert dict(decision.arguments) == {
        "issue_id": 17
    }
    assert decision.call_identity.startswith(
        f"{decision.tool_name}:"
    )
    assert len(
        decision.call_identity.split(":", 1)[1]
    ) == 64
    print("PASS: selected arguments use Contract Service")


def test_state_update_is_controlled() -> None:
    decision = AgentToolSelectionService().select(
        base_state()
    )

    update = decision.to_state_update()
    selected = update["selected_tool"]

    assert isinstance(
        decision,
        AgentToolSelectionDecision,
    )
    assert set(selected) == {
        "selection_version",
        "tool_name",
        "tool_version",
        "arguments",
        "call_identity",
        "confidence",
        "reason",
    }
    assert 0.55 <= selected["confidence"] <= 0.99
    print("PASS: selected_tool state update is controlled")


def test_invalid_issue_id_is_rejected() -> None:
    for value in (None, 0, -1, True, "17"):
        state = base_state()
        state["issue_id"] = value

        error = expect_raises(
            AgentToolSelectionError,
            lambda state=state: (
                AgentToolSelectionService()
                .select(state)
            ),
        )
        assert error.error_code == "invalid_issue_id"

    print("PASS: invalid issue_id is rejected")


def test_unconfirmed_triage_is_rejected() -> None:
    state = base_state()
    state["triage_confirmed"] = False

    error = expect_raises(
        AgentToolSelectionError,
        lambda: AgentToolSelectionService()
        .select(state),
    )

    assert error.error_code == "triage_not_confirmed"
    print("PASS: unconfirmed triage is rejected")


def test_invalid_triage_fields_are_rejected() -> None:
    cases = (
        ("issue_type", "Unknown"),
        ("subtype", ""),
        ("severity", "urgent"),
        ("confidence", 2.0),
        ("reason", " "),
    )

    for field, value in cases:
        state = base_state()
        triage = dict(state["triage_result"])
        triage[field] = value
        state["triage_result"] = triage

        error = expect_raises(
            AgentToolSelectionError,
            lambda state=state: (
                AgentToolSelectionService()
                .select(state)
            ),
        )
        assert error.error_code.startswith(
            "invalid_triage_"
        )

    print("PASS: invalid triage fields are rejected")


def test_malformed_tool_results_are_rejected() -> None:
    invalid_values = (
        "search_knowledge",
        [17],
        [{"tool_name": "unapproved"}],
        [
            {"tool_name": SEARCH_KNOWLEDGE_TOOL},
            {"tool_name": SEARCH_KNOWLEDGE_TOOL},
        ],
    )

    for value in invalid_values:
        state = base_state()
        state["tool_results"] = value

        expect_raises(
            AgentToolSelectionError,
            lambda state=state: (
                AgentToolSelectionService()
                .select(state)
            ),
        )

    print("PASS: malformed Tool results are rejected")


def test_all_tools_exhausted_is_rejected() -> None:
    state = base_state()
    state["tool_results"] = [
        {"tool_name": SEARCH_KNOWLEDGE_TOOL},
        {"tool_name": GET_ANALYSIS_HISTORY_TOOL},
        {
            "tool_name": (
                CALCULATE_DELIVERY_RISK_TOOL
            )
        },
    ]

    error = expect_raises(
        AgentToolSelectionError,
        lambda: AgentToolSelectionService()
        .select(state),
    )

    assert error.error_code == (
        "no_useful_tool_available"
    )
    print("PASS: exhausted Tool set is rejected")


def test_source_is_pure_and_not_fixed_sequence() -> None:
    source = inspect.getsource(
        AgentToolSelectionService
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
        "AgentGuardedToolExecutionService",
        "execute_once(",
        "state_json",
        "ToolCall",
        "retry",
    )
    found = [
        token for token in forbidden
        if token in source
    ]
    assert not found, found
    assert "_score_candidates(" in source
    assert "triage_confidence" in source
    assert "risk_level" in source
    assert "prior_tool_names" in source

    observed = {
        AgentToolSelectionService()
        .select(base_state())
        .tool_name,
    }

    critical = base_state()
    critical["triage_result"] = {
        "issue_type": "Deployment",
        "subtype": "rollback",
        "severity": "critical",
        "confidence": 0.95,
        "reason": "Critical deployment rollback.",
    }
    observed.add(
        AgentToolSelectionService()
        .select(critical)
        .tool_name
    )

    uncertain = base_state()
    uncertain["triage_result"] = {
        "issue_type": "Data",
        "subtype": "mapping",
        "severity": "medium",
        "confidence": 0.60,
        "reason": "Generic mapping classification.",
    }
    observed.add(
        AgentToolSelectionService()
        .select(uncertain)
        .tool_name
    )

    assert observed == {
        SEARCH_KNOWLEDGE_TOOL,
        GET_ANALYSIS_HISTORY_TOOL,
        CALCULATE_DELIVERY_RISK_TOOL,
    }
    print("PASS: selection is pure and signal-dependent")


def main() -> None:
    tests = (
        test_version_is_frozen,
        test_normal_triage_selects_knowledge,
        test_critical_deployment_selects_risk,
        test_high_project_risk_selects_risk,
        test_low_confidence_selects_history,
        test_clarification_can_prioritize_history,
        test_prior_knowledge_result_is_excluded,
        test_prior_risk_result_is_excluded,
        test_contract_normalizes_arguments,
        test_state_update_is_controlled,
        test_invalid_issue_id_is_rejected,
        test_unconfirmed_triage_is_rejected,
        test_invalid_triage_fields_are_rejected,
        test_malformed_tool_results_are_rejected,
        test_all_tools_exhausted_is_rejected,
        test_source_is_pure_and_not_fixed_sequence,
    )

    for test in tests:
        test()

    print(
        "Agent Tool Selection assertions "
        "passed (16/16)"
    )


if __name__ == "__main__":
    main()
