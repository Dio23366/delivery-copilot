from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping


AGENT_TOOL_REGISTRY_VERSION = "agent_tool_registry_v0.1"

SEARCH_KNOWLEDGE_TOOL = "search_knowledge"
GET_ANALYSIS_HISTORY_TOOL = "get_analysis_history"
CALCULATE_DELIVERY_RISK_TOOL = "calculate_delivery_risk"

APPROVED_AGENT_TOOL_NAMES = (
    SEARCH_KNOWLEDGE_TOOL,
    GET_ANALYSIS_HISTORY_TOOL,
    CALCULATE_DELIVERY_RISK_TOOL,
)


@dataclass(frozen=True, slots=True)
class AgentToolDefinition:
    tool_name: str
    tool_version: str
    description: str
    adapter_target: str
    timeout_seconds: int
    input_schema_name: str
    output_schema_name: str
    argument_fields: tuple[str, ...]
    result_fields: tuple[str, ...]
    read_only: bool = True
    requires_approval: bool = False
    produces_evidence: bool = False

    def __post_init__(self) -> None:
        string_fields = {
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "description": self.description,
            "adapter_target": self.adapter_target,
            "input_schema_name": self.input_schema_name,
            "output_schema_name": self.output_schema_name,
        }
        for field_name, value in string_fields.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a nonblank string")
            if value != value.strip():
                raise ValueError(f"{field_name} must be normalized")

        if type(self.timeout_seconds) is not int or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive integer")
        if self.read_only is not True:
            raise ValueError("approved Agent tools must be read-only")
        if self.requires_approval is not False:
            raise ValueError(
                "approved read-only Agent tools must not require approval"
            )
        if not isinstance(self.produces_evidence, bool):
            raise ValueError("produces_evidence must be a boolean")

        self._validate_field_names(
            "argument_fields",
            self.argument_fields,
        )
        self._validate_field_names(
            "result_fields",
            self.result_fields,
        )

    @staticmethod
    def _validate_field_names(
        field_name: str,
        values: tuple[str, ...],
    ) -> None:
        if not isinstance(values, tuple) or not values:
            raise ValueError(f"{field_name} must be a nonempty tuple")

        normalized_values: list[str] = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"{field_name} entries must be nonblank strings"
                )
            if value != value.strip():
                raise ValueError(
                    f"{field_name} entries must be normalized"
                )
            normalized_values.append(value)

        if len(set(normalized_values)) != len(normalized_values):
            raise ValueError(f"{field_name} must not contain duplicates")


class ApprovedAgentToolRegistry:
    def __init__(
        self,
        definitions: Iterable[AgentToolDefinition],
        *,
        registry_version: str = AGENT_TOOL_REGISTRY_VERSION,
    ) -> None:
        if (
            not isinstance(registry_version, str)
            or not registry_version.strip()
        ):
            raise ValueError("registry_version must be a nonblank string")
        if registry_version != registry_version.strip():
            raise ValueError("registry_version must be normalized")

        ordered_definitions = tuple(definitions)
        if not ordered_definitions:
            raise ValueError("at least one Agent tool definition is required")

        definitions_by_name: dict[str, AgentToolDefinition] = {}
        for definition in ordered_definitions:
            if not isinstance(definition, AgentToolDefinition):
                raise TypeError(
                    "registry entries must be AgentToolDefinition instances"
                )
            if definition.tool_name in definitions_by_name:
                raise ValueError(
                    "duplicate Agent tool definition: "
                    f"{definition.tool_name}"
                )
            definitions_by_name[definition.tool_name] = definition

        self._registry_version = registry_version
        self._ordered_names = tuple(definitions_by_name)
        self._definitions = MappingProxyType(definitions_by_name)

    @property
    def registry_version(self) -> str:
        return self._registry_version

    @property
    def definitions(self) -> Mapping[str, AgentToolDefinition]:
        return self._definitions

    def contains(self, tool_name: str) -> bool:
        return isinstance(tool_name, str) and tool_name in self._definitions

    def get(self, tool_name: str) -> AgentToolDefinition:
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise ValueError("tool_name must be a nonblank string")

        normalized_tool_name = tool_name.strip()
        definition = self._definitions.get(normalized_tool_name)
        if definition is None:
            raise LookupError(
                f"Agent tool is not approved: {normalized_tool_name}"
            )
        return definition

    def list_names(self) -> tuple[str, ...]:
        return self._ordered_names

    def list_definitions(self) -> tuple[AgentToolDefinition, ...]:
        return tuple(
            self._definitions[tool_name]
            for tool_name in self._ordered_names
        )


APPROVED_AGENT_TOOL_DEFINITIONS = (
    AgentToolDefinition(
        tool_name=SEARCH_KNOWLEDGE_TOOL,
        tool_version="grounded_retrieval_v1",
        description=(
            "Retrieve issue-scoped grounded knowledge evidence and "
            "citation snapshots."
        ),
        adapter_target="AgentSearchKnowledgeToolAdapter.execute",
        timeout_seconds=30,
        input_schema_name="AgentSearchKnowledgeInput",
        output_schema_name="AgentSearchKnowledgeOutput",
        argument_fields=("issue_id",),
        result_fields=(
            "retrieval_status",
            "retrieval_query",
            "knowledge_evidence",
            "knowledge_citations",
            "retrieval_error_code",
        ),
        produces_evidence=True,
    ),
    AgentToolDefinition(
        tool_name=GET_ANALYSIS_HISTORY_TOOL,
        tool_version="analysis_history_v1",
        description=(
            "Read prior issue analysis records in deterministic newest-first "
            "order."
        ),
        adapter_target="AgentAnalysisHistoryToolAdapter.execute",
        timeout_seconds=10,
        input_schema_name="AgentAnalysisHistoryInput",
        output_schema_name="AgentAnalysisHistoryOutput",
        argument_fields=("issue_id",),
        result_fields=(
            "issue_id",
            "analysis_count",
            "analyses",
        ),
        produces_evidence=True,
    ),
    AgentToolDefinition(
        tool_name=CALCULATE_DELIVERY_RISK_TOOL,
        tool_version="delivery_risk_v1",
        description=(
            "Calculate a controlled delivery-risk level from project delivery "
            "signals."
        ),
        adapter_target="AgentDeliveryRiskToolAdapter.execute",
        timeout_seconds=5,
        input_schema_name="AgentDeliveryRiskInput",
        output_schema_name="AgentDeliveryRiskOutput",
        argument_fields=("issue_id",),
        result_fields=(
            "project_id",
            "overdue_requirements",
            "blocked_issues",
            "critical_issues",
            "delivery_completion_rate",
            "risk_level",
        ),
        produces_evidence=False,
    ),
)

approved_agent_tool_registry = ApprovedAgentToolRegistry(
    APPROVED_AGENT_TOOL_DEFINITIONS
)