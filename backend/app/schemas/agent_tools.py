from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


AgentSearchRetrievalStatus = Literal[
    "succeeded",
    "no_results",
    "failed",
]
AgentAnalysisRetrievalStatus = Literal[
    "not_attempted",
    "succeeded",
    "no_results",
    "failed",
]
AgentRiskLevel = Literal["low", "medium", "high", "critical"]
AgentDeliveryRiskLevel = Literal["low", "medium", "high"]
AgentProviderName = Literal["llm", "rule_based_fallback"]
AgentFeedbackStatus = Literal[
    "pending",
    "accepted",
    "rejected",
    "edited_and_accepted",
]

AGENT_ANALYSIS_HISTORY_LIMIT = 5


class AgentToolSchemaModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )


def _normalize_required_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value must not be blank")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _validate_text_tuple(
    values: tuple[str, ...],
) -> tuple[str, ...]:
    normalized_values: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError("entries must be strings")
        normalized_values.append(_normalize_required_text(value))
    return tuple(normalized_values)


class AgentSearchKnowledgeInput(AgentToolSchemaModel):
    issue_id: int = Field(gt=0)


class AgentKnowledgeEvidence(AgentToolSchemaModel):
    citation_id: str = Field(pattern=r"^K[1-9][0-9]*$")
    rank: int = Field(ge=1)
    chunk_id: int = Field(gt=0)
    document_id: int = Field(gt=0)
    document_title: str = Field(min_length=1)
    scope_type: str = Field(min_length=1)
    doc_type: str = Field(min_length=1)
    source_kind: str = Field(min_length=1)
    source_name: str | None = None
    source_uri: str | None = None
    chunk_index: int = Field(ge=0)
    chunk_text: str = Field(min_length=1)
    distance: float = Field(
        ge=0.0,
        le=2.0,
        allow_inf_nan=False,
    )
    similarity_score: float = Field(
        ge=-1.0,
        le=1.0,
        allow_inf_nan=False,
    )

    @field_validator(
        "document_title",
        "scope_type",
        "doc_type",
        "source_kind",
        "chunk_text",
    )
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        return _normalize_required_text(value)

    @field_validator("source_name", "source_uri")
    @classmethod
    def normalize_optional_text(
        cls,
        value: str | None,
    ) -> str | None:
        return _normalize_optional_text(value)


class AgentKnowledgeCitation(AgentToolSchemaModel):
    citation_id: str = Field(pattern=r"^K[1-9][0-9]*$")
    rank: int = Field(ge=1)
    chunk_id: int = Field(gt=0)
    document_id: int = Field(gt=0)
    document_title: str = Field(min_length=1)
    scope_type: str = Field(min_length=1)
    doc_type: str = Field(min_length=1)
    source_kind: str = Field(min_length=1)
    source_name: str | None = None
    source_uri: str | None = None
    chunk_index: int = Field(ge=0)
    chunk_text: str = Field(min_length=1)
    similarity_score: float = Field(
        ge=-1.0,
        le=1.0,
        allow_inf_nan=False,
    )

    @field_validator(
        "document_title",
        "scope_type",
        "doc_type",
        "source_kind",
        "chunk_text",
    )
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        return _normalize_required_text(value)

    @field_validator("source_name", "source_uri")
    @classmethod
    def normalize_optional_text(
        cls,
        value: str | None,
    ) -> str | None:
        return _normalize_optional_text(value)


class AgentSearchKnowledgeOutput(AgentToolSchemaModel):
    retrieval_status: AgentSearchRetrievalStatus
    retrieval_query: str = Field(min_length=1)
    knowledge_evidence: tuple[AgentKnowledgeEvidence, ...] = ()
    knowledge_citations: tuple[AgentKnowledgeCitation, ...] = ()
    retrieval_error_code: str | None = None

    @field_validator("retrieval_query")
    @classmethod
    def normalize_retrieval_query(cls, value: str) -> str:
        return _normalize_required_text(value)

    @field_validator("retrieval_error_code")
    @classmethod
    def normalize_error_code(
        cls,
        value: str | None,
    ) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def validate_outcome_consistency(self) -> Self:
        evidence = self.knowledge_evidence
        citations = self.knowledge_citations

        if self.retrieval_status == "succeeded":
            if not evidence or not citations:
                raise ValueError(
                    "succeeded retrieval requires evidence and citations"
                )
            if self.retrieval_error_code is not None:
                raise ValueError(
                    "succeeded retrieval must not contain an error code"
                )
        elif self.retrieval_status == "no_results":
            if evidence or citations:
                raise ValueError(
                    "no_results retrieval must not contain evidence"
                )
            if self.retrieval_error_code is not None:
                raise ValueError(
                    "no_results retrieval must not contain an error code"
                )
        else:
            if evidence or citations:
                raise ValueError(
                    "failed retrieval must not contain evidence"
                )
            if self.retrieval_error_code is None:
                raise ValueError(
                    "failed retrieval requires an error code"
                )

        if len(evidence) != len(citations):
            raise ValueError(
                "knowledge evidence and citations must have equal length"
            )

        expected_ranks = tuple(range(1, len(evidence) + 1))
        evidence_ranks = tuple(item.rank for item in evidence)
        citation_ranks = tuple(item.rank for item in citations)

        if evidence_ranks != expected_ranks:
            raise ValueError(
                "knowledge evidence ranks must be continuous"
            )
        if citation_ranks != expected_ranks:
            raise ValueError(
                "knowledge citation ranks must be continuous"
            )

        for evidence_item, citation_item in zip(
            evidence,
            citations,
            strict=True,
        ):
            evidence_identity = (
                evidence_item.citation_id,
                evidence_item.rank,
                evidence_item.chunk_id,
                evidence_item.document_id,
            )
            citation_identity = (
                citation_item.citation_id,
                citation_item.rank,
                citation_item.chunk_id,
                citation_item.document_id,
            )
            if evidence_identity != citation_identity:
                raise ValueError(
                    "evidence and citation identities must match"
                )

        return self


