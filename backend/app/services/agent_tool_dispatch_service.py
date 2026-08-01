from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.services.agent_analysis_history_tool_adapter import (
    agent_analysis_history_tool_adapter,
)
from app.services.agent_delivery_risk_tool_adapter import (
    AgentDeliveryRiskToolAdapter,
)
from app.services.agent_search_knowledge_tool_adapter import (
    agent_search_knowledge_tool_adapter,
)
from app.services.agent_tool_contract_service import (
    ValidatedAgentToolArguments,
)
from app.services.agent_tool_registry import (
    ApprovedAgentToolRegistry,
    approved_agent_tool_registry,
)


AgentToolAdapterCallable = Callable[..., BaseModel]


_agent_delivery_risk_tool_adapter = (
    AgentDeliveryRiskToolAdapter()
)


DEFAULT_AGENT_TOOL_ADAPTERS: Mapping[
    str,
    AgentToolAdapterCallable,
] = MappingProxyType(
    {
        (
            "AgentSearchKnowledgeToolAdapter.execute"
        ): agent_search_knowledge_tool_adapter.execute,
        (
            "AgentAnalysisHistoryToolAdapter.execute"
        ): agent_analysis_history_tool_adapter.execute,
        (
            "AgentDeliveryRiskToolAdapter.execute"
        ): _agent_delivery_risk_tool_adapter.execute,
    }
)


class AgentToolDispatchError(RuntimeError):
    def __init__(
        self,
        *,
        error_code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code


class AgentToolDispatchService:
    def __init__(
        self,
        *,
        registry: ApprovedAgentToolRegistry = (
            approved_agent_tool_registry
        ),
        adapters: Mapping[
            str,
            AgentToolAdapterCallable,
        ] = DEFAULT_AGENT_TOOL_ADAPTERS,
    ) -> None:
        if not isinstance(
            registry,
            ApprovedAgentToolRegistry,
        ):
            raise TypeError(
                "registry must be an "
                "ApprovedAgentToolRegistry"
            )
        if not isinstance(adapters, Mapping):
            raise TypeError(
                "adapters must be a mapping"
            )

        normalized_adapters: dict[
            str,
            AgentToolAdapterCallable,
        ] = {}
        for adapter_target, adapter in adapters.items():
            if (
                not isinstance(adapter_target, str)
                or not adapter_target.strip()
            ):
                raise ValueError(
                    "adapter target must be a "
                    "nonblank string"
                )
            if adapter_target != adapter_target.strip():
                raise ValueError(
                    "adapter target must be normalized"
                )
            if not callable(adapter):
                raise TypeError(
                    "adapter mapping values must be callable"
                )
            normalized_adapters[adapter_target] = adapter

        expected_targets = {
            definition.adapter_target
            for definition
            in registry.list_definitions()
        }
        actual_targets = set(normalized_adapters)

        missing_targets = sorted(
            expected_targets - actual_targets
        )
        unexpected_targets = sorted(
            actual_targets - expected_targets
        )
        if missing_targets or unexpected_targets:
            raise ValueError(
                "Adapter mapping must exactly cover "
                "approved Registry targets; "
                f"missing={missing_targets}; "
                f"unexpected={unexpected_targets}"
            )

        self._registry = registry
        self._adapters = MappingProxyType(
            normalized_adapters
        )

    @property
    def adapters(
        self,
    ) -> Mapping[str, AgentToolAdapterCallable]:
        return self._adapters

    def execute(
        self,
        validated_arguments: ValidatedAgentToolArguments,
        db: Session,
    ) -> BaseModel:
        if not isinstance(
            validated_arguments,
            ValidatedAgentToolArguments,
        ):
            raise TypeError(
                "validated_arguments must be a "
                "ValidatedAgentToolArguments instance"
            )

        try:
            definition = self._registry.get(
                validated_arguments.tool_name
            )
        except (LookupError, ValueError) as exc:
            raise AgentToolDispatchError(
                error_code="unapproved_tool",
                message=str(exc),
            ) from exc

        if (
            validated_arguments.tool_version
            != definition.tool_version
        ):
            raise AgentToolDispatchError(
                error_code="tool_version_mismatch",
                message=(
                    "Validated Tool version does not "
                    "match Registry definition."
                ),
            )
        if (
            validated_arguments.input_schema_name
            != definition.input_schema_name
        ):
            raise AgentToolDispatchError(
                error_code="input_schema_mismatch",
                message=(
                    "Validated input schema does not "
                    "match Registry definition."
                ),
            )

        adapter = self._adapters.get(
            definition.adapter_target
        )
        if adapter is None:
            raise AgentToolDispatchError(
                error_code="tool_adapter_unavailable",
                message=(
                    "Approved Tool adapter is unavailable: "
                    f"{definition.adapter_target}"
                ),
            )

        result = adapter(
            db=db,
            **validated_arguments.as_dict(),
        )
        if not isinstance(result, BaseModel):
            raise AgentToolDispatchError(
                error_code="invalid_adapter_output",
                message=(
                    "Tool adapter must return a "
                    "Pydantic BaseModel."
                ),
            )

        return result


agent_tool_dispatch_service = AgentToolDispatchService()
