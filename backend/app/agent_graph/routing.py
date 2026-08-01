from __future__ import annotations

from typing import Literal

from app.agent_graph.state import (
    AgentGraphState,
    validate_agent_graph_state,
)


TriageRoute = Literal[
    "wait",
    "continue",
]
EvidenceRoute = Literal[
    "more_tools",
    "clarification",
    "analysis",
]
ClarificationRoute = Literal[
    "wait",
    "continue",
]
FinalReviewRoute = Literal[
    "wait",
    "continue",
]


def route_after_triage_confirmation(
    state: AgentGraphState,
) -> TriageRoute:
    validated = validate_agent_graph_state(state)

    if validated.get("triage_confirmed") is True:
        return "continue"

    return "wait"


def route_after_evidence_evaluation(
    state: AgentGraphState,
) -> EvidenceRoute:
    validated = validate_agent_graph_state(state)

    if validated.get("evidence_sufficient") is True:
        return "analysis"

    clarification_question = validated.get(
        "clarification_question"
    )
    clarification_response = validated.get(
        "clarification_response"
    )

    if (
        clarification_question is not None
        and clarification_response is None
    ):
        return "clarification"

    selected_tool = validated.get("selected_tool")
    tool_results = validated.get(
        "tool_results",
        [],
    )
    max_tool_calls = validated.get(
        "max_tool_calls",
        1,
    )

    if (
        selected_tool is not None
        and len(tool_results) < max_tool_calls
    ):
        return "more_tools"

    return "analysis"


def route_after_clarification(
    state: AgentGraphState,
) -> ClarificationRoute:
    validated = validate_agent_graph_state(state)

    if (
        validated.get("clarification_response")
        is not None
    ):
        return "continue"

    return "wait"


def route_after_final_review(
    state: AgentGraphState,
) -> FinalReviewRoute:
    validated = validate_agent_graph_state(state)

    if validated.get("pending_approval") is False:
        return "continue"

    return "wait"
