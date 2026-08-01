from __future__ import annotations

import math

import httpx

from app.core.config import settings
from app.embeddings.base import BaseEmbeddingProvider
from app.embeddings.schemas import EmbeddingResult


class EmbeddingConfigurationError(RuntimeError):
    pass


class EmbeddingProviderError(RuntimeError):
    pass


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    provider_name = 'aliyun_model_studio'
    model_name = 'text-embedding-v4'
    dimension = 1536

    def __init__(self) -> None:
        self.api_key = settings.embedding_api_key
        self.provider_name = settings.embedding_provider
        self.model_name = settings.embedding_model
        self.dimension = settings.embedding_dimension
        self.base_url = settings.embedding_base_url.strip().rstrip('/') if settings.embedding_base_url else ''
        self.timeout_seconds = settings.ai_llm_timeout_seconds

    def embed_text(self, text: str) -> EmbeddingResult:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError('text must not be blank')
        if not isinstance(self.provider_name, str) or not self.provider_name.strip():
            raise EmbeddingConfigurationError('Embedding provider is required')
        if not isinstance(self.provider_name, str) or self.provider_name.strip().lower() not in {'openai', 'aliyun_model_studio'}:
            raise EmbeddingConfigurationError('Embedding provider is invalid')
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise EmbeddingConfigurationError('Embedding model is required')
        if not self.base_url:
            raise EmbeddingConfigurationError('Embedding base URL is required')
        if self.base_url.endswith('/chat/completions') or self.base_url.endswith('/embeddings'):
            raise EmbeddingConfigurationError('Embedding base URL is invalid')
        if self.dimension != 1536:
            raise EmbeddingConfigurationError('Embedding dimension must be 1536')
        if not self.api_key:
            raise EmbeddingConfigurationError('Embedding API key is required for embedding generation')

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f'{self.base_url}/embeddings',
                    headers={
                        'Authorization': f'Bearer {self.api_key}',
                        'Content-Type': 'application/json',
                    },
                    json={
                        'model': self.model_name,
                        'input': cleaned,
                        'dimensions': self.dimension,
                        'encoding_format': 'float',
                    },
                )
                response.raise_for_status()
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise EmbeddingProviderError('OpenAI embedding API returned an invalid JSON response') from exc
        except httpx.HTTPStatusError as exc:
            raise EmbeddingProviderError('OpenAI embedding API returned an error') from exc
        except httpx.RequestError as exc:
            raise EmbeddingProviderError('OpenAI embedding API request failed') from exc

        if not isinstance(payload, dict):
            raise EmbeddingProviderError('OpenAI embedding API returned an invalid response')
        data = payload.get('data')
        if not isinstance(data, list) or not data:
            raise EmbeddingProviderError('OpenAI embedding API returned an invalid response')
        first = data[0]
        if not isinstance(first, dict):
            raise EmbeddingProviderError('OpenAI embedding API returned an invalid response')
        embedding = first.get('embedding')
        if not isinstance(embedding, list):
            raise EmbeddingProviderError('OpenAI embedding API returned an invalid embedding payload')
        if len(embedding) != self.dimension:
            raise EmbeddingProviderError('OpenAI embedding dimension mismatch')
        for value in embedding:
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
                raise EmbeddingProviderError('OpenAI embedding contains non-finite values')

        return EmbeddingResult(
            embedding=[float(value) for value in embedding],
            provider=self.provider_name,
            model=self.model_name,
            dimension=self.dimension,
        )
