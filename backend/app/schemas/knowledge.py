from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ScopeType(str, Enum):
    global_scope = 'global'
    customer = 'customer'
    project = 'project'


class DocType(str, Enum):
    api_doc = 'api_doc'
    deployment_guide = 'deployment_guide'
    troubleshooting_guide = 'troubleshooting_guide'
    solution_note = 'solution_note'
    product_guide = 'product_guide'


class SourceKind(str, Enum):
    manual = 'manual'
    uploaded = 'uploaded'
    internal_wiki = 'internal_wiki'
    generated = 'generated'


class KnowledgeStatus(str, Enum):
    pending = 'pending'
    ready = 'ready'
    failed = 'failed'
    archived = 'archived'


class KnowledgeDocumentCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    scope_type: ScopeType
    customer_id: int | None = None
    project_id: int | None = None
    title: str = Field(min_length=1)
    doc_type: DocType
    source_kind: SourceKind
    source_uri: str | None = None
    source_name: str | None = None
    content_text: str = Field(min_length=1)
    version_label: str | None = None

    @field_validator('title')
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('title must not be blank')
        return value

    @field_validator('content_text')
    @classmethod
    def validate_content_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('content_text must not be blank')
        return value


class KnowledgeChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    chunk_index: int
    chunk_text: str
    char_count: int
    source_span_start: int | None
    source_span_end: int | None
    created_at: datetime


class KnowledgeDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scope_type: ScopeType
    customer_id: int | None
    project_id: int | None
    title: str
    doc_type: DocType
    source_kind: SourceKind
    source_uri: str | None = None
    source_name: str | None = None
    content_text: str | None = None
    content_hash: str
    status: KnowledgeStatus
    chunk_count: int
    created_at: datetime
    ingested_at: datetime | None
    last_indexed_at: datetime | None


class KnowledgeDocumentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scope_type: ScopeType
    customer_id: int | None
    project_id: int | None
    title: str
    doc_type: DocType
    source_kind: SourceKind
    source_uri: str | None = None
    source_name: str | None = None
    content_hash: str
    status: KnowledgeStatus
    chunk_count: int
    created_at: datetime
    ingested_at: datetime | None
    last_indexed_at: datetime | None

class KnowledgeSearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    query: str = Field(min_length=1)
    customer_id: int | None = Field(default=None, gt=0)
    project_id: int | None = Field(default=None, gt=0)
    issue_id: int | None = Field(default=None, gt=0)
    top_k: int = Field(default=5, ge=1, le=20)
    min_similarity: float | None = Field(
        default=None,
        ge=-1.0,
        le=1.0,
        allow_inf_nan=False,
    )

    @field_validator('query')
    @classmethod
    def validate_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError('query must not be blank')
        return normalized

    @model_validator(mode='after')
    def validate_context_ids(self) -> 'KnowledgeSearchRequest':
        context_count = sum(
            value is not None
            for value in (
                self.customer_id,
                self.project_id,
                self.issue_id,
            )
        )

        if context_count > 1:
            raise ValueError(
                'Only one of customer_id, project_id, or issue_id may be provided'
            )

        return self


class KnowledgeSearchContext(BaseModel):
    model_config = ConfigDict(extra='forbid')

    customer_id: int | None = Field(default=None, gt=0)
    project_id: int | None = Field(default=None, gt=0)
    issue_id: int | None = Field(default=None, gt=0)
    resolved_scope_types: list[ScopeType] = Field(min_length=1)

    @field_validator('resolved_scope_types')
    @classmethod
    def validate_resolved_scope_types(
        cls,
        value: list[ScopeType],
    ) -> list[ScopeType]:
        if len(value) != len(set(value)):
            raise ValueError('resolved_scope_types must not contain duplicates')
        return value


class KnowledgeSearchResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    rank: int = Field(ge=1)
    chunk_id: int = Field(gt=0)
    document_id: int = Field(gt=0)
    document_title: str
    scope_type: ScopeType
    customer_id: int | None = Field(default=None, gt=0)
    project_id: int | None = Field(default=None, gt=0)
    doc_type: DocType
    source_kind: SourceKind
    source_name: str | None = None
    source_uri: str | None = None
    chunk_index: int = Field(ge=0)
    chunk_text: str
    distance: float = Field(allow_inf_nan=False)
    similarity_score: float = Field(allow_inf_nan=False)


class KnowledgeSearchResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    query: str
    top_k: int = Field(ge=1, le=20)
    min_similarity: float | None = Field(
        default=None,
        ge=-1.0,
        le=1.0,
        allow_inf_nan=False,
    )
    context: KnowledgeSearchContext
    result_count: int = Field(ge=0)
    results: list[KnowledgeSearchResult]

    @model_validator(mode='after')
    def validate_result_summary(self) -> 'KnowledgeSearchResponse':
        if self.result_count != len(self.results):
            raise ValueError('result_count must equal the number of results')

        if self.result_count > self.top_k:
            raise ValueError('result_count must not exceed top_k')

        expected_ranks = list(range(1, self.result_count + 1))
        actual_ranks = [result.rank for result in self.results]

        if actual_ranks != expected_ranks:
            raise ValueError('result ranks must be continuous and start at 1')

        return self
