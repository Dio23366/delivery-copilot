from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from typing import Any


AGENT_CLARIFICATION_REQUEST_VERSION = (
    "agent_clarification_request_v0.1"
)

REQUEST_CLARIFICATION_NODE = (
    "request_clarification"
)
WAITING_FOR_CLARIFICATION_STATUS = (
    "waiting_for_clarification"
)
CLARIFICATION_RESUME_NODE = (
    "route_investigation"
)
CLARIFICATION_INTERRUPT_REASON = (
    "additional_information_required"
)


class AgentClarificationRequestError(ValueError):
    def __init__(
        self,
        *,
        error_code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class AgentClarificationRequest:
    clarification_question: str
    evidence_reason: str
    waiting_status: str = (
        WAITING_FOR_CLARIFICATION_STATUS
    )
    resume_node: str = CLARIFICATION_RESUME_NODE
    interrupt_reason: str = (
        CLARIFICATION_INTERRUPT_REASON
    )
    request_version: str = (
        AGENT_CLARIFICATION_REQUEST_VERSION
    )

    def as_dict(self) -> dict[str, object]:
        return {
            "request_version": self.request_version,
            "node_name": REQUEST_CLARIFICATION_NODE,
            "clarification_question": (
                self.clarification_question
            ),
            "evidence_reason": self.evidence_reason,
            "waiting_status": self.waiting_status,
            "resume_node": self.resume_node,
            "interrupt_reason": (
                self.interrupt_reason
            ),
        }

    def to_state_update(self) -> dict[str, object]:
        return {
            "clarification_question": (
                self.clarification_question
            ),
            "clarification_response": None,
        }


class AgentClarificationRequestService:
    def create_request(
        self,
        state: Mapping[str, Any],
    ) -> AgentClarificationRequest:
        if not isinstance(state, Mapping):
            raise AgentClarificationRequestError(
                error_code="invalid_agent_state",
                message="Agent state must be a mapping.",
            )

        if state.get("triage_confirmed") is not True:
            raise AgentClarificationRequestError(
                error_code="triage_not_confirmed",
                message=(
                    "Clarification requires confirmed "
                    "triage."
                ),
            )

        if (
            "selected_tool" not in state
            or state.get("selected_tool") is not None
        ):
            raise AgentClarificationRequestError(
                error_code="tool_execution_incomplete",
                message=(
                    "Clarification requires "
                    "selected_tool to be cleared."
                ),
            )

        if state.get("evidence_sufficient") is not False:
            raise AgentClarificationRequestError(
                error_code=(
                    "clarification_not_required"
                ),
                message=(
                    "Clarification may only be requested "
                    "when evidence is insufficient."
                ),
            )

        evidence_reason = self._normalized_text(
            state.get("evidence_reason"),
            field_name="evidence_reason",
            error_code=(
                "invalid_evidence_reason"
            ),
        )

        tool_results = state.get("tool_results")
        if (
            isinstance(tool_results, (str, bytes))
            or not isinstance(
                tool_results,
                Sequence,
            )
            or not tool_results
        ):
            raise AgentClarificationRequestError(
                error_code="missing_tool_results",
                message=(
                    "Clarification requires at least "
                    "one completed Tool result."
                ),
            )

        for item in tool_results:
            if not isinstance(item, Mapping):
                raise AgentClarificationRequestError(
                    error_code=(
                        "invalid_tool_results"
                    ),
                    message=(
                        "Each Tool result must be a "
                        "mapping."
                    ),
                )
            if item.get(
                "execution_status"
            ) != "completed":
                raise AgentClarificationRequestError(
                    error_code=(
                        "invalid_tool_results"
                    ),
                    message=(
                        "Clarification may only use "
                        "completed Tool results."
                    ),
                )

        existing_question = state.get(
            "clarification_question"
        )
        if existing_question is not None:
            raise AgentClarificationRequestError(
                error_code=(
                    "clarification_already_requested"
                ),
                message=(
                    "A clarification question already "
                    "exists."
                ),
            )

        existing_response = state.get(
            "clarification_response"
        )
        if existing_response is not None:
            raise AgentClarificationRequestError(
                error_code=(
                    "clarification_already_supplied"
                ),
                message=(
                    "A clarification response already "
                    "exists."
                ),
            )

        context = self._normalized_context(state)
        question = self._build_question(
            context=context,
            evidence_reason=evidence_reason,
        )

        request = AgentClarificationRequest(
            clarification_question=question,
            evidence_reason=evidence_reason,
        )
        self._assert_json_safe(
            request.as_dict()
        )
        self._assert_json_safe(
            request.to_state_update()
        )
        return request

    @classmethod
    def _normalized_context(
        cls,
        state: Mapping[str, Any],
    ) -> dict[str, str]:
        context = {
            "issue_title": cls._optional_text(
                state.get("issue_title")
            ),
            "issue_description": cls._optional_text(
                state.get("issue_description")
            ),
            "issue_type": cls._optional_text(
                state.get("issue_type")
            ),
            "severity": cls._optional_text(
                state.get("severity")
            ),
            "status": cls._optional_text(
                state.get("status")
            ),
            "project_name": cls._optional_text(
                state.get("project_name")
            ),
            "delivery_stage": cls._optional_text(
                state.get("delivery_stage")
            ),
        }

        if not any(context.values()):
            raise AgentClarificationRequestError(
                error_code=(
                    "missing_issue_context"
                ),
                message=(
                    "Clarification requires persisted "
                    "Issue context."
                ),
            )

        return context

    @classmethod
    def _build_question(
        cls,
        *,
        context: Mapping[str, str],
        evidence_reason: str,
    ) -> str:
        searchable = " ".join(
            [
                context["issue_title"],
                context["issue_description"],
                context["issue_type"],
                context["status"],
                evidence_reason,
            ]
        ).lower()

        issue_reference = cls._issue_reference(
            context
        )

        if any(
            token in searchable
            for token in (
                "auth",
                "token",
                "credential",
                "permission",
                "401",
                "403",
                "api",
            )
        ):
            return (
                f"For {issue_reference}, please provide "
                "the authentication method, the time of "
                "the most recent credential or token "
                "change, and the original error code or "
                "response body from a failed request."
            )

        if any(
            token in searchable
            for token in (
                "deploy",
                "release",
                "configuration",
                "config",
                "environment",
                "version",
            )
        ):
            return (
                f"For {issue_reference}, please confirm "
                "the affected environment and version, "
                "the most recent deployment or "
                "configuration change, and the first "
                "relevant error log with its timestamp."
            )

        if any(
            token in searchable
            for token in (
                "data",
                "sync",
                "mapping",
                "integration",
                "record",
                "schema",
            )
        ):
            return (
                f"For {issue_reference}, please provide "
                "one affected record or request "
                "identifier, the source and target "
                "systems, the failure timestamp, and the "
                "expected versus actual result."
            )

        if any(
            token in searchable
            for token in (
                "waiting_on_customer",
                "customer",
                "client",
            )
        ):
            return (
                f"For {issue_reference}, please confirm "
                "the customer's latest action, when it "
                "occurred, the exact error observed, and "
                "whether the issue can still be "
                "reproduced."
            )

        return (
            f"For {issue_reference}, please provide the "
            "failure timestamp, the most recent related "
            "change, concise reproduction steps, and "
            "the original error message or log entry."
        )

    @staticmethod
    def _issue_reference(
        context: Mapping[str, str],
    ) -> str:
        title = context["issue_title"]
        project = context["project_name"]

        if title and project:
            return (
                f'issue "{title}" in project '
                f'"{project}"'
            )
        if title:
            return f'issue "{title}"'
        if project:
            return f'issue in project "{project}"'
        return "the current issue"

    @staticmethod
    def _optional_text(
        value: object,
    ) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise AgentClarificationRequestError(
                error_code=(
                    "invalid_issue_context"
                ),
                message=(
                    "Issue context text fields must be "
                    "strings when present."
                ),
            )
        return value.strip()

    @staticmethod
    def _normalized_text(
        value: object,
        *,
        field_name: str,
        error_code: str,
    ) -> str:
        if (
            not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
        ):
            raise AgentClarificationRequestError(
                error_code=error_code,
                message=(
                    f"{field_name} must be a normalized "
                    "nonblank string."
                ),
            )
        return value

    @staticmethod
    def _assert_json_safe(
        value: object,
    ) -> None:
        try:
            serialized = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
            )
            json.loads(serialized)
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise AgentClarificationRequestError(
                error_code=(
                    "clarification_not_json_safe"
                ),
                message=(
                    "Clarification request must be JSON "
                    "serializable."
                ),
            ) from exc


agent_clarification_request_service = (
    AgentClarificationRequestService()
)
