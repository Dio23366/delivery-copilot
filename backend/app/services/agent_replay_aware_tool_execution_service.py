from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models import AgentToolCall
from app.services.agent_orchestration_service import (
    AgentOrchestrationService,
    agent_orchestration_service,
)
from app.services.agent_persistence_service import (
    AgentToolCallReplayReservation,
)
from app.services.agent_tool_contract_service import (
    AgentToolContractError,
    AgentToolContractService,
    ValidatedAgentToolArguments,
    agent_tool_contract_service,
)
from app.services.agent_tool_dispatch_service import (
    AgentToolDispatchError,
    AgentToolDispatchService,
    agent_tool_dispatch_service,
)
from app.services.agent_tool_executor_service import (
    AgentToolExecutionOutcome,
)
from app.services.agent_tool_registry import (
    AgentToolDefinition,
    ApprovedAgentToolRegistry,
    approved_agent_tool_registry,
)


AGENT_REPLAY_AWARE_TOOL_EXECUTION_VERSION = (
    "agent_replay_aware_tool_execution_v0.1"
)


@dataclass(frozen=True, slots=True)
class AgentReplayAwareToolExecutionOutcome:
    reservation: AgentToolCallReplayReservation
    execution: AgentToolExecutionOutcome
    replayed: bool
    dispatch_performed: bool
    replay_version: str = (
        AGENT_REPLAY_AWARE_TOOL_EXECUTION_VERSION
    )

    def as_dict(self) -> dict[str, object]:
        return {
            "replay_version": self.replay_version,
            "reservation": self.reservation.as_dict(),
            "execution": self.execution.as_dict(),
            "replayed": self.replayed,
            "dispatch_performed": self.dispatch_performed,
        }


