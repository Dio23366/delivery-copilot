from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from app.services.agent_tool_contract_service import (
    AgentToolContractService,
    agent_tool_contract_service,
)
from app.services.agent_tool_registry import (
    CALCULATE_DELIVERY_RISK_TOOL,
    GET_ANALYSIS_HISTORY_TOOL,
    SEARCH_KNOWLEDGE_TOOL,
    ApprovedAgentToolRegistry,
    approved_agent_tool_registry,
)


AGENT_TOOL_SELECTION_VERSION = (
    "agent_tool_selection_v0.1"
)

ALLOWED_TRIAGE_ISSUE_TYPES = frozenset(
    {
        "API",
        "Data",
        "Deployment",
        "Configuration",
        "Integration",
    }
)
ALLOWED_TRIAGE_SEVERITIES = frozenset(
    {"low", "medium", "high", "critical"}
)

BASE_TOOL_SCORES = MappingProxyType(
    {
        SEARCH_KNOWLEDGE_TOOL: 70,
        GET_ANALYSIS_HISTORY_TOOL: 60,
        CALCULATE_DELIVERY_RISK_TOOL: 45,
    }
)


class AgentToolSelectionError(ValueError):
    def __init__(
        self,
        *,
        error_code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class AgentToolSelectionDecision:
    tool_name: str
    tool_version: str
    arguments: Mapping[str, object]
    call_identity: str
    confidence: float
    reason: str
    selection_version: str = AGENT_TOOL_SELECTION_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "selection_version": self.selection_version,
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "arguments": dict(self.arguments),
            "call_identity": self.call_identity,
            "confidence": self.confidence,
            "reason": self.reason,
        }

    def to_state_update(self) -> dict[str, object]:
        return {
            "selected_tool": self.as_dict(),
        }


