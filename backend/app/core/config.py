import os

from pydantic import BaseModel, Field, field_validator


def normalize_embedding_base_url(value: str) -> str:
    normalized = value.strip().rstrip('/')

    if normalized.endswith('/chat/completions'):
        normalized = normalized[:-len('/chat/completions')].rstrip('/')

    if normalized.endswith('/embeddings'):
        normalized = normalized[:-len('/embeddings')].rstrip('/')

    if not normalized:
        raise ValueError('Embedding base URL must not be blank')

    return normalized


class Settings(BaseModel):
    app_name: str = 'Enterprise Delivery API'
    database_url: str = os.getenv('DATABASE_URL', 'sqlite:///./enterprise_delivery.db')
    ai_llm_api_key: str | None = os.getenv('AI_LLM_API_KEY') or None
    ai_llm_model: str = os.getenv('AI_LLM_MODEL', 'gpt-4.1-mini')
    ai_llm_base_url: str = os.getenv('AI_LLM_BASE_URL', 'https://api.openai.com/v1/chat/completions')
    ai_llm_timeout_seconds: float = float(os.getenv('AI_LLM_TIMEOUT_SECONDS', '120.0'))
    embedding_provider: str = os.getenv('EMBEDDING_PROVIDER', 'openai')
    embedding_model: str = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')
    embedding_dimension: int = int(os.getenv('EMBEDDING_DIMENSION', '1536'))
    embedding_base_url: str = Field(default_factory=lambda: os.getenv('EMBEDDING_BASE_URL') or os.getenv('AI_LLM_BASE_URL') or 'https://api.openai.com/v1')
    embedding_api_key: str | None = Field(default_factory=lambda: os.getenv('EMBEDDING_API_KEY') or os.getenv('AI_LLM_API_KEY') or None)

    @field_validator('embedding_base_url', mode='after')
    @classmethod
    def resolve_embedding_base_url(cls, value: str) -> str:
        return normalize_embedding_base_url(value)


settings = Settings()
