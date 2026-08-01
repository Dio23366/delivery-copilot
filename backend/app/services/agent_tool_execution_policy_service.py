from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from app.services.agent_tool_contract_service import (
    AgentToolContractService,
    agent_tool_contract_service,
)


AGENT_TOOL_EXECUTION_POLICY_VERSION = (
    "agent_tool_execution_policy_v0.1"
)


@dataclass(frozen=True, slots=True)
class AgentToolExecutionPolicyDecision:
    allowed: bool
    tool_name: str
    tool_version: str
    call_identity: str
    normalized_arguments: Mapping[str, object]
    tool_call_count: int
    max_tool_calls: int
    error_code: str | None
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "call_identity": self.call_identity,
            "normalized_arguments": dict(
                self.normalized_arguments
            ),
            "tool_call_count": self.tool_call_count,
            "max_tool_calls": self.max_tool_calls,
            "error_code": self.error_code,
            "reason": self.reason,
        }


class AgentToolExecutionPolicyService:
    def __init__(
        self,
        *,
        contract_service: AgentToolContractService = (
            agent_tool_contract_service
        ),
    ) -> None:
        if not isinstance(
            contract_service,
            AgentToolContractService,
        ):
            raise TypeError(
                "contract_service must be an "
                "AgentToolContractService"
            )
        self._contract_service = contract_service

    def evaluate(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, object],
        tool_call_count: int,
        max_tool_calls: int,
        prior_call_identities: Iterable[str],
    ) -> AgentToolExecutionPolicyDecision:
        self._validate_counts(
            tool_call_count=tool_call_count,
            max_tool_calls=max_tool_calls,
        )
        identities = self._normalize_identities(
            prior_call_identities
        )
        if len(identities) != tool_call_count:
            raise ValueError(
                "tool_call_count must match the number "
                "of prior_call_identities"
            )

        validated_arguments = (
            self._contract_service.validate_arguments(
                tool_name,
                arguments,
            )
        )
        normalized_arguments = MappingProxyType(
            validated_arguments.as_dict()
        )

        if tool_call_count >= max_tool_calls:
            return AgentToolExecutionPolicyDecision(
                allowed=False,
                tool_name=validated_arguments.tool_name,
                tool_version=(
                    validated_arguments.tool_version
                ),
                call_identity=(
                    validated_arguments.call_identity
                ),
                normalized_arguments=(
                    normalized_arguments
                ),
                tool_call_count=tool_call_count,
                max_tool_calls=max_tool_calls,
                error_code="max_tool_calls_reached",
                reason=(
                    "The Agent Tool call limit has "
                    "already been reached."
                ),
            )

        if (
            validated_arguments.call_identity
            in identities
        ):
            return AgentToolExecutionPolicyDecision(
                allowed=False,
                tool_name=validated_arguments.tool_name,
                tool_version=(
                    validated_arguments.tool_version
                ),
                call_identity=(
                    validated_arguments.call_identity
                ),
                normalized_arguments=(
                    normalized_arguments
                ),
                tool_call_count=tool_call_count,
                max_tool_calls=max_tool_calls,
                error_code="duplicate_tool_call",
                reason=(
                    "An identical approved Tool call "
                    "already exists in this run."
                ),
            )

        return AgentToolExecutionPolicyDecision(
            allowed=True,
            tool_name=validated_arguments.tool_name,
            tool_version=validated_arguments.tool_version,
            call_identity=validated_arguments.call_identity,
            normalized_arguments=normalized_arguments,
            tool_call_count=tool_call_count,
            max_tool_calls=max_tool_calls,
            error_code=None,
            reason="The approved Tool call may execute.",
        )

    @staticmethod
    def _validate_counts(
        *,
        tool_call_count: int,
        max_tool_calls: int,
    ) -> None:
        if (
            type(tool_call_count) is not int
            or tool_call_count < 0
        ):
            raise ValueError(
                "tool_call_count must be a "
                "nonnegative integer"
            )
        if (
            type(max_tool_calls) is not int
            or max_tool_calls <= 0
        ):
            raise ValueError(
                "max_tool_calls must be a "
                "positive integer"
            )

    @staticmethod
    def _normalize_identities(
        prior_call_identities: Iterable[str],
    ) -> tuple[str, ...]:
        if isinstance(
            prior_call_identities,
            (str, bytes),
        ):
            raise TypeError(
                "prior_call_identities must be an "
                "iterable of strings"
            )
        if not isinstance(
            prior_call_identities,
            Iterable,
        ):
            raise TypeError(
                "prior_call_identities must be iterable"
            )

        normalized: list[str] = []
        for identity in prior_call_identities:
            if (
                not isinstance(identity, str)
                or not identity.strip()
            ):
                raise ValueError(
                    "prior call identities must be "
                    "nonblank strings"
                )
            if identity != identity.strip():
                raise ValueError(
                    "prior call identities must be "
                    "normalized"
                )
            normalized.append(identity)

        return tuple(normalized)


agent_tool_execution_policy_service = (
    AgentToolExecutionPolicyService()
)
