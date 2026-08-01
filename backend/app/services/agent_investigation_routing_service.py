from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


AGENT_INVESTIGATION_ROUTING_VERSION = "agent_investigation_routing_v0.1"
DEFAULT_MAX_STEPS = 16
DEFAULT_MAX_TOOL_CALLS = 3

NEXT_NODE_SELECT_TOOL = "select_tool"
NEXT_NODE_EVALUATE_EVIDENCE = "evaluate_evidence"
NEXT_NODE_LIMIT_EXCEEDED = "limit_exceeded"
NEXT_NODE_FAILED = "failed"

ALLOWED_NEXT_NODES = frozenset(
    {
        NEXT_NODE_SELECT_TOOL,
        NEXT_NODE_EVALUATE_EVIDENCE,
        NEXT_NODE_LIMIT_EXCEEDED,
        NEXT_NODE_FAILED,
    }
)


@dataclass(frozen=True)
class AgentInvestigationRoutingOutcome:
    next_node: str
    reason: str
    max_steps: int
    max_tool_calls: int
    error_code: str | None = None
    routing_version: str = AGENT_INVESTIGATION_ROUTING_VERSION

    def __post_init__(self) -> None:
        if self.next_node not in ALLOWED_NEXT_NODES:
            raise ValueError(
                f"Unsupported investigation next_node: {self.next_node}"
            )
        if not self.reason.strip():
            raise ValueError("Investigation routing reason must be nonblank")
        if self.max_steps <= 0:
            raise ValueError("max_steps must be positive")
        if self.max_tool_calls <= 0:
            raise ValueError("max_tool_calls must be positive")

    def to_state_update(self) -> dict[str, object]:
        return {
            "max_steps": self.max_steps,
            "max_tool_calls": self.max_tool_calls,
        }