class AgentToolSelectionService:
    def __init__(
        self,
        *,
        registry: ApprovedAgentToolRegistry = (
            approved_agent_tool_registry
        ),
        contract_service: AgentToolContractService = (
            agent_tool_contract_service
        ),
    ) -> None:
        if not isinstance(
            registry,
            ApprovedAgentToolRegistry,
        ):
            raise TypeError(
                "registry must be an "
                "ApprovedAgentToolRegistry"
            )
        if not isinstance(
            contract_service,
            AgentToolContractService,
        ):
            raise TypeError(
                "contract_service must be an "
                "AgentToolContractService"
            )
        self._registry = registry
        self._contract_service = contract_service

    def select(
        self,
        state: Mapping[str, Any],
    ) -> AgentToolSelectionDecision:
        if not isinstance(state, Mapping):
            raise AgentToolSelectionError(
                error_code="invalid_agent_state",
                message="Agent state must be a mapping.",
            )

        issue_id = self._require_issue_id(state)
        triage_result = self._require_triage(state)
        issue_context = self._optional_issue_context(
            state
        )
        prior_tool_names = self._prior_tool_names(
            state
        )

        scores = self._score_candidates(
            triage_result=triage_result,
            issue_context=issue_context,
            clarification_response=state.get(
                "clarification_response"
            ),
        )

        available = [
            (score, tool_name)
            for tool_name, score in scores.items()
            if tool_name not in prior_tool_names
        ]
        if not available:
            raise AgentToolSelectionError(
                error_code="no_useful_tool_available",
                message=(
                    "No unused approved Tool remains for "
                    "this Agent Run."
                ),
            )

        available.sort(
            key=lambda item: (-item[0], item[1])
        )
        selected_score, selected_name = available[0]

        definition = self._registry.get(
            selected_name
        )
        validated = (
            self._contract_service
            .validate_arguments(
                definition.tool_name,
                {"issue_id": issue_id},
            )
        )

        reason = self._selection_reason(
            tool_name=selected_name,
            triage_result=triage_result,
            issue_context=issue_context,
            clarification_response=state.get(
                "clarification_response"
            ),
            prior_tool_names=prior_tool_names,
        )
        confidence = round(
            min(
                0.99,
                max(0.55, selected_score / 120),
            ),
            2,
        )

        return AgentToolSelectionDecision(
            tool_name=validated.tool_name,
            tool_version=validated.tool_version,
            arguments=MappingProxyType(
                validated.as_dict()
            ),
            call_identity=validated.call_identity,
            confidence=confidence,
            reason=reason,
        )

    @staticmethod
    def _require_issue_id(
        state: Mapping[str, Any],
    ) -> int:
        issue_id = state.get("issue_id")
        if (
            type(issue_id) is not int
            or issue_id <= 0
        ):
            raise AgentToolSelectionError(
                error_code="invalid_issue_id",
                message=(
                    "Agent state issue_id must be a "
                    "positive integer."
                ),
            )
        return issue_id

    @staticmethod
    def _require_triage(
        state: Mapping[str, Any],
    ) -> dict[str, object]:
        if state.get("triage_confirmed") is not True:
            raise AgentToolSelectionError(
                error_code="triage_not_confirmed",
                message=(
                    "Tool selection requires confirmed "
                    "triage."
                ),
            )

        triage = state.get("triage_result")
        if not isinstance(triage, Mapping):
            raise AgentToolSelectionError(
                error_code="invalid_triage_result",
                message=(
                    "triage_result must be a mapping."
                ),
            )

        issue_type = triage.get("issue_type")
        subtype = triage.get("subtype")
        severity = triage.get("severity")
        confidence = triage.get("confidence")
        reason = triage.get("reason")

        if issue_type not in ALLOWED_TRIAGE_ISSUE_TYPES:
            raise AgentToolSelectionError(
                error_code="invalid_triage_issue_type",
                message=(
                    "triage_result issue_type is not "
                    "controlled."
                ),
            )
        if (
            not isinstance(subtype, str)
            or not subtype.strip()
            or subtype != subtype.strip()
        ):
            raise AgentToolSelectionError(
                error_code="invalid_triage_subtype",
                message=(
                    "triage_result subtype must be a "
                    "normalized nonblank string."
                ),
            )
        if severity not in ALLOWED_TRIAGE_SEVERITIES:
            raise AgentToolSelectionError(
                error_code="invalid_triage_severity",
                message=(
                    "triage_result severity is not "
                    "controlled."
                ),
            )
        if (
            isinstance(confidence, bool)
            or not isinstance(
                confidence,
                (int, float),
            )
            or confidence < 0
            or confidence > 1
        ):
            raise AgentToolSelectionError(
                error_code="invalid_triage_confidence",
                message=(
                    "triage_result confidence must be "
                    "between 0 and 1."
                ),
            )
        if (
            not isinstance(reason, str)
            or not reason.strip()
            or reason != reason.strip()
        ):
            raise AgentToolSelectionError(
                error_code="invalid_triage_reason",
                message=(
                    "triage_result reason must be a "
                    "normalized nonblank string."
                ),
            )

        return {
            "issue_type": issue_type,
            "subtype": subtype,
            "severity": severity,
            "confidence": float(confidence),
            "reason": reason,
        }

    @staticmethod
    def _optional_issue_context(
        state: Mapping[str, Any],
    ) -> dict[str, object]:
        context = state.get("issue_context")
        if context is None:
            return {}
        if not isinstance(context, Mapping):
            raise AgentToolSelectionError(
                error_code="invalid_issue_context",
                message=(
                    "issue_context must be a mapping "
                    "when present."
                ),
            )

        normalized: dict[str, object] = {}
        for key in (
            "risk_level",
            "health",
            "status",
            "delivery_stage",
        ):
            value = context.get(key)
            if value is None:
                continue
            if (
                not isinstance(value, str)
                or not value.strip()
                or value != value.strip()
            ):
                raise AgentToolSelectionError(
                    error_code=(
                        "invalid_issue_context"
                    ),
                    message=(
                        f"issue_context {key} must be a "
                        "normalized nonblank string."
                    ),
                )
            normalized[key] = value

        return normalized

    def _prior_tool_names(
        self,
        state: Mapping[str, Any],
    ) -> frozenset[str]:
        tool_results = state.get("tool_results")
        if tool_results is None:
            return frozenset()
        if (
            isinstance(tool_results, (str, bytes))
            or not isinstance(
                tool_results,
                Sequence,
            )
        ):
            raise AgentToolSelectionError(
                error_code="invalid_tool_results",
                message=(
                    "tool_results must be a controlled "
                    "sequence."
                ),
            )

        names: list[str] = []
        for item in tool_results:
            if not isinstance(item, Mapping):
                raise AgentToolSelectionError(
                    error_code="invalid_tool_results",
                    message=(
                        "Each tool_results item must be "
                        "a mapping."
                    ),
                )
            tool_name = item.get("tool_name")
            if (
                not isinstance(tool_name, str)
                or not tool_name.strip()
                or tool_name != tool_name.strip()
                or not self._registry.contains(
                    tool_name
                )
            ):
                raise AgentToolSelectionError(
                    error_code="invalid_tool_results",
                    message=(
                        "tool_results contains an "
                        "unapproved Tool name."
                    ),
                )
            names.append(tool_name)

        if len(set(names)) != len(names):
            raise AgentToolSelectionError(
                error_code="duplicate_tool_results",
                message=(
                    "tool_results must not contain "
                    "duplicate Tool names."
                ),
            )

        return frozenset(names)

    @staticmethod
    def _score_candidates(
        *,
        triage_result: Mapping[str, object],
        issue_context: Mapping[str, object],
        clarification_response: object,
    ) -> dict[str, int]:
        scores = dict(BASE_TOOL_SCORES)

        issue_type = str(
            triage_result["issue_type"]
        )
        severity = str(
            triage_result["severity"]
        )
        triage_confidence = float(
            triage_result["confidence"]
        )

        if issue_type in {
            "API",
            "Configuration",
            "Integration",
        }:
            scores[SEARCH_KNOWLEDGE_TOOL] += 25
        else:
            scores[SEARCH_KNOWLEDGE_TOOL] += 20

        if triage_confidence < 0.70:
            scores[GET_ANALYSIS_HISTORY_TOOL] += 40
        elif triage_confidence < 0.85:
            scores[GET_ANALYSIS_HISTORY_TOOL] += 25

        if (
            isinstance(
                clarification_response,
                str,
            )
            and clarification_response.strip()
        ):
            scores[GET_ANALYSIS_HISTORY_TOOL] += 15

        if severity == "critical":
            scores[
                CALCULATE_DELIVERY_RISK_TOOL
            ] += 55
        elif severity == "high":
            scores[
                CALCULATE_DELIVERY_RISK_TOOL
            ] += 35

        if issue_type == "Deployment":
            scores[
                CALCULATE_DELIVERY_RISK_TOOL
            ] += 15

        risk_level = issue_context.get(
            "risk_level"
        )
        health = issue_context.get("health")
        if risk_level == "high":
            scores[
                CALCULATE_DELIVERY_RISK_TOOL
            ] += 50
        if health == "critical":
            scores[
                CALCULATE_DELIVERY_RISK_TOOL
            ] += 50

        return scores

    @staticmethod
    def _selection_reason(
        *,
        tool_name: str,
        triage_result: Mapping[str, object],
        issue_context: Mapping[str, object],
        clarification_response: object,
        prior_tool_names: frozenset[str],
    ) -> str:
        severity = str(
            triage_result["severity"]
        )
        confidence = float(
            triage_result["confidence"]
        )
        risk_level = issue_context.get(
            "risk_level"
        )
        health = issue_context.get("health")

        if tool_name == CALCULATE_DELIVERY_RISK_TOOL:
            reason = (
                "Elevated severity or delivery-risk "
                "signals prioritize a controlled "
                "delivery-risk calculation."
            )
        elif tool_name == GET_ANALYSIS_HISTORY_TOOL:
            if (
                confidence < 0.85
                or (
                    isinstance(
                        clarification_response,
                        str,
                    )
                    and clarification_response.strip()
                )
            ):
                reason = (
                    "Lower-confidence triage or a human "
                    "clarification prioritizes prior "
                    "analysis history."
                )
            else:
                reason = (
                    "Prior analysis history is the "
                    "highest-ranked remaining approved "
                    "evidence source."
                )
        else:
            reason = (
                "Grounded knowledge is the "
                "highest-ranked evidence source for "
                "the confirmed technical triage."
            )

        if prior_tool_names:
            reason = (
                f"{reason} Previously completed Tools were "
                "excluded."
            )

        if (
            tool_name
            == CALCULATE_DELIVERY_RISK_TOOL
            and severity not in {"high", "critical"}
            and risk_level != "high"
            and health != "critical"
        ):
            raise AgentToolSelectionError(
                error_code="invalid_risk_selection",
                message=(
                    "Delivery-risk selection lacks an "
                    "elevated risk signal."
                ),
            )

        return reason


agent_tool_selection_service = (
    AgentToolSelectionService()
)
