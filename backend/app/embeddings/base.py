from __future__ import annotations

from abc import ABC, abstractmethod

from app.embeddings.schemas import EmbeddingResult


class BaseEmbeddingProvider(ABC):
    provider_name: str
    model_name: str
    dimension: int

    @abstractmethod
    def embed_text(self, text: str) -> EmbeddingResult:
        raise NotImplementedError
