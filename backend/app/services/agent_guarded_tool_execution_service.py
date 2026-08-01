from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.agent_tool_call_policy_snapshot_service import (
    AgentToolCallPolicySnapshotService,
    agent_tool_call_policy_snapshot_service,
)
from app.services.agent_tool_execution_policy_service import (
    AgentToolExecutionPolicyDecision,
    AgentToolExecutionPolicyService,
    agent_tool_execution_policy_service,
)
from app.services.agent_tool_executor_service import (
    AgentToolExecutionOutcome,
    AgentToolExecutorService,
    agent_tool_executor_service,
)


AGENT_GUARDED_TOOL_EXECUTION_VERSION = (
    "agent_guarded_tool_execution_v0.1"
)


@dataclass(frozen=True, slots=True)
class AgentGuardedToolExecutionOutcome:
    decision: AgentToolExecutionPolicyDecision
    execution: AgentToolExecutionOutcome

    def as_dict(self) -> dict[str, object]:
        return {
            "decision": self.decision.as_dict(),
            "execution": self.execution.as_dict(),
        }


class AgentToolExecutionRejectedError(RuntimeError):
    def __init__(
        self,
        *,
        decision: AgentToolExecutionPolicyDecision,
    ) -> None:
        if decision.allowed:
            raise ValueError(
                "Rejected execution requires a "
                "disallowed policy decision"
            )
        super().__init__(decision.reason)
        self.error_code = decision.error_code
        self.decision = decision


class AgentGuardedToolExecutionService:
    def __init__(
        self,
        *,
        snapshot_service: (
            AgentToolCallPolicySnapshotService
        ) = agent_tool_call_policy_snapshot_service,
        policy_service: AgentToolExecutionPolicyService = (
            agent_tool_execution_policy_service
        ),
        executor_service: AgentToolExecutorService = (
            agent_tool_executor_service
        ),
    ) -> None:
        self._snapshot_service = snapshot_service
        self._policy_service = policy_service
        self._executor_service = executor_service

    def execute_once(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        tool_name: str,
        arguments: Mapping[str, object],
        max_tool_calls: int,
    ) -> AgentGuardedToolExecutionOutcome:
        snapshot = self._snapshot_service.load(
            db,
            run_id=run_id,
        )
        decision = self._policy_service.evaluate(
            tool_name=tool_name,
            arguments=arguments,
            tool_call_count=snapshot.tool_call_count,
            max_tool_calls=max_tool_calls,
            prior_call_identities=(
                snapshot.prior_call_identities
            ),
        )

        if not decision.allowed:
            raise AgentToolExecutionRejectedError(
                decision=decision
            )

        execution = self._executor_service.execute_once(
            db,
            run_id=run_id,
            step_index=step_index,
            tool_name=decision.tool_name,
            arguments=dict(
                decision.normalized_arguments
            ),
        )

        if execution.call_identity != decision.call_identity:
            raise RuntimeError(
                "Executor call identity does not match "
                "the approved policy decision."
            )
        if execution.tool_name != decision.tool_name:
            raise RuntimeError(
                "Executor Tool name does not match "
                "the approved policy decision."
            )
        if execution.tool_version != decision.tool_version:
            raise RuntimeError(
                "Executor Tool version does not match "
                "the approved policy decision."
            )

        return AgentGuardedToolExecutionOutcome(
            decision=decision,
            execution=execution,
        )


agent_guarded_tool_execution_service = (
    AgentGuardedToolExecutionService()
)