class AgentInvestigationRoutingService:
    def route(
        self,
        state: Mapping[str, Any],
        *,
        step_count: int,
        tool_call_count: int,
    ) -> AgentInvestigationRoutingOutcome:
        if not isinstance(state, Mapping):
            return self._failed(
                reason="Agent state must be a mapping.",
                error_code="invalid_agent_state",
            )

        max_steps = self._resolve_positive_limit(
            state.get("max_steps"),
            default=DEFAULT_MAX_STEPS,
        )
        if max_steps is None:
            return self._failed(
                reason="max_steps must be a positive integer.",
                error_code="invalid_max_steps",
            )

        max_tool_calls = self._resolve_positive_limit(
            state.get("max_tool_calls"),
            default=DEFAULT_MAX_TOOL_CALLS,
        )
        if max_tool_calls is None:
            return self._failed(
                reason="max_tool_calls must be a positive integer.",
                error_code="invalid_max_tool_calls",
                max_steps=max_steps,
            )

        if not self._is_nonnegative_integer(step_count):
            return self._failed(
                reason="step_count must be a nonnegative integer.",
                error_code="invalid_step_count",
                max_steps=max_steps,
                max_tool_calls=max_tool_calls,
            )

        if not self._is_nonnegative_integer(tool_call_count):
            return self._failed(
                reason="tool_call_count must be a nonnegative integer.",
                error_code="invalid_tool_call_count",
                max_steps=max_steps,
                max_tool_calls=max_tool_calls,
            )

        if step_count >= max_steps:
            return self._outcome(
                next_node=NEXT_NODE_LIMIT_EXCEEDED,
                reason="The configured max_steps boundary has been reached.",
                error_code="max_steps_reached",
                max_steps=max_steps,
                max_tool_calls=max_tool_calls,
            )

        triage_result = state.get("triage_result")
        if not isinstance(triage_result, Mapping) or not triage_result:
            return self._failed(
                reason="A nonempty confirmed triage_result is required.",
                error_code="missing_triage_result",
                max_steps=max_steps,
                max_tool_calls=max_tool_calls,
            )

        triage_confirmed = state.get("triage_confirmed")
        if triage_confirmed is not None and triage_confirmed is not True:
            return self._failed(
                reason="triage_confirmed must be true when present.",
                error_code="triage_not_confirmed",
                max_steps=max_steps,
                max_tool_calls=max_tool_calls,
            )

        tool_results = state.get("tool_results")
        if not self._is_optional_collection(tool_results):
            return self._failed(
                reason="tool_results must be a controlled collection when present.",
                error_code="invalid_tool_results",
                max_steps=max_steps,
                max_tool_calls=max_tool_calls,
            )

        retrieved_evidence = state.get("retrieved_evidence")
        if not self._is_optional_collection(retrieved_evidence):
            return self._failed(
                reason=(
                    "retrieved_evidence must be a controlled collection "
                    "when present."
                ),
                error_code="invalid_retrieved_evidence",
                max_steps=max_steps,
                max_tool_calls=max_tool_calls,
            )

        clarification_response = state.get("clarification_response")
        if (
            clarification_response is not None
            and not isinstance(clarification_response, str)
        ):
            return self._failed(
                reason="clarification_response must be a string when present.",
                error_code="invalid_clarification_response",
                max_steps=max_steps,
                max_tool_calls=max_tool_calls,
            )

        has_tool_results = self._has_items(tool_results)
        has_retrieved_evidence = self._has_items(retrieved_evidence)
        has_clarification_response = (
            isinstance(clarification_response, str)
            and bool(clarification_response.strip())
        )

        selected_tool = state.get("selected_tool")
        if (
            selected_tool is not None
            and not has_tool_results
            and not has_retrieved_evidence
        ):
            return self._failed(
                reason=(
                    "route_investigation cannot continue while a selected "
                    "tool has no result."
                ),
                error_code="pending_selected_tool",
                max_steps=max_steps,
                max_tool_calls=max_tool_calls,
            )

        if (
            has_tool_results
            or has_retrieved_evidence
            or has_clarification_response
        ):
            return self._outcome(
                next_node=NEXT_NODE_EVALUATE_EVIDENCE,
                reason=(
                    "Controlled evidence or a human clarification response "
                    "is ready for evaluation."
                ),
                max_steps=max_steps,
                max_tool_calls=max_tool_calls,
            )

        if tool_call_count >= max_tool_calls:
            return self._outcome(
                next_node=NEXT_NODE_LIMIT_EXCEEDED,
                reason=(
                    "No evidence is ready and the configured max_tool_calls "
                    "boundary has been reached."
                ),
                error_code="max_tool_calls_reached",
                max_steps=max_steps,
                max_tool_calls=max_tool_calls,
            )

        return self._outcome(
            next_node=NEXT_NODE_SELECT_TOOL,
            reason=(
                "Confirmed triage exists, no evidence is ready, and another "
                "approved tool call is within limits."
            ),
            max_steps=max_steps,
            max_tool_calls=max_tool_calls,
        )

    def _outcome(
        self,
        *,
        next_node: str,
        reason: str,
        max_steps: int,
        max_tool_calls: int,
        error_code: str | None = None,
    ) -> AgentInvestigationRoutingOutcome:
        return AgentInvestigationRoutingOutcome(
            next_node=next_node,
            reason=reason,
            max_steps=max_steps,
            max_tool_calls=max_tool_calls,
            error_code=error_code,
        )

    def _failed(
        self,
        *,
        reason: str,
        error_code: str,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    ) -> AgentInvestigationRoutingOutcome:
        return self._outcome(
            next_node=NEXT_NODE_FAILED,
            reason=reason,
            max_steps=max_steps,
            max_tool_calls=max_tool_calls,
            error_code=error_code,
        )

    @staticmethod
    def _resolve_positive_limit(
        value: object,
        *,
        default: int,
    ) -> int | None:
        if value is None:
            return default
        if isinstance(value, bool):
            return None
        if not isinstance(value, int):
            return None
        if value <= 0:
            return None
        return value

    @staticmethod
    def _is_nonnegative_integer(value: object) -> bool:
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
        )

    @staticmethod
    def _is_optional_collection(value: object) -> bool:
        if value is None:
            return True
        if isinstance(value, Mapping):
            return True
        return (
            isinstance(value, Sequence)
            and not isinstance(value, (str, bytes, bytearray))
        )

    @staticmethod
    def _has_items(value: object) -> bool:
        if value is None:
            return False
        if isinstance(value, Mapping):
            return bool(value)
        if (
            isinstance(value, Sequence)
            and not isinstance(value, (str, bytes, bytearray))
        ):
            return bool(value)
        return False


agent_investigation_routing_service = AgentInvestigationRoutingService()