class AgentReplayAwareToolExecutionError(RuntimeError):
    def __init__(
        self,
        *,
        error_code: str,
        message: str,
        call_identity: str,
        tool_call: AgentToolCall | None,
        replayed: bool,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.call_identity = call_identity
        self.tool_call = tool_call
        self.replayed = replayed


class AgentReplayAwareToolExecutionService:
    def __init__(
        self,
        *,
        contract_service: AgentToolContractService = (
            agent_tool_contract_service
        ),
        dispatch_service: AgentToolDispatchService = (
            agent_tool_dispatch_service
        ),
        orchestration_service: AgentOrchestrationService = (
            agent_orchestration_service
        ),
        registry: ApprovedAgentToolRegistry = (
            approved_agent_tool_registry
        ),
    ) -> None:
        self._contract_service = contract_service
        self._dispatch_service = dispatch_service
        self._orchestration_service = orchestration_service
        self._registry = registry

    def execute(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        tool_name: str,
        arguments: Mapping[str, object],
        max_tool_calls: int,
    ) -> AgentReplayAwareToolExecutionOutcome:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError(
                "run_id must be a nonblank string"
            )
        if run_id != run_id.strip():
            raise ValueError(
                "run_id must be normalized"
            )
        if type(step_index) is not int or step_index <= 0:
            raise ValueError(
                "step_index must be a positive integer"
            )
        if type(max_tool_calls) is not int or max_tool_calls < 1:
            raise ValueError(
                "max_tool_calls must be a positive integer"
            )

        validated_arguments = (
            self._contract_service.validate_arguments(
                tool_name,
                arguments,
            )
        )
        definition = self._registry.get(
            validated_arguments.tool_name
        )

        if (
            definition.read_only is not True
            or definition.requires_approval is not False
        ):
            raise AgentReplayAwareToolExecutionError(
                error_code="unsafe_replay_tool",
                message=(
                    "Replay-aware execution only supports "
                    "approved read-only tools."
                ),
                call_identity=(
                    validated_arguments.call_identity
                ),
                tool_call=None,
                replayed=False,
            )

        reservation = (
            self._orchestration_service
            .reserve_or_reuse_tool_call(
                db,
                run_id=run_id,
                step_index=step_index,
                tool_name=definition.tool_name,
                arguments_json=(
                    validated_arguments.as_dict()
                ),
                max_tool_calls=max_tool_calls,
            )
        )

        return self._execute_reservation(
            db,
            run_id=run_id,
            step_index=step_index,
            reservation=reservation,
            validated_arguments=validated_arguments,
            definition=definition,
        )

    def execute_current_step(
        self,
        db: Session,
        *,
        run_id: str,
        tool_name: str,
        arguments: Mapping[str, object],
        max_tool_calls: int,
    ) -> AgentReplayAwareToolExecutionOutcome:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError(
                "run_id must be a nonblank string"
            )
        if run_id != run_id.strip():
            raise ValueError(
                "run_id must be normalized"
            )
        if type(max_tool_calls) is not int or max_tool_calls < 1:
            raise ValueError(
                "max_tool_calls must be a positive integer"
            )

        validated_arguments = (
            self._contract_service.validate_arguments(
                tool_name,
                arguments,
            )
        )
        definition = self._registry.get(
            validated_arguments.tool_name
        )

        if (
            definition.read_only is not True
            or definition.requires_approval is not False
        ):
            raise AgentReplayAwareToolExecutionError(
                error_code="unsafe_replay_tool",
                message=(
                    "Replay-aware execution only supports "
                    "approved read-only tools."
                ),
                call_identity=(
                    validated_arguments.call_identity
                ),
                tool_call=None,
                replayed=False,
            )

        reservation = (
            self._orchestration_service
            .reserve_or_reuse_current_tool_call(
                db,
                run_id=run_id,
                tool_name=definition.tool_name,
                arguments_json=(
                    validated_arguments.as_dict()
                ),
                max_tool_calls=max_tool_calls,
            )
        )
        step_index = reservation.step_index
        if type(step_index) is not int or step_index <= 0:
            raise RuntimeError(
                "Current-Step replay reservation must "
                "return a positive step_index."
            )

        return self._execute_reservation(
            db,
            run_id=run_id,
            step_index=step_index,
            reservation=reservation,
            validated_arguments=validated_arguments,
            definition=definition,
        )

    def _execute_reservation(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        reservation: AgentToolCallReplayReservation,
        validated_arguments: ValidatedAgentToolArguments,
        definition: AgentToolDefinition,
    ) -> AgentReplayAwareToolExecutionOutcome:
        if not isinstance(
            reservation,
            AgentToolCallReplayReservation,
        ):
            raise TypeError(
                "reserve_or_reuse_tool_call returned "
                "an invalid reservation type"
            )
        if (
            reservation.call_identity
            != validated_arguments.call_identity
        ):
            raise RuntimeError(
                "Replay reservation call identity does "
                "not match validated arguments."
            )

        tool_call = reservation.tool_call
        self._validate_persisted_tool_call(
            tool_call=tool_call,
            definition=definition,
        )

        if tool_call.call_status == "completed":
            return self._reuse_completed(
                reservation=reservation,
                validated_arguments=validated_arguments,
                tool_call=tool_call,
            )

        if tool_call.call_status in {
            "failed",
            "timed_out",
            "cancelled",
        }:
            self._raise_persisted_terminal(
                reservation=reservation,
                tool_call=tool_call,
            )

        if tool_call.call_status == "created":
            tool_call = (
                self._orchestration_service
                .start_tool_call(
                    db,
                    run_id=run_id,
                    step_index=step_index,
                    tool_call_index=int(
                        tool_call.tool_call_index
                    ),
                )
            )
            if tool_call.call_status != "running":
                raise RuntimeError(
                    "Started ToolCall must be running."
                )
        elif tool_call.call_status != "running":
            raise AgentReplayAwareToolExecutionError(
                error_code="invalid_replay_tool_call_status",
                message=(
                    "Persisted ToolCall has an unsupported "
                    "replay status."
                ),
                call_identity=(
                    validated_arguments.call_identity
                ),
                tool_call=tool_call,
                replayed=(
                    reservation.reservation_action
                    == "reused"
                ),
            )

        return self._dispatch_and_persist(
            db,
            run_id=run_id,
            step_index=step_index,
            reservation=reservation,
            validated_arguments=validated_arguments,
            tool_call=tool_call,
        )

    def _reuse_completed(
        self,
        *,
        reservation: AgentToolCallReplayReservation,
        validated_arguments: ValidatedAgentToolArguments,
        tool_call: AgentToolCall,
    ) -> AgentReplayAwareToolExecutionOutcome:
        raw_result = tool_call.result_json
        if not isinstance(raw_result, Mapping):
            raise AgentReplayAwareToolExecutionError(
                error_code="invalid_persisted_tool_result",
                message=(
                    "Completed ToolCall result_json must be "
                    "a JSON object."
                ),
                call_identity=reservation.call_identity,
                tool_call=tool_call,
                replayed=True,
            )

        try:
            validated_result = (
                self._contract_service.validate_result(
                    validated_arguments.tool_name,
                    raw_result,
                )
            )
        except AgentToolContractError as exc:
            raise AgentReplayAwareToolExecutionError(
                error_code="invalid_persisted_tool_result",
                message=(
                    "Persisted Tool result no longer "
                    "matches the approved contract."
                ),
                call_identity=reservation.call_identity,
                tool_call=tool_call,
                replayed=True,
            ) from exc

        execution = AgentToolExecutionOutcome(
            tool_call=tool_call,
            tool_name=validated_result.tool_name,
            tool_version=validated_result.tool_version,
            call_identity=reservation.call_identity,
            result_json=MappingProxyType(
                validated_result.as_dict()
            ),
        )
        return AgentReplayAwareToolExecutionOutcome(
            reservation=reservation,
            execution=execution,
            replayed=True,
            dispatch_performed=False,
        )

    def _dispatch_and_persist(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        reservation: AgentToolCallReplayReservation,
        validated_arguments: ValidatedAgentToolArguments,
        tool_call: AgentToolCall,
    ) -> AgentReplayAwareToolExecutionOutcome:
        tool_call_index = int(
            tool_call.tool_call_index
        )

        try:
            adapter_output = self._dispatch_service.execute(
                validated_arguments,
                db,
            )
            raw_result = adapter_output.model_dump(
                mode="json"
            )
            validated_result = (
                self._contract_service.validate_result(
                    validated_arguments.tool_name,
                    raw_result,
                )
            )
        except TimeoutError as exc:
            timed_out_tool_call = (
                self._orchestration_service
                .timeout_tool_call(
                    db,
                    run_id=run_id,
                    step_index=step_index,
                    tool_call_index=tool_call_index,
                    error_code="TOOL_TIMEOUT",
                    error_message=(
                        "Tool execution reported a timeout."
                    ),
                )
            )
            raise AgentReplayAwareToolExecutionError(
                error_code="TOOL_TIMEOUT",
                message=(
                    "Tool execution reported a timeout."
                ),
                call_identity=reservation.call_identity,
                tool_call=timed_out_tool_call,
                replayed=(
                    reservation.reservation_action
                    == "reused"
                ),
            ) from exc
        except Exception as exc:
            error_code, error_message = (
                self._classify_failure(exc)
            )
            failed_tool_call = (
                self._orchestration_service.fail_tool_call(
                    db,
                    run_id=run_id,
                    step_index=step_index,
                    tool_call_index=tool_call_index,
                    error_code=error_code,
                    error_message=error_message,
                )
            )
            raise AgentReplayAwareToolExecutionError(
                error_code=error_code,
                message=error_message,
                call_identity=reservation.call_identity,
                tool_call=failed_tool_call,
                replayed=(
                    reservation.reservation_action
                    == "reused"
                ),
            ) from exc

        completed_tool_call = (
            self._orchestration_service
            .complete_tool_call(
                db,
                run_id=run_id,
                step_index=step_index,
                tool_call_index=tool_call_index,
                result_json=validated_result.as_dict(),
            )
        )
        execution = AgentToolExecutionOutcome(
            tool_call=completed_tool_call,
            tool_name=validated_result.tool_name,
            tool_version=validated_result.tool_version,
            call_identity=reservation.call_identity,
            result_json=MappingProxyType(
                validated_result.as_dict()
            ),
        )
        return AgentReplayAwareToolExecutionOutcome(
            reservation=reservation,
            execution=execution,
            replayed=(
                reservation.reservation_action
                == "reused"
            ),
            dispatch_performed=True,
        )

    @staticmethod
    def _validate_persisted_tool_call(
        *,
        tool_call: AgentToolCall,
        definition: AgentToolDefinition,
    ) -> None:
        if (
            type(tool_call.tool_call_index) is not int
            or tool_call.tool_call_index <= 0
        ):
            raise ValueError(
                "Persisted ToolCall index must be positive."
            )
        if tool_call.tool_name != definition.tool_name:
            raise RuntimeError(
                "Persisted Tool name does not match "
                "the approved Registry."
            )
        if tool_call.tool_version != definition.tool_version:
            raise RuntimeError(
                "Persisted Tool version does not match "
                "the approved Registry."
            )
        if (
            tool_call.read_only is not True
            or tool_call.requires_approval is not False
        ):
            raise RuntimeError(
                "Persisted Tool policy is not replay-safe."
            )
        if (
            type(tool_call.timeout_seconds) is not int
            or tool_call.timeout_seconds
            != definition.timeout_seconds
        ):
            raise RuntimeError(
                "Persisted Tool timeout does not match "
                "the approved Registry."
            )

    @staticmethod
    def _raise_persisted_terminal(
        *,
        reservation: AgentToolCallReplayReservation,
        tool_call: AgentToolCall,
    ) -> None:
        defaults = {
            "failed": (
                "tool_execution_failed",
                "Persisted Tool execution failed.",
            ),
            "timed_out": (
                "TOOL_TIMEOUT",
                "Persisted Tool execution timed out.",
            ),
            "cancelled": (
                "TOOL_CANCELLED",
                "Persisted Tool execution was cancelled.",
            ),
        }
        default_code, default_message = defaults[
            tool_call.call_status
        ]

        error_code = tool_call.error_code
        if (
            not isinstance(error_code, str)
            or not error_code.strip()
            or error_code != error_code.strip()
        ):
            error_code = default_code

        error_message = tool_call.error_message
        if (
            not isinstance(error_message, str)
            or not error_message.strip()
        ):
            error_message = default_message
        else:
            error_message = error_message.strip()

        raise AgentReplayAwareToolExecutionError(
            error_code=error_code,
            message=error_message,
            call_identity=reservation.call_identity,
            tool_call=tool_call,
            replayed=True,
        )

    @staticmethod
    def _classify_failure(
        exc: Exception,
    ) -> tuple[str, str]:
        if isinstance(exc, AgentToolContractError):
            return exc.error_code, str(exc)
        if isinstance(exc, AgentToolDispatchError):
            return exc.error_code, str(exc)
        if isinstance(exc, ValidationError):
            return (
                "tool_validation_failed",
                "Tool adapter validation failed.",
            )
        if isinstance(exc, (LookupError, ValueError)):
            message = str(exc).strip()
            if not message:
                message = "Tool business validation failed."
            return "tool_business_error", message[:500]

        return (
            "tool_execution_failed",
            (
                f"{type(exc).__name__} occurred during "
                "Tool execution."
            ),
        )


agent_replay_aware_tool_execution_service = (
    AgentReplayAwareToolExecutionService()
)
