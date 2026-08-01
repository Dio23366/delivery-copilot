from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from typing import Any

from app.services.agent_tool_registry import (
    CALCULATE_DELIVERY_RISK_TOOL,
    GET_ANALYSIS_HISTORY_TOOL,
    SEARCH_KNOWLEDGE_TOOL,
    ApprovedAgentToolRegistry,
    approved_agent_tool_registry,
)


AGENT_EVIDENCE_EVALUATION_VERSION = (
    "agent_evidence_evaluation_v0.1"
)

GENERATE_ANALYSIS_NODE = "generate_analysis"
SELECT_TOOL_NODE = "select_tool"
REQUEST_CLARIFICATION_NODE = (
    "request_clarification"
)
LIMIT_EXCEEDED_NODE = "limit_exceeded"

APPROVED_TOOL_ORDER = (
    SEARCH_KNOWLEDGE_TOOL,
    GET_ANALYSIS_HISTORY_TOOL,
    CALCULATE_DELIVERY_RISK_TOOL,
)

TOOL_RESULT_FIELDS = frozenset(
    {
        "tool_name",
        "tool_version",
        "call_identity",
        "arguments",
        "result_json",
        "execution_status",
    }
)

EVIDENCE_FIELDS = frozenset(
    {
        "source_tool",
        "source_call_identity",
        "evidence_type",
        "payload",
    }
)


