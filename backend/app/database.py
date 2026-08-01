from collections.abc import Generator
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.base import Base

DATABASE_DIALECT = urlparse(settings.database_url).scheme.split('+', 1)[0]
engine_kwargs = {'pool_pre_ping': True}
if DATABASE_DIALECT == 'sqlite':
    engine_kwargs['connect_args'] = {'check_same_thread': False}

engine = create_engine(
    settings.database_url,
    **engine_kwargs,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_ai_analysis_log_columns() -> None:
    if DATABASE_DIALECT != 'sqlite':
        return

    with engine.connect() as connection:
        columns = {
            row[1]
            for row in connection.execute(text('PRAGMA table_info(ai_analysis_logs)')).fetchall()
        }
        if not columns:
            return

        if 'provider' not in columns:
            connection.execute(text("ALTER TABLE ai_analysis_logs ADD COLUMN provider VARCHAR(50) DEFAULT 'rule_based_fallback'"))
        if 'model_name' not in columns:
            connection.execute(text('ALTER TABLE ai_analysis_logs ADD COLUMN model_name VARCHAR(255)'))
        if 'prompt_version' not in columns:
            connection.execute(text('ALTER TABLE ai_analysis_logs ADD COLUMN prompt_version VARCHAR(100)'))
        if 'retrieval_status' not in columns:
            connection.execute(text("ALTER TABLE ai_analysis_logs ADD COLUMN retrieval_status VARCHAR(50) NOT NULL DEFAULT 'not_attempted'"))
        if 'retrieval_query' not in columns:
            connection.execute(text('ALTER TABLE ai_analysis_logs ADD COLUMN retrieval_query TEXT'))
        if 'knowledge_citations_json' not in columns:
            connection.execute(text("ALTER TABLE ai_analysis_logs ADD COLUMN knowledge_citations_json TEXT NOT NULL DEFAULT '[]'"))
        if 'retrieval_error_code' not in columns:
            connection.execute(text('ALTER TABLE ai_analysis_logs ADD COLUMN retrieval_error_code VARCHAR(100)'))
        connection.execute(
            text("UPDATE ai_analysis_logs SET provider = COALESCE(provider, 'rule_based_fallback') WHERE provider IS NULL OR provider = ''")
        )
        connection.execute(
            text("UPDATE ai_analysis_logs SET retrieval_status = 'not_attempted' WHERE retrieval_status IS NULL OR retrieval_status = ''")
        )
        connection.execute(
            text("UPDATE ai_analysis_logs SET knowledge_citations_json = '[]' WHERE knowledge_citations_json IS NULL OR knowledge_citations_json = ''")
        )
        connection.commit()


def _normalize_legacy_customer_statuses() -> None:
    if DATABASE_DIALECT != 'sqlite':
        return

    with engine.connect() as connection:
        columns = {
            row[1]
            for row in connection.execute(text('PRAGMA table_info(customers)')).fetchall()
        }
        if not columns:
            return

        connection.execute(
            text("UPDATE customers SET status = 'active' WHERE status = 'onboarding'")
        )
        connection.commit()


def init_db() -> None:
    import app.models  # noqa: F401 — register model metadata

    if DATABASE_DIALECT == 'sqlite':
        Base.metadata.create_all(bind=engine)
        _ensure_ai_analysis_log_columns()
        _normalize_legacy_customer_statuses()
