from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from types import ModuleType
from typing import Any

from pydantic import BaseModel, ValidationError

from app.schemas import agent_tools as agent_tool_schemas
from app.services.agent_tool_registry import (
    AgentToolDefinition,
    ApprovedAgentToolRegistry,
    approved_agent_tool_registry,
)


AGENT_TOOL_CALL_IDENTITY_VERSION = "agent_tool_call_identity_v0.1"


class AgentToolContractError(ValueError):
    def __init__(
        self,
        *,
        error_code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class ValidatedAgentToolArguments:
    tool_name: str
    tool_version: str
    input_schema_name: str
    arguments_json: Mapping[str, object]
    canonical_arguments_json: str
    call_identity: str

    def as_dict(self) -> dict[str, object]:
        return dict(self.arguments_json)


@dataclass(frozen=True, slots=True)
class ValidatedAgentToolResult:
    tool_name: str
    tool_version: str
    output_schema_name: str
    result_json: Mapping[str, object]

    def as_dict(self) -> dict[str, object]:
        return dict(self.result_json)


class AgentToolContractService:
    def __init__(
        self,
        *,
        registry: ApprovedAgentToolRegistry = (
            approved_agent_tool_registry
        ),
        schema_module: ModuleType = agent_tool_schemas,
    ) -> None:
        if not isinstance(registry, ApprovedAgentToolRegistry):
            raise TypeError(
                "registry must be an ApprovedAgentToolRegistry"
            )
        if not isinstance(schema_module, ModuleType):
            raise TypeError("schema_module must be a Python module")

        self._registry = registry
        self._schema_module = schema_module

    @property
    def registry(self) -> ApprovedAgentToolRegistry:
        return self._registry

    def validate_arguments(
        self,
        tool_name: str,
        arguments: Mapping[str, object],
    ) -> ValidatedAgentToolArguments:
        definition = self._get_definition(tool_name)
        schema = self._resolve_schema(
            definition.input_schema_name,
            error_code="unknown_input_schema",
        )
        normalized = self._validate_payload(
            schema=schema,
            payload=arguments,
            error_code="invalid_tool_arguments",
        )
        canonical = self._canonical_json(normalized)
        identity = self._build_call_identity(
            tool_name=definition.tool_name,
            canonical_arguments_json=canonical,
        )

        return ValidatedAgentToolArguments(
            tool_name=definition.tool_name,
            tool_version=definition.tool_version,
            input_schema_name=definition.input_schema_name,
            arguments_json=MappingProxyType(normalized),
            canonical_arguments_json=canonical,
            call_identity=identity,
        )

    def validate_result(
        self,
        tool_name: str,
        result: Mapping[str, object],
    ) -> ValidatedAgentToolResult:
        definition = self._get_definition(tool_name)
        schema = self._resolve_schema(
            definition.output_schema_name,
            error_code="unknown_output_schema",
        )
        normalized = self._validate_payload(
            schema=schema,
            payload=result,
            error_code="invalid_tool_result",
        )

        return ValidatedAgentToolResult(
            tool_name=definition.tool_name,
            tool_version=definition.tool_version,
            output_schema_name=definition.output_schema_name,
            result_json=MappingProxyType(normalized),
        )

    def _get_definition(
        self,
        tool_name: str,
    ) -> AgentToolDefinition:
        try:
            return self._registry.get(tool_name)
        except (LookupError, ValueError) as exc:
            raise AgentToolContractError(
                error_code="unapproved_tool",
                message=str(exc),
            ) from exc

    def _resolve_schema(
        self,
        schema_name: str,
        *,
        error_code: str,
    ) -> type[BaseModel]:
        candidate: Any = getattr(
            self._schema_module,
            schema_name,
            None,
        )
        if (
            not isinstance(candidate, type)
            or not issubclass(candidate, BaseModel)
        ):
            raise AgentToolContractError(
                error_code=error_code,
                message=(
                    "Registry schema is unavailable or is not a "
                    f"Pydantic model: {schema_name}"
                ),
            )
        return candidate

    @staticmethod
    def _validate_payload(
        *,
        schema: type[BaseModel],
        payload: Mapping[str, object],
        error_code: str,
    ) -> dict[str, object]:
        if not isinstance(payload, Mapping):
            raise AgentToolContractError(
                error_code=error_code,
                message="Tool payload must be a mapping.",
            )

        try:
            model = schema.model_validate(dict(payload))
        except ValidationError as exc:
            details = [
                {
                    "type": str(item.get("type", "validation_error")),
                    "loc": list(item.get("loc", ())),
                    "msg": str(item.get("msg", "Validation failed.")),
                }
                for item in exc.errors(
                    include_url=False,
                    include_input=False,
                )
            ]
            raise AgentToolContractError(
                error_code=error_code,
                message=json.dumps(
                    details,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ),
            ) from exc

        normalized = model.model_dump(mode="json")
        if not isinstance(normalized, dict):
            raise AgentToolContractError(
                error_code=error_code,
                message="Validated Tool payload must serialize to an object.",
            )

        AgentToolContractService._canonical_json(normalized)
        return normalized

    @staticmethod
    def _canonical_json(payload: Mapping[str, object]) -> str:
        try:
            return json.dumps(
                dict(payload),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise AgentToolContractError(
                error_code="non_json_tool_payload",
                message="Tool payload is not canonical JSON serializable.",
            ) from exc

    @staticmethod
    def _build_call_identity(
        *,
        tool_name: str,
        canonical_arguments_json: str,
    ) -> str:
        digest = sha256(
            canonical_arguments_json.encode("utf-8")
        ).hexdigest()
        return f"{tool_name}:{digest}"


agent_tool_contract_service = AgentToolContractService()