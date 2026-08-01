from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentRun, AgentStep, AgentToolCall
from app.services.agent_tool_contract_service import (
    AgentToolContractError,
    AgentToolContractService,
    agent_tool_contract_service,
)


AGENT_TOOL_CALL_POLICY_SNAPSHOT_VERSION = (
    "agent_tool_call_policy_snapshot_v0.1"
)


class AgentToolCallPolicySnapshotError(ValueError):
    def __init__(
        self,
        *,
        error_code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class AgentToolCallPolicySnapshot:
    run_id: str
    tool_call_count: int
    prior_call_identities: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "tool_call_count": self.tool_call_count,
            "prior_call_identities": list(
                self.prior_call_identities
            ),
        }


class AgentToolCallPolicySnapshotService:
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

    def load(
        self,
        db: Session,
        *,
        run_id: str,
    ) -> AgentToolCallPolicySnapshot:
        normalized_run_id = self._normalize_run_id(
            run_id
        )

        agent_run = db.scalar(
            select(AgentRun).where(
                AgentRun.run_id == normalized_run_id
            )
        )
        if agent_run is None:
            raise LookupError(
                f"Agent run not found: {normalized_run_id}"
            )

        tool_calls = tuple(
            db.scalars(
                select(AgentToolCall)
                .join(
                    AgentStep,
                    AgentToolCall.agent_step_id
                    == AgentStep.id,
                )
                .where(
                    AgentStep.agent_run_id
                    == agent_run.id
                )
                .order_by(
                    AgentStep.step_index,
                    AgentToolCall.tool_call_index,
                )
            ).all()
        )

        persisted_count = agent_run.tool_call_count
        if (
            type(persisted_count) is not int
            or persisted_count < 0
        ):
            raise AgentToolCallPolicySnapshotError(
                error_code="invalid_persisted_tool_call_count",
                message=(
                    "AgentRun.tool_call_count must be a "
                    "nonnegative integer."
                ),
            )
        if persisted_count != len(tool_calls):
            raise AgentToolCallPolicySnapshotError(
                error_code="tool_call_count_mismatch",
                message=(
                    "AgentRun.tool_call_count does not "
                    "match persisted AgentToolCall rows."
                ),
            )

        identities: list[str] = []
        for tool_call in tool_calls:
            arguments = tool_call.arguments_json
            if not isinstance(arguments, Mapping):
                raise AgentToolCallPolicySnapshotError(
                    error_code="invalid_persisted_tool_arguments",
                    message=(
                        "Persisted Tool arguments must be "
                        "a JSON object."
                    ),
                )

            try:
                validated = (
                    self._contract_service
                    .validate_arguments(
                        tool_call.tool_name,
                        arguments,
                    )
                )
            except AgentToolContractError as exc:
                raise (
                    AgentToolCallPolicySnapshotError(
                        error_code=(
                            "invalid_persisted_tool_call"
                        ),
                        message=(
                            "Persisted ToolCall no longer "
                            "matches the approved contract."
                        ),
                    )
                ) from exc

            if (
                tool_call.tool_version
                != validated.tool_version
            ):
                raise AgentToolCallPolicySnapshotError(
                    error_code=(
                        "persisted_tool_version_mismatch"
                    ),
                    message=(
                        "Persisted Tool version does not "
                        "match the approved Registry."
                    ),
                )

            identities.append(
                validated.call_identity
            )

        return AgentToolCallPolicySnapshot(
            run_id=normalized_run_id,
            tool_call_count=persisted_count,
            prior_call_identities=tuple(identities),
        )

    @staticmethod
    def _normalize_run_id(run_id: str) -> str:
        if not isinstance(run_id, str):
            raise TypeError(
                "run_id must be a string"
            )
        normalized = run_id.strip()
        if not normalized:
            raise ValueError(
                "run_id must be a nonblank string"
            )
        if normalized != run_id:
            raise ValueError(
                "run_id must be normalized"
            )
        return normalized


agent_tool_call_policy_snapshot_service = (
    AgentToolCallPolicySnapshotService()
)
