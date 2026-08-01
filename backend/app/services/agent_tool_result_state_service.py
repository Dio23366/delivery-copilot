from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from types import MappingProxyType
from typing import Any

from app.services.agent_guarded_tool_execution_service import (
    AgentGuardedToolExecutionOutcome,
)
from app.services.agent_replay_aware_tool_execution_service import (
    AgentReplayAwareToolExecutionOutcome,
)
from app.services.agent_tool_registry import (
    CALCULATE_DELIVERY_RISK_TOOL,
    GET_ANALYSIS_HISTORY_TOOL,
    SEARCH_KNOWLEDGE_TOOL,
    ApprovedAgentToolRegistry,
    approved_agent_tool_registry,
)
from app.services.agent_tool_selection_service import (
    AGENT_TOOL_SELECTION_VERSION,
)


AGENT_TOOL_RESULT_STATE_VERSION = (
    "agent_tool_result_state_v0.1"
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

SELECTED_TOOL_FIELDS = frozenset(
    {
        "selection_version",
        "tool_name",
        "tool_version",
        "arguments",
        "call_identity",
        "confidence",
        "reason",
    }
)


class AgentToolResultStateError(ValueError):
    def __init__(
        self,
        *,
        error_code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class AgentToolResultStateOutcome:
    tool_result: Mapping[str, object]
    retrieved_evidence: tuple[Mapping[str, object], ...]
    state_update: Mapping[str, object]
    result_state_version: str = (
        AGENT_TOOL_RESULT_STATE_VERSION
    )

    def as_dict(self) -> dict[str, object]:
        return {
            "result_state_version": (
                self.result_state_version
            ),
            "tool_result": dict(self.tool_result),
            "retrieved_evidence": [
                dict(item)
                for item in self.retrieved_evidence
            ],
            "state_update": dict(
                self.state_update
            ),
        }

    def to_state_update(self) -> dict[str, object]:
        return dict(self.state_update)


class AgentToolResultStateService:
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

    def apply(
        self,
        state: Mapping[str, Any],
        execution_outcome: (
            AgentGuardedToolExecutionOutcome
        ),
    ) -> AgentToolResultStateOutcome:
        if not isinstance(state, Mapping):
            raise AgentToolResultStateError(
                error_code="invalid_agent_state",
                message="Agent state must be a mapping.",
            )
        if not isinstance(
            execution_outcome,
            AgentGuardedToolExecutionOutcome,
        ):
            raise AgentToolResultStateError(
                error_code="invalid_execution_outcome",
                message=(
                    "execution_outcome must be an "
                    "AgentGuardedToolExecutionOutcome."
                ),
            )

        selected_tool = self._selected_tool(
            state
        )
        prior_tool_results = (
            self._prior_tool_results(state)
        )
        prior_evidence = (
            self._prior_retrieved_evidence(state)
        )

        decision = execution_outcome.decision
        execution = execution_outcome.execution

        tool_name = self._normalized_text(
            getattr(
                execution,
                "tool_name",
                None,
            ),
            error_code="invalid_execution_tool_name",
            field_name="execution.tool_name",
        )
        tool_version = self._normalized_text(
            getattr(
                execution,
                "tool_version",
                None,
            ),
            error_code=(
                "invalid_execution_tool_version"
            ),
            field_name="execution.tool_version",
        )
        call_identity = self._normalized_text(
            getattr(
                execution,
                "call_identity",
                None,
            ),
            error_code=(
                "invalid_execution_call_identity"
            ),
            field_name="execution.call_identity",
        )

        definition = self._registry.get(
            tool_name
        )
        if tool_version != definition.tool_version:
            raise AgentToolResultStateError(
                error_code="execution_tool_version_mismatch",
                message=(
                    "Execution Tool version does not "
                    "match the approved Registry."
                ),
            )

        selected_name = selected_tool[
            "tool_name"
        ]
        selected_version = selected_tool[
            "tool_version"
        ]
        selected_identity = selected_tool[
            "call_identity"
        ]
        selected_arguments = selected_tool[
            "arguments"
        ]

        if tool_name != selected_name:
            raise AgentToolResultStateError(
                error_code="selected_tool_name_mismatch",
                message=(
                    "Execution Tool name does not match "
                    "selected_tool."
                ),
            )
        if tool_version != selected_version:
            raise AgentToolResultStateError(
                error_code=(
                    "selected_tool_version_mismatch"
                ),
                message=(
                    "Execution Tool version does not "
                    "match selected_tool."
                ),
            )
        if call_identity != selected_identity:
            raise AgentToolResultStateError(
                error_code=(
                    "selected_call_identity_mismatch"
                ),
                message=(
                    "Execution call identity does not "
                    "match selected_tool."
                ),
            )

        self._validate_decision(
            decision=decision,
            tool_name=tool_name,
            tool_version=tool_version,
            call_identity=call_identity,
            selected_arguments=(
                selected_arguments
            ),
        )

        if any(
            item["call_identity"] == call_identity
            for item in prior_tool_results
        ):
            raise AgentToolResultStateError(
                error_code="duplicate_tool_result",
                message=(
                    "tool_results already contains this "
                    "call identity."
                ),
            )

        raw_result = getattr(
            execution,
            "result_json",
            None,
        )
        if not isinstance(raw_result, Mapping):
            raise AgentToolResultStateError(
                error_code="invalid_tool_result_json",
                message=(
                    "execution.result_json must be a "
                    "mapping."
                ),
            )
        result_json = self._json_mapping(
            raw_result,
            error_code="invalid_tool_result_json",
        )

        tool_result = {
            "tool_name": tool_name,
            "tool_version": tool_version,
            "call_identity": call_identity,
            "arguments": dict(
                selected_arguments
            ),
            "result_json": result_json,
            "execution_status": "completed",
        }

        new_evidence = self._extract_evidence(
            definition_produces_evidence=(
                definition.produces_evidence
            ),
            tool_name=tool_name,
            call_identity=call_identity,
            result_json=result_json,
        )

        combined_tool_results = [
            *prior_tool_results,
            tool_result,
        ]
        combined_evidence = [
            *prior_evidence,
            *new_evidence,
        ]

        state_update = {
            "selected_tool": None,
            "tool_results": combined_tool_results,
            "retrieved_evidence": (
                combined_evidence
            ),
        }

        self._assert_json_safe(
            state_update,
            error_code=(
                "result_state_not_json_serializable"
            ),
        )

        return AgentToolResultStateOutcome(
            tool_result=MappingProxyType(
                dict(tool_result)
            ),
            retrieved_evidence=tuple(
                MappingProxyType(dict(item))
                for item in combined_evidence
            ),
            state_update=MappingProxyType(
                dict(state_update)
            ),
        )

    def apply_replay(
        self,
        state: Mapping[str, Any],
        execution_outcome: (
            AgentReplayAwareToolExecutionOutcome
        ),
    ) -> AgentToolResultStateOutcome:
        if not isinstance(state, Mapping):
            raise AgentToolResultStateError(
                error_code="invalid_agent_state",
                message="Agent state must be a mapping.",
            )
        if not isinstance(
            execution_outcome,
            AgentReplayAwareToolExecutionOutcome,
        ):
            raise AgentToolResultStateError(
                error_code="invalid_replay_execution_outcome",
                message=(
                    "execution_outcome must be an "
                    "AgentReplayAwareToolExecutionOutcome."
                ),
            )

        selected_tool = self._selected_tool(state)
        prior_tool_results = self._prior_tool_results(state)
        prior_evidence = self._prior_retrieved_evidence(state)
        execution = execution_outcome.execution
        reservation = execution_outcome.reservation

        tool_name = self._normalized_text(
            getattr(execution, "tool_name", None),
            error_code="invalid_execution_tool_name",
            field_name="execution.tool_name",
        )
        tool_version = self._normalized_text(
            getattr(execution, "tool_version", None),
            error_code="invalid_execution_tool_version",
            field_name="execution.tool_version",
        )
        call_identity = self._normalized_text(
            getattr(execution, "call_identity", None),
            error_code="invalid_execution_call_identity",
            field_name="execution.call_identity",
        )

        definition = self._registry.get(tool_name)
        if tool_version != definition.tool_version:
            raise AgentToolResultStateError(
                error_code="execution_tool_version_mismatch",
                message=(
                    "Execution Tool version does not match "
                    "the approved Registry."
                ),
            )

        selected_name = selected_tool["tool_name"]
        selected_version = selected_tool["tool_version"]
        selected_identity = selected_tool["call_identity"]
        selected_arguments = selected_tool["arguments"]

        if tool_name != selected_name:
            raise AgentToolResultStateError(
                error_code="selected_tool_name_mismatch",
                message=(
                    "Execution Tool name does not match "
                    "selected_tool."
                ),
            )
        if tool_version != selected_version:
            raise AgentToolResultStateError(
                error_code="selected_tool_version_mismatch",
                message=(
                    "Execution Tool version does not match "
                    "selected_tool."
                ),
            )
        if call_identity != selected_identity:
            raise AgentToolResultStateError(
                error_code="selected_call_identity_mismatch",
                message=(
                    "Execution call identity does not match "
                    "selected_tool."
                ),
            )
        if reservation.call_identity != call_identity:
            raise AgentToolResultStateError(
                error_code="replay_reservation_identity_mismatch",
                message=(
                    "Replay reservation identity does not "
                    "match execution."
                ),
            )
        if getattr(execution.tool_call, "call_status", None) != "completed":
            raise AgentToolResultStateError(
                error_code="replay_tool_call_not_completed",
                message=(
                    "Replay result-state mapping requires a "
                    "completed ToolCall."
                ),
            )

        raw_result = getattr(execution, "result_json", None)
        if not isinstance(raw_result, Mapping):
            raise AgentToolResultStateError(
                error_code="invalid_tool_result_json",
                message=(
                    "execution.result_json must be a mapping."
                ),
            )
        result_json = self._json_mapping(
            raw_result,
            error_code="invalid_tool_result_json",
        )
        tool_result = {
            "tool_name": tool_name,
            "tool_version": tool_version,
            "call_identity": call_identity,
            "arguments": dict(selected_arguments),
            "result_json": result_json,
            "execution_status": "completed",
        }
        new_evidence = self._extract_evidence(
            definition_produces_evidence=(
                definition.produces_evidence
            ),
            tool_name=tool_name,
            call_identity=call_identity,
            result_json=result_json,
        )

        matching_results = [
            item
            for item in prior_tool_results
            if item["call_identity"] == call_identity
        ]
        if len(matching_results) > 1:
            raise AgentToolResultStateError(
                error_code="duplicate_replay_tool_result",
                message=(
                    "tool_results contains multiple entries "
                    "for the replay call identity."
                ),
            )

        matching_evidence = [
            item
            for item in prior_evidence
            if item.get("source_call_identity")
            == call_identity
        ]

        if matching_results:
            if matching_results[0] != tool_result:
                raise AgentToolResultStateError(
                    error_code="replay_tool_result_mismatch",
                    message=(
                        "Persisted replay Tool result does not "
                        "match Agent state."
                    ),
                )
            if matching_evidence != new_evidence:
                raise AgentToolResultStateError(
                    error_code="replay_evidence_mismatch",
                    message=(
                        "Persisted replay evidence does not "
                        "match Agent state."
                    ),
                )
            combined_tool_results = prior_tool_results
            combined_evidence = prior_evidence
        else:
            if matching_evidence:
                raise AgentToolResultStateError(
                    error_code="orphan_replay_evidence",
                    message=(
                        "Agent state contains replay evidence "
                        "without the matching Tool result."
                    ),
                )
            combined_tool_results = [
                *prior_tool_results,
                tool_result,
            ]
            combined_evidence = [
                *prior_evidence,
                *new_evidence,
            ]

        state_update = {
            "selected_tool": None,
            "tool_results": combined_tool_results,
            "retrieved_evidence": combined_evidence,
        }
        self._assert_json_safe(
            state_update,
            error_code="result_state_not_json_serializable",
        )

        return AgentToolResultStateOutcome(
            tool_result=MappingProxyType(dict(tool_result)),
            retrieved_evidence=tuple(
                MappingProxyType(dict(item))
                for item in combined_evidence
            ),
            state_update=MappingProxyType(
                dict(state_update)
            ),
        )

    def _selected_tool(
        self,
        state: Mapping[str, Any],
    ) -> dict[str, object]:
        selected = state.get("selected_tool")
        if not isinstance(selected, Mapping):
            raise AgentToolResultStateError(
                error_code="missing_selected_tool",
                message=(
                    "Agent state must contain a "
                    "selected_tool mapping."
                ),
            )

        selected_keys = frozenset(
            selected.keys()
        )
        if selected_keys != SELECTED_TOOL_FIELDS:
            raise AgentToolResultStateError(
                error_code="invalid_selected_tool",
                message=(
                    "selected_tool fields do not match "
                    "the frozen contract."
                ),
            )

        selection_version = self._normalized_text(
            selected.get("selection_version"),
            error_code="invalid_selected_tool",
            field_name=(
                "selected_tool.selection_version"
            ),
        )
        if (
            selection_version
            != AGENT_TOOL_SELECTION_VERSION
        ):
            raise AgentToolResultStateError(
                error_code="invalid_selected_tool",
                message=(
                    "selected_tool selection_version "
                    "is unsupported."
                ),
            )

        tool_name = self._normalized_text(
            selected.get("tool_name"),
            error_code="invalid_selected_tool",
            field_name="selected_tool.tool_name",
        )
        definition = self._registry.get(tool_name)

        tool_version = self._normalized_text(
            selected.get("tool_version"),
            error_code="invalid_selected_tool",
            field_name=(
                "selected_tool.tool_version"
            ),
        )
        if tool_version != definition.tool_version:
            raise AgentToolResultStateError(
                error_code="invalid_selected_tool",
                message=(
                    "selected_tool tool_version does not "
                    "match the approved Registry."
                ),
            )

        call_identity = self._normalized_text(
            selected.get("call_identity"),
            error_code="invalid_selected_tool",
            field_name=(
                "selected_tool.call_identity"
            ),
        )
        arguments = selected.get("arguments")
        if not isinstance(arguments, Mapping):
            raise AgentToolResultStateError(
                error_code="invalid_selected_tool",
                message=(
                    "selected_tool.arguments must be a "
                    "mapping."
                ),
            )
        normalized_arguments = self._json_mapping(
            arguments,
            error_code="invalid_selected_tool",
        )

        confidence = selected.get("confidence")
        if (
            isinstance(confidence, bool)
            or not isinstance(
                confidence,
                (int, float),
            )
            or confidence < 0
            or confidence > 1
        ):
            raise AgentToolResultStateError(
                error_code="invalid_selected_tool",
                message=(
                    "selected_tool.confidence must be "
                    "between 0 and 1."
                ),
            )

        reason = self._normalized_text(
            selected.get("reason"),
            error_code="invalid_selected_tool",
            field_name="selected_tool.reason",
        )

        return {
            "selection_version": selection_version,
            "tool_name": tool_name,
            "tool_version": tool_version,
            "arguments": normalized_arguments,
            "call_identity": call_identity,
            "confidence": float(confidence),
            "reason": reason,
        }

    def _prior_tool_results(
        self,
        state: Mapping[str, Any],
    ) -> list[dict[str, object]]:
        raw = state.get("tool_results")
        if raw is None:
            return []
        items = self._mapping_sequence(
            raw,
            error_code="invalid_tool_results",
            field_name="tool_results",
        )

        identities: set[str] = set()
        normalized: list[dict[str, object]] = []
        for item in items:
            if frozenset(item.keys()) != (
                TOOL_RESULT_FIELDS
            ):
                raise AgentToolResultStateError(
                    error_code="invalid_tool_results",
                    message=(
                        "A prior tool_results item does "
                        "not match the frozen contract."
                    ),
                )
            identity = self._normalized_text(
                item.get("call_identity"),
                error_code="invalid_tool_results",
                field_name=(
                    "tool_results.call_identity"
                ),
            )
            if identity in identities:
                raise AgentToolResultStateError(
                    error_code=(
                        "duplicate_prior_tool_result"
                    ),
                    message=(
                        "Prior tool_results contains a "
                        "duplicate call identity."
                    ),
                )
            identities.add(identity)
            normalized.append(
                self._json_mapping(
                    item,
                    error_code=(
                        "invalid_tool_results"
                    ),
                )
            )

        return normalized

    def _prior_retrieved_evidence(
        self,
        state: Mapping[str, Any],
    ) -> list[dict[str, object]]:
        raw = state.get("retrieved_evidence")
        if raw is None:
            return []
        return self._mapping_sequence(
            raw,
            error_code=(
                "invalid_retrieved_evidence"
            ),
            field_name="retrieved_evidence",
        )

    def _validate_decision(
        self,
        *,
        decision: object,
        tool_name: str,
        tool_version: str,
        call_identity: str,
        selected_arguments: Mapping[str, object],
    ) -> None:
        decision_name = self._normalized_text(
            getattr(
                decision,
                "tool_name",
                None,
            ),
            error_code="invalid_policy_decision",
            field_name="decision.tool_name",
        )
        decision_version = self._normalized_text(
            getattr(
                decision,
                "tool_version",
                None,
            ),
            error_code="invalid_policy_decision",
            field_name="decision.tool_version",
        )
        decision_identity = self._normalized_text(
            getattr(
                decision,
                "call_identity",
                None,
            ),
            error_code="invalid_policy_decision",
            field_name="decision.call_identity",
        )
        decision_arguments = getattr(
            decision,
            "normalized_arguments",
            None,
        )
        if not isinstance(
            decision_arguments,
            Mapping,
        ):
            raise AgentToolResultStateError(
                error_code="invalid_policy_decision",
                message=(
                    "decision.normalized_arguments "
                    "must be a mapping."
                ),
            )
        normalized_decision_arguments = (
            self._json_mapping(
                decision_arguments,
                error_code=(
                    "invalid_policy_decision"
                ),
            )
        )

        if (
            decision_name != tool_name
            or decision_version != tool_version
            or decision_identity != call_identity
            or normalized_decision_arguments
            != dict(selected_arguments)
        ):
            raise AgentToolResultStateError(
                error_code=(
                    "policy_execution_mismatch"
                ),
                message=(
                    "Guarded policy decision does not "
                    "match selected_tool and execution."
                ),
            )

    def _extract_evidence(
        self,
        *,
        definition_produces_evidence: bool,
        tool_name: str,
        call_identity: str,
        result_json: Mapping[str, object],
    ) -> list[dict[str, object]]:
        if not definition_produces_evidence:
            return []

        if tool_name == SEARCH_KNOWLEDGE_TOOL:
            status = result_json.get(
                "retrieval_status"
            )
            if status not in {
                "succeeded",
                "no_results",
                "failed",
            }:
                raise AgentToolResultStateError(
                    error_code=(
                        "invalid_search_result"
                    ),
                    message=(
                        "Search result retrieval_status "
                        "is not controlled."
                    ),
                )
            raw_items = result_json.get(
                "knowledge_evidence",
                [],
            )
            items = self._mapping_sequence(
                raw_items,
                error_code="invalid_search_result",
                field_name=(
                    "knowledge_evidence"
                ),
            )
            if status != "succeeded":
                if items:
                    raise AgentToolResultStateError(
                        error_code=(
                            "invalid_search_result"
                        ),
                        message=(
                            "Only succeeded search "
                            "results may contain evidence."
                        ),
                    )
                return []
            if not items:
                raise AgentToolResultStateError(
                    error_code="invalid_search_result",
                    message=(
                        "Succeeded search result must "
                        "contain knowledge evidence."
                    ),
                )
            return [
                self._evidence_envelope(
                    source_tool=tool_name,
                    source_call_identity=(
                        call_identity
                    ),
                    evidence_type=(
                        "knowledge_chunk"
                    ),
                    payload=item,
                )
                for item in items
            ]

        if tool_name == GET_ANALYSIS_HISTORY_TOOL:
            count = result_json.get(
                "analysis_count"
            )
            if (
                type(count) is not int
                or count < 0
            ):
                raise AgentToolResultStateError(
                    error_code=(
                        "invalid_history_result"
                    ),
                    message=(
                        "analysis_count must be a "
                        "nonnegative integer."
                    ),
                )
            items = self._mapping_sequence(
                result_json.get(
                    "analyses",
                    [],
                ),
                error_code=(
                    "invalid_history_result"
                ),
                field_name="analyses",
            )
            if count != len(items):
                raise AgentToolResultStateError(
                    error_code=(
                        "invalid_history_result"
                    ),
                    message=(
                        "analysis_count must match "
                        "analyses."
                    ),
                )
            return [
                self._evidence_envelope(
                    source_tool=tool_name,
                    source_call_identity=(
                        call_identity
                    ),
                    evidence_type=(
                        "analysis_history"
                    ),
                    payload=item,
                )
                for item in items
            ]

        raise AgentToolResultStateError(
            error_code=(
                "unsupported_evidence_tool"
            ),
            message=(
                "Approved evidence-producing Tool is "
                "not mapped by the result-state "
                "contract."
            ),
        )

    @staticmethod
    def _evidence_envelope(
        *,
        source_tool: str,
        source_call_identity: str,
        evidence_type: str,
        payload: Mapping[str, object],
    ) -> dict[str, object]:
        return {
            "source_tool": source_tool,
            "source_call_identity": (
                source_call_identity
            ),
            "evidence_type": evidence_type,
            "payload": dict(payload),
        }

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
            raise AgentToolResultStateError(
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
        cls._assert_json_safe(
            candidate,
            error_code=error_code,
        )
        serialized = json.dumps(
            candidate,
            ensure_ascii=False,
            sort_keys=True,
        )
        loaded = json.loads(serialized)
        if not isinstance(loaded, dict):
            raise AgentToolResultStateError(
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
            isinstance(
                value,
                (str, bytes),
            )
            or not isinstance(
                value,
                Sequence,
            )
        ):
            raise AgentToolResultStateError(
                error_code=error_code,
                message=(
                    f"{field_name} must be a "
                    "controlled sequence."
                ),
            )

        normalized: list[dict[str, object]] = []
        for item in value:
            if not isinstance(item, Mapping):
                raise AgentToolResultStateError(
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

    @staticmethod
    def _assert_json_safe(
        value: object,
        *,
        error_code: str,
    ) -> None:
        try:
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise AgentToolResultStateError(
                error_code=error_code,
                message=(
                    "Controlled Tool result state must "
                    "be JSON serializable."
                ),
            ) from exc


agent_tool_result_state_service = (
    AgentToolResultStateService()
)
