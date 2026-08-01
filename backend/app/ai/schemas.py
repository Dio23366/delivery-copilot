from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RiskLevel = Literal['low', 'medium', 'high', 'critical']
ProviderName = Literal['llm', 'rule_based_fallback']
RetrievalStatus = Literal['not_attempted', 'succeeded', 'no_results', 'failed']


@dataclass(frozen=True)
class KnowledgeEvidence:
    citation_id: str
    rank: int
    chunk_id: int
    document_id: int
    document_title: str
    scope_type: str
    doc_type: str
    source_kind: str
    source_name: str | None
    source_uri: str | None
    chunk_index: int
    chunk_text: str
    distance: float
    similarity_score: float


@dataclass(frozen=True)
class KnowledgeCitationSnapshot:
    citation_id: str
    rank: int
    chunk_id: int
    document_id: int
    document_title: str
    scope_type: str
    doc_type: str
    source_kind: str
    source_name: str | None
    source_uri: str | None
    chunk_index: int
    chunk_text: str
    similarity_score: float


@dataclass(frozen=True)
class SupplementalEvidence:
    evidence_id: str
    evidence_type: str
    source_name: str
    content: str


@dataclass(frozen=True)
class GroundedRetrievalOutcome:
    retrieval_status: RetrievalStatus
    retrieval_query: str
    knowledge_evidence: tuple[KnowledgeEvidence, ...]
    knowledge_citations: tuple[KnowledgeCitationSnapshot, ...]
    retrieval_error_code: str | None


@dataclass(frozen=True)
class IssueAnalysisContext:
    issue: dict[str, object]
    project: dict[str, object] | None
    customer: dict[str, object] | None
    retrieval_query: str | None = None
    knowledge_evidence: tuple[KnowledgeEvidence, ...] = ()
    supplemental_evidence: tuple[SupplementalEvidence, ...] = ()


@dataclass(frozen=True)
class IssueAnalysisResult:
    issue_summary: str
    possible_root_cause: str
    recommended_actions: list[str]
    customer_update_draft: str
    risk_level: RiskLevel
    project_impact: str


@dataclass(frozen=True)
class ProviderAnalysisResult(IssueAnalysisResult):
    provider: ProviderName
    model_name: str | None
    prompt_version: str | None