class AgentEvidenceEvaluationError(ValueError):
    def __init__(
        self,
        *,
        error_code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class AgentEvidenceEvaluationDecision:
    next_node: str
    evidence_sufficient: bool
    evidence_reason: str
    completed_tool_count: int
    knowledge_evidence_count: int
    history_evidence_count: int
    unused_tool_names: tuple[str, ...]
    evaluation_version: str = (
        AGENT_EVIDENCE_EVALUATION_VERSION
    )

    def as_dict(self) -> dict[str, object]:
        return {
            "evaluation_version": (
                self.evaluation_version
            ),
            "next_node": self.next_node,
            "evidence_sufficient": (
                self.evidence_sufficient
            ),
            "evidence_reason": (
                self.evidence_reason
            ),
            "completed_tool_count": (
                self.completed_tool_count
            ),
            "knowledge_evidence_count": (
                self.knowledge_evidence_count
            ),
            "history_evidence_count": (
                self.history_evidence_count
            ),
            "unused_tool_names": list(
                self.unused_tool_names
            ),
        }

    def to_state_update(self) -> dict[str, object]:
        return {
            "evidence_sufficient": (
                self.evidence_sufficient
            ),
            "evidence_reason": (
                self.evidence_reason
            ),
        }


class AgentEvidenceEvaluationService:
    def __init__(
        self,
        *,
        registry: ApprovedAgentToolRegistry = (
            approved_agent_tool_registry
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
        self._registry = registry

    def evaluate(
        self,
        state: Mapping[str, Any],
    ) -> AgentEvidenceEvaluationDecision:
        if not isinstance(state, Mapping):
            raise AgentEvidenceEvaluationError(
                error_code="invalid_agent_state",
                message="Agent state must be a mapping.",
            )

        if state.get("triage_confirmed") is not True:
            raise AgentEvidenceEvaluationError(
                error_code="triage_not_confirmed",
                message=(
                    "Evidence evaluation requires "
                    "confirmed triage."
                ),
            )

        if (
            "selected_tool" not in state
            or state.get("selected_tool") is not None
        ):
            raise AgentEvidenceEvaluationError(
                error_code="tool_execution_incomplete",
                message=(
                    "Evidence evaluation requires "
                    "selected_tool to be cleared."
                ),
            )

        max_tool_calls = state.get(
            "max_tool_calls"
        )
        if (
            type(max_tool_calls) is not int
            or max_tool_calls < 1
        ):
            raise AgentEvidenceEvaluationError(
                error_code="invalid_max_tool_calls",
                message=(
                    "max_tool_calls must be a positive "
                    "integer."
                ),
            )

        tool_results = self._tool_results(
            state
        )
        if not tool_results:
            raise AgentEvidenceEvaluationError(
                error_code="missing_tool_results",
                message=(
                    "Evidence evaluation requires at "
                    "least one completed Tool result."
                ),
            )
        if len(tool_results) > max_tool_calls:
            raise AgentEvidenceEvaluationError(
                error_code="tool_budget_inconsistent",
                message=(
                    "Completed Tool results exceed the "
                    "configured Tool budget."
                ),
            )

        evidence = self._retrieved_evidence(
            state,
            tool_results=tool_results,
        )

        completed_names = frozenset(
            item["tool_name"]
            for item in tool_results
        )
        unused_names = tuple(
            tool_name
            for tool_name in APPROVED_TOOL_ORDER
            if tool_name not in completed_names
        )

        knowledge_count = sum(
            1
            for item in evidence
            if item["evidence_type"]
            == "knowledge_chunk"
            and self._knowledge_is_usable(
                item["payload"]
            )
        )
        history_count = sum(
            1
            for item in evidence
            if item["evidence_type"]
            == "analysis_history"
            and self._history_is_usable(
                item["payload"]
            )
        )

        clarification_response = (
            self._clarification_response(state)
        )

        if knowledge_count > 0:
            return self._decision(
                next_node=GENERATE_ANALYSIS_NODE,
                evidence_sufficient=True,
                evidence_reason=(
                    "Grounded knowledge contains at "
                    "least one usable chunk."
                ),
                completed_tool_count=len(
                    tool_results
                ),
                knowledge_evidence_count=(
                    knowledge_count
                ),
                history_evidence_count=(
                    history_count
                ),
                unused_tool_names=unused_names,
            )

        if history_count > 0:
            return self._decision(
                next_node=GENERATE_ANALYSIS_NODE,
                evidence_sufficient=True,
                evidence_reason=(
                    "Accepted analysis history provides "
                    "usable prior evidence."
                ),
                completed_tool_count=len(
                    tool_results
                ),
                knowledge_evidence_count=(
                    knowledge_count
                ),
                history_evidence_count=(
                    history_count
                ),
                unused_tool_names=unused_names,
            )

        remaining_budget = (
            max_tool_calls - len(tool_results)
        )
        if unused_names and remaining_budget > 0:
            return self._decision(
                next_node=SELECT_TOOL_NODE,
                evidence_sufficient=False,
                evidence_reason=(
                    "Current Tool results are "
                    "insufficient and another approved "
                    "unused Tool remains."
                ),
                completed_tool_count=len(
                    tool_results
                ),
                knowledge_evidence_count=(
                    knowledge_count
                ),
                history_evidence_count=(
                    history_count
                ),
                unused_tool_names=unused_names,
            )

        if clarification_response is None:
            return self._decision(
                next_node=REQUEST_CLARIFICATION_NODE,
                evidence_sufficient=False,
                evidence_reason=(
                    "Approved Tool evidence is "
                    "insufficient; focused human "
                    "clarification is required."
                ),
                completed_tool_count=len(
                    tool_results
                ),
                knowledge_evidence_count=(
                    knowledge_count
                ),
                history_evidence_count=(
                    history_count
                ),
                unused_tool_names=unused_names,
            )

        if len(clarification_response) >= 12:
            return self._decision(
                next_node=GENERATE_ANALYSIS_NODE,
                evidence_sufficient=True,
                evidence_reason=(
                    "Human clarification plus completed "
                    "Tool context is sufficient for a "
                    "controlled analysis draft."
                ),
                completed_tool_count=len(
                    tool_results
                ),
                knowledge_evidence_count=(
                    knowledge_count
                ),
                history_evidence_count=(
                    history_count
                ),
                unused_tool_names=unused_names,
            )

        return self._decision(
            next_node=LIMIT_EXCEEDED_NODE,
            evidence_sufficient=False,
            evidence_reason=(
                "The Tool budget is exhausted and the "
                "available clarification remains too "
                "limited for analysis."
            ),
            completed_tool_count=len(tool_results),
            knowledge_evidence_count=(
                knowledge_count
            ),
            history_evidence_count=(
                history_count
            ),
            unused_tool_names=unused_names,
        )

    def _tool_results(
        self,
        state: Mapping[str, Any],
    ) -> list[dict[str, object]]:
        raw = state.get("tool_results")
        items = self._mapping_sequence(
            raw,
            error_code="invalid_tool_results",
            field_name="tool_results",
        )

        identities: set[str] = set()
        tool_names: set[str] = set()
        normalized: list[dict[str, object]] = []

        for item in items:
            if frozenset(item.keys()) != (
                TOOL_RESULT_FIELDS
            ):
                raise AgentEvidenceEvaluationError(
                    error_code="invalid_tool_results",
                    message=(
                        "A tool_results item does not "
                        "match the frozen contract."
                    ),
                )

            tool_name = self._normalized_text(
                item.get("tool_name"),
                error_code="invalid_tool_results",
                field_name="tool_results.tool_name",
            )
            definition = self._registry.get(
                tool_name
            )
            tool_version = self._normalized_text(
                item.get("tool_version"),
                error_code="invalid_tool_results",
                field_name=(
                    "tool_results.tool_version"
                ),
            )
            if tool_version != definition.tool_version:
                raise AgentEvidenceEvaluationError(
                    error_code="invalid_tool_results",
                    message=(
                        "Tool result version does not "
                        "match the approved Registry."
                    ),
                )

            identity = self._normalized_text(
                item.get("call_identity"),
                error_code="invalid_tool_results",
                field_name=(
                    "tool_results.call_identity"
                ),
            )
            expected_prefix = f"{tool_name}:"
            if (
                not identity.startswith(
                    expected_prefix
                )
                or len(
                    identity[
                        len(expected_prefix):
                    ]
                ) != 64
            ):
                raise AgentEvidenceEvaluationError(
                    error_code="invalid_tool_results",
                    message=(
                        "Tool result call identity is "
                        "invalid."
                    ),
                )

            if identity in identities:
                raise AgentEvidenceEvaluationError(
                    error_code=(
                        "duplicate_tool_result_identity"
                    ),
                    message=(
                        "tool_results contains a "
                        "duplicate call identity."
                    ),
                )
            if tool_name in tool_names:
                raise AgentEvidenceEvaluationError(
                    error_code=(
                        "duplicate_completed_tool"
                    ),
                    message=(
                        "The same approved Tool appears "
                        "more than once."
                    ),
                )
            identities.add(identity)
            tool_names.add(tool_name)

            arguments = item.get("arguments")
            result_json = item.get("result_json")
            if not isinstance(arguments, Mapping):
                raise AgentEvidenceEvaluationError(
                    error_code="invalid_tool_results",
                    message=(
                        "Tool result arguments must be "
                        "a mapping."
                    ),
                )
            if not isinstance(result_json, Mapping):
                raise AgentEvidenceEvaluationError(
                    error_code="invalid_tool_results",
                    message=(
                        "Tool result result_json must be "
                        "a mapping."
                    ),
                )
            if item.get("execution_status") != "completed":
                raise AgentEvidenceEvaluationError(
                    error_code="invalid_tool_results",
                    message=(
                        "Only completed Tool results may "
                        "be evaluated."
                    ),
                )

            normalized.append(
                self._json_mapping(
                    item,
                    error_code=(
                        "invalid_tool_results"
                    ),
                )
            )

        return normalized

    def _retrieved_evidence(
        self,
        state: Mapping[str, Any],
        *,
        tool_results: Sequence[
            Mapping[str, object]
        ],
    ) -> list[dict[str, object]]:
        raw = state.get("retrieved_evidence")
        items = self._mapping_sequence(
            raw,
            error_code=(
                "invalid_retrieved_evidence"
            ),
            field_name="retrieved_evidence",
        )

        result_by_identity = {
            str(item["call_identity"]): item
            for item in tool_results
        }
        signatures: set[str] = set()
        normalized: list[dict[str, object]] = []

        for item in items:
            if frozenset(item.keys()) != (
                EVIDENCE_FIELDS
            ):
                raise AgentEvidenceEvaluationError(
                    error_code=(
                        "invalid_retrieved_evidence"
                    ),
                    message=(
                        "A retrieved_evidence item does "
                        "not match the frozen contract."
                    ),
                )

            source_tool = self._normalized_text(
                item.get("source_tool"),
                error_code=(
                    "invalid_retrieved_evidence"
                ),
                field_name=(
                    "retrieved_evidence.source_tool"
                ),
            )
            source_identity = self._normalized_text(
                item.get(
                    "source_call_identity"
                ),
                error_code=(
                    "invalid_retrieved_evidence"
                ),
                field_name=(
                    "retrieved_evidence."
                    "source_call_identity"
                ),
            )
            evidence_type = self._normalized_text(
                item.get("evidence_type"),
                error_code=(
                    "invalid_retrieved_evidence"
                ),
                field_name=(
                    "retrieved_evidence.evidence_type"
                ),
            )
            payload = item.get("payload")
            if not isinstance(payload, Mapping):
                raise AgentEvidenceEvaluationError(
                    error_code=(
                        "invalid_retrieved_evidence"
                    ),
                    message=(
                        "Evidence payload must be a "
                        "mapping."
                    ),
                )

            source_result = result_by_identity.get(
                source_identity
            )
            if source_result is None:
                raise AgentEvidenceEvaluationError(
                    error_code=(
                        "orphan_retrieved_evidence"
                    ),
                    message=(
                        "Evidence does not reference a "
                        "completed Tool result."
                    ),
                )
            if (
                source_result["tool_name"]
                != source_tool
            ):
                raise AgentEvidenceEvaluationError(
                    error_code=(
                        "evidence_tool_mismatch"
                    ),
                    message=(
                        "Evidence source Tool does not "
                        "match its Tool result."
                    ),
                )

            if (
                evidence_type == "knowledge_chunk"
                and source_tool
                != SEARCH_KNOWLEDGE_TOOL
            ):
                raise AgentEvidenceEvaluationError(
                    error_code=(
                        "evidence_type_mismatch"
                    ),
                    message=(
                        "knowledge_chunk evidence must "
                        "come from search_knowledge."
                    ),
                )
            if (
                evidence_type == "analysis_history"
                and source_tool
                != GET_ANALYSIS_HISTORY_TOOL
            ):
                raise AgentEvidenceEvaluationError(
                    error_code=(
                        "evidence_type_mismatch"
                    ),
                    message=(
                        "analysis_history evidence must "
                        "come from "
                        "get_analysis_history."
                    ),
                )
            if evidence_type not in {
                "knowledge_chunk",
                "analysis_history",
            }:
                raise AgentEvidenceEvaluationError(
                    error_code=(
                        "unsupported_evidence_type"
                    ),
                    message=(
                        "Evidence type is not supported."
                    ),
                )

            normalized_item = self._json_mapping(
                item,
                error_code=(
                    "invalid_retrieved_evidence"
                ),
            )
            signature = json.dumps(
                normalized_item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if signature in signatures:
                raise AgentEvidenceEvaluationError(
                    error_code=(
                        "duplicate_retrieved_evidence"
                    ),
                    message=(
                        "retrieved_evidence contains a "
                        "duplicate item."
                    ),
                )
            signatures.add(signature)
            normalized.append(normalized_item)

        return normalized

    @staticmethod
    def _knowledge_is_usable(
        payload: Mapping[str, object],
    ) -> bool:
        chunk_text = payload.get("chunk_text")
        if (
            not isinstance(chunk_text, str)
            or not chunk_text.strip()
        ):
            return False

        similarity = payload.get(
            "similarity_score"
        )
        if similarity is None:
            return True
        if (
            isinstance(similarity, bool)
            or not isinstance(
                similarity,
                (int, float),
            )
            or similarity < 0
            or similarity > 1
        ):
            return False
        return similarity >= 0.60

    @staticmethod
    def _history_is_usable(
        payload: Mapping[str, object],
    ) -> bool:
        feedback_status = payload.get(
            "feedback_status"
        )
        if feedback_status not in {
            "accepted",
            "edited_and_accepted",
        }:
            return False

        summary = payload.get("issue_summary")
        root_cause = payload.get(
            "possible_root_cause"
        )
        actions = payload.get(
            "recommended_actions"
        )

        has_summary = (
            isinstance(summary, str)
            and bool(summary.strip())
        )
        has_root_cause = (
            isinstance(root_cause, str)
            and bool(root_cause.strip())
        )
        has_actions = (
            isinstance(actions, Sequence)
            and not isinstance(
                actions,
                (str, bytes),
            )
            and any(
                isinstance(item, str)
                and bool(item.strip())
                for item in actions
            )
        )
        return (
            has_summary
            or has_root_cause
            or has_actions
        )

    @staticmethod
    def _clarification_response(
        state: Mapping[str, Any],
    ) -> str | None:
        value = state.get(
            "clarification_response"
        )
        if value is None:
            return None
        if (
            not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
        ):
            raise AgentEvidenceEvaluationError(
                error_code=(
                    "invalid_clarification_response"
                ),
                message=(
                    "clarification_response must be a "
                    "normalized nonblank string when "
                    "present."
                ),
            )
        return value

    @staticmethod
    def _decision(
        *,
        next_node: str,
        evidence_sufficient: bool,
        evidence_reason: str,
        completed_tool_count: int,
        knowledge_evidence_count: int,
        history_evidence_count: int,
        unused_tool_names: tuple[str, ...],
    ) -> AgentEvidenceEvaluationDecision:
        return AgentEvidenceEvaluationDecision(
            next_node=next_node,
            evidence_sufficient=(
                evidence_sufficient
            ),
            evidence_reason=evidence_reason,
            completed_tool_count=(
                completed_tool_count
            ),
            knowledge_evidence_count=(
                knowledge_evidence_count
            ),
            history_evidence_count=(
                history_evidence_count
            ),
            unused_tool_names=unused_tool_names,
        )

    @staticmethod
    def _normalized_text(
        value: object,
        *,
        error_code: str,
        field_name: str,
    ) -> str:
        if (
            not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
        ):
            raise AgentEvidenceEvaluationError(
                error_code=error_code,
                message=(
                    f"{field_name} must be a normalized "
                    "nonblank string."
                ),
            )
        return value

    @classmethod
    def _json_mapping(
        cls,
        value: Mapping[object, object],
        *,
        error_code: str,
    ) -> dict[str, object]:
        candidate = dict(value)
        try:
            serialized = json.dumps(
                candidate,
                ensure_ascii=False,
                sort_keys=True,
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise AgentEvidenceEvaluationError(
                error_code=error_code,
                message=(
                    "Controlled evidence state must be "
                    "JSON serializable."
                ),
            ) from exc

        loaded = json.loads(serialized)
        if not isinstance(loaded, dict):
            raise AgentEvidenceEvaluationError(
                error_code=error_code,
                message=(
                    "Controlled JSON mapping was not "
                    "preserved."
                ),
            )
        return loaded

    @classmethod
    def _mapping_sequence(
        cls,
        value: object,
        *,
        error_code: str,
        field_name: str,
    ) -> list[dict[str, object]]:
        if (
            isinstance(value, (str, bytes))
            or not isinstance(value, Sequence)
        ):
            raise AgentEvidenceEvaluationError(
                error_code=error_code,
                message=(
                    f"{field_name} must be a "
                    "controlled sequence."
                ),
            )

        normalized: list[dict[str, object]] = []
        for item in value:
            if not isinstance(item, Mapping):
                raise AgentEvidenceEvaluationError(
                    error_code=error_code,
                    message=(
                        f"Each {field_name} item must "
                        "be a mapping."
                    ),
                )
            normalized.append(
                cls._json_mapping(
                    item,
                    error_code=error_code,
                )
            )
        return normalized


agent_evidence_evaluation_service = (
    AgentEvidenceEvaluationService()
)