class AgentAnalysisHistoryInput(AgentToolSchemaModel):
    issue_id: int = Field(gt=0)


class AgentAnalysisHistoryItem(AgentToolSchemaModel):
    analysis_id: int = Field(gt=0)
    issue_id: int = Field(gt=0)
    analysis_type: str = Field(min_length=1)
    provider: AgentProviderName
    model_name: str | None = None
    prompt_version: str | None = None
    issue_summary: str = Field(min_length=1)
    possible_root_cause: str = Field(min_length=1)
    recommended_actions: tuple[str, ...] = ()
    customer_update_draft: str = Field(min_length=1)
    risk_level: AgentRiskLevel
    project_impact: str = Field(min_length=1)
    feedback_status: AgentFeedbackStatus
    feedback_note: str | None = None
    edited_output: str | None = None
    retrieval_status: AgentAnalysisRetrievalStatus
    retrieval_query: str | None = None
    knowledge_citations: tuple[AgentKnowledgeCitation, ...] = ()
    retrieval_error_code: str | None = None
    knowledge_grounded: bool
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "analysis_type",
        "issue_summary",
        "possible_root_cause",
        "customer_update_draft",
        "project_impact",
    )
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        return _normalize_required_text(value)

    @field_validator(
        "model_name",
        "prompt_version",
        "feedback_note",
        "edited_output",
        "retrieval_query",
        "retrieval_error_code",
    )
    @classmethod
    def normalize_optional_text(
        cls,
        value: str | None,
    ) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("recommended_actions")
    @classmethod
    def validate_recommended_actions(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        return _validate_text_tuple(values)

    @model_validator(mode="after")
    def validate_grounded_flag(self) -> Self:
        expected_grounded = (
            self.provider == "llm"
            and self.retrieval_status == "succeeded"
            and bool(self.knowledge_citations)
            and self.prompt_version
            == "issue_summarizer_v4_grounded"
        )
        if self.knowledge_grounded is not expected_grounded:
            raise ValueError(
                "knowledge_grounded is inconsistent with analysis data"
            )
        return self


class AgentAnalysisHistoryOutput(AgentToolSchemaModel):
    issue_id: int = Field(gt=0)
    analysis_count: int = Field(
        ge=0,
        le=AGENT_ANALYSIS_HISTORY_LIMIT,
    )
    analyses: tuple[AgentAnalysisHistoryItem, ...] = Field(
        default=(),
        max_length=AGENT_ANALYSIS_HISTORY_LIMIT,
    )

    @model_validator(mode="after")
    def validate_history_consistency(self) -> Self:
        if self.analysis_count != len(self.analyses):
            raise ValueError(
                "analysis_count must equal the number of analyses"
            )

        for item in self.analyses:
            if item.issue_id != self.issue_id:
                raise ValueError(
                    "all analyses must belong to the requested issue"
                )

        ordering_keys = tuple(
            (item.created_at, item.analysis_id)
            for item in self.analyses
        )
        if ordering_keys != tuple(
            sorted(ordering_keys, reverse=True)
        ):
            raise ValueError(
                "analyses must be ordered newest first"
            )

        return self


class AgentDeliveryRiskInput(AgentToolSchemaModel):
    issue_id: int = Field(gt=0)


class AgentDeliveryRiskSignals(AgentToolSchemaModel):
    project_id: int = Field(gt=0)
    overdue_requirements: int = Field(ge=0)
    blocked_issues: int = Field(ge=0)
    critical_issues: int = Field(ge=0)
    delivery_completion_rate: float = Field(
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
    )


class AgentDeliveryRiskOutput(AgentToolSchemaModel):
    project_id: int = Field(gt=0)
    overdue_requirements: int = Field(ge=0)
    blocked_issues: int = Field(ge=0)
    critical_issues: int = Field(ge=0)
    delivery_completion_rate: float = Field(
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
    )
    risk_level: AgentDeliveryRiskLevel