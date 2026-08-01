from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingResult:
    embedding: list[float]
    provider: str
    model: str
    dimension: int


@dataclass(frozen=True)
class BatchEmbeddingFailure:
    chunk_id: int
    status_code: int
    detail: str


@dataclass(frozen=True)
class BatchEmbeddingResult:
    document_id: int
    total: int
    succeeded: int
    skipped: int
    failed: int
    status: str
    failures: list[BatchEmbeddingFailure]