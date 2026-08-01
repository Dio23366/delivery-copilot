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
from app.services.agent_tool_contract_service import (
    AgentToolContractError,
    AgentToolContractService,
    agent_tool_contract_service,
)
from app.services.agent_tool_dispatch_service import (
    AgentToolDispatchError,
    AgentToolDispatchService,
    agent_tool_dispatch_service,
)
from app.services.agent_tool_registry import (
    ApprovedAgentToolRegistry,
    approved_agent_tool_registry,
)


AGENT_TOOL_EXECUTOR_VERSION = "agent_tool_executor_v0.1"


@dataclass(frozen=True, slots=True)
class AgentToolExecutionOutcome:
    tool_call: AgentToolCall
    tool_name: str
    tool_version: str
    call_identity: str
    result_json: Mapping[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "call_identity": self.call_identity,
            "result_json": dict(self.result_json),
        }


class AgentToolExecutorError(RuntimeError):
    def __init__(
        self,
        *,
        error_code: str,
        message: str,
        call_identity: str,
        tool_call: AgentToolCall,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.call_identity = call_identity
        self.tool_call = tool_call


class AgentToolExecutorService:
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

    def execute_once(
        self,
        db: Session,
        *,
        run_id: str,
        step_index: int,
        tool_name: str,
        arguments: Mapping[str, object],
    ) -> AgentToolExecutionOutcome:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError(
                "run_id must be a nonblank string"
            )
        if run_id != run_id.strip():
            raise ValueError("run_id must be normalized")
        if type(step_index) is not int or step_index <= 0:
            raise ValueError(
                "step_index must be a positive integer"
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

        created_tool_call = (
            self._orchestration_service.create_tool_call(
                db,
                run_id=run_id,
                step_index=step_index,
                tool_name=definition.tool_name,
                timeout_seconds=definition.timeout_seconds,
                arguments_json=(
                    validated_arguments.as_dict()
                ),
                tool_version=definition.tool_version,
                read_only=definition.read_only,
                requires_approval=(
                    definition.requires_approval
                ),
            )
        )
        tool_call_index = int(
            created_tool_call.tool_call_index
        )

        running_tool_call = (
            self._orchestration_service.start_tool_call(
                db,
                run_id=run_id,
                step_index=step_index,
                tool_call_index=tool_call_index,
            )
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
                    definition.tool_name,
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
            raise AgentToolExecutorError(
                error_code="TOOL_TIMEOUT",
                message=(
                    "Tool execution reported a timeout."
                ),
                call_identity=(
                    validated_arguments.call_identity
                ),
                tool_call=timed_out_tool_call,
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
            raise AgentToolExecutorError(
                error_code=error_code,
                message=error_message,
                call_identity=(
                    validated_arguments.call_identity
                ),
                tool_call=failed_tool_call,
            ) from exc

        completed_tool_call = (
            self._orchestration_service.complete_tool_call(
                db,
                run_id=run_id,
                step_index=step_index,
                tool_call_index=tool_call_index,
                result_json=validated_result.as_dict(),
            )
        )

        return AgentToolExecutionOutcome(
            tool_call=completed_tool_call,
            tool_name=validated_result.tool_name,
            tool_version=validated_result.tool_version,
            call_identity=(
                validated_arguments.call_identity
            ),
            result_json=MappingProxyType(
                validated_result.as_dict()
            ),
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


agent_tool_executor_service = AgentToolExecutorService()
